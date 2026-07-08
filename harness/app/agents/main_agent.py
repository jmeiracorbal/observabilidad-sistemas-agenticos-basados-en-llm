# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import json
from dataclasses import dataclass
from typing import Any

from agents.model_call_builder import build_model_call_record
from agents.memory_agent import MemoryAgent, memory_operation
from agents.math_agent import MathAgent
from agents.observability_helpers import record_autorepair_flow, record_decision, record_retry_flow, utc_now
from agents.planner_agent import PlannerAgent, _PLANNER_SYSTEM, _validate_or_repair_plan
from agents.registry import action_names, public_catalog
from agents.researcher_agent import ResearcherAgent
from agents.time_agent import TimeAgent
from agents.writer_agent import WriterAgent
from conversation.context_window import apply_context_window_policy
from conversation.service import ConversationService
from llm.gateway import get_model_name, invoke_llm
from llm.prompt_xml import append_internal_context
from observability.decorators import span
from observability.models import TokenUsage
from observability.run_events import emit_run_event
from observability.tracer import Tracer

_MAIN_ACTIONS = action_names()

_FINAL_RESPONSE_MAX_ATTEMPTS = 3

_DIRECT_ANSWER_SYSTEM = (
    "Eres el asistente que responde al usuario en español. "
    "Responde en una o dos frases cortas, directas y naturales. "
    "El bloque <internal_context> es solo para ti. "
    "Devuelve únicamente la respuesta al usuario: sin etiquetas XML, sin metadata interna "
    "ni menciones a agentes, herramientas o runtime."
)

_FINAL_SYSTEM = (
    "Eres el asistente que responde al usuario en español. "
    "El bloque <internal_context> contiene el historial y el dato calculado por el runtime. "
    "Responde en una o dos frases cortas, directas y naturales e incorpora el dato calculado. "
    "Devuelve únicamente la respuesta al usuario: sin etiquetas XML ni citas del contexto interno."
)

_FINAL_RETRY_SYSTEM = (
    "Eres el asistente que responde al usuario en español. "
    "Tu respuesta anterior fue inválida: no incorporó el dato calculado o filtró contexto interno/XML. "
    "Corrige y devuelve solo la respuesta al usuario en una frase corta con el dato calculado."
)


@dataclass
class FinalPromptContext:
    system: str
    prompt: str
    forbidden_echoes: tuple[str, ...]
    required_inclusion: str | None = None
    contract_evidence: str | None = None


@dataclass
class ConversationContext:
    conversation_id: str
    turn_index: int
    history_text: str
    remaining_input_tokens: int
    output_reserve_tokens: int
    summarized: bool
    truncated: bool


class MainAgent:
    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer
        self._conversations = ConversationService()
        self._planner = PlannerAgent(tracer)
        self._math = MathAgent(tracer)
        self._memory = MemoryAgent(tracer)
        self._time = TimeAgent(tracer)
        self._researcher = ResearcherAgent(tracer)
        self._writer = WriterAgent(tracer)

    def run(self, user_input: str, conversation_id: str | None = None) -> tuple[str, str, str, int]:
        conversation = self._prepare_conversation(user_input, conversation_id)
        run = self._tracer.start_run(user_input, conversation.conversation_id, conversation.turn_index)
        emit_run_event(
            "run_started",
            {
                "run_id": run.id,
                "message": user_input,
                "conversation_id": conversation.conversation_id,
                "turn_index": conversation.turn_index,
                "remaining_input_tokens": conversation.remaining_input_tokens,
                "output_reserve_tokens": conversation.output_reserve_tokens,
            },
        )
        try:
            with span(self._tracer, run.id, "main_agent", "agent") as main_span:
                self._record_conversation_events(main_span.id, user_input, conversation)
                self._conversations.append_message(
                    conversation_id=conversation.conversation_id,
                    run_id=run.id,
                    turn_index=conversation.turn_index,
                    role="user",
                    kind="raw",
                    content=user_input,
                )
                record_decision(
                    self._tracer,
                    main_span.id,
                    "MainAgent",
                    "message_received",
                    user_input,
                    "MainAgent recibe el mensaje del usuario y abre el span principal de ejecución.",
                )
                record_decision(
                    self._tracer,
                    main_span.id,
                    "MainAgent",
                    "catalog_read",
                    user_input,
                    "MainAgent consulta el AgentRegistry: acciones, subagentes, capacidades públicas y tools internas visibles. MainAgent no ejecuta esas tools.",
                    available_tools=list(_MAIN_ACTIONS),
                    payload={"catalog": public_catalog(), "main_agent_generic_tools": []},
                )

                record_decision(
                    self._tracer,
                    main_span.id,
                    "MainAgent",
                    "subagent_call_request",
                    user_input,
                    "MainAgent delega la planificación en PlannerAgent como subagente real.",
                    available_tools=list(_MAIN_ACTIONS),
                    selected_tools=["planner_agent"],
                    payload={"target_agent": "PlannerAgent", "arguments": {"task": user_input, "catalog": public_catalog()}},
                )
                planner_plan = self._planner.run(run.id, user_input, public_catalog(), main_span.id, conversation.history_text, conversation)
                record_decision(
                    self._tracer,
                    main_span.id,
                    "MainAgent",
                    "subagent_call_response",
                    user_input,
                    "MainAgent recibe de PlannerAgent el plan estructurado.",
                    available_tools=list(_MAIN_ACTIONS),
                    selected_tools=[] if planner_plan["selected_action"] == "direct_answer" else [planner_plan["selected_action"]],
                    payload={"source_agent": "PlannerAgent", "plan": planner_plan},
                )
                plan = _validate_plan_contract(planner_plan, user_input)
                plan, repair = _validate_or_repair_plan(plan, user_input)
                if repair:
                    record_autorepair_flow(
                        self._tracer,
                        main_span.id,
                        "MainAgent",
                        user_input,
                        available_tools=list(_MAIN_ACTIONS),
                        selected_tools=[] if plan["selected_action"] == "direct_answer" else [plan["selected_action"]],
                        **repair,
                    )
                selected_action = str(plan["selected_action"])
                selected = [] if selected_action == "direct_answer" else [selected_action]
                record_decision(
                    self._tracer,
                    main_span.id,
                    "MainAgent",
                    "decision_validation",
                    user_input,
                    "MainAgent valida contrato del planner y señales deterministas de dominio antes de delegar subagentes.",
                    available_tools=list(_MAIN_ACTIONS),
                    selected_tools=selected,
                    payload={"planner_plan": planner_plan, "validated_plan": plan, "overridden": plan != planner_plan},
                )

                observation = self._execute_selected_action(run.id, main_span.id, user_input, plan)
                final_response = self._produce_final_response(main_span.id, user_input, plan, observation, conversation)
                self._conversations.append_message(
                    conversation_id=conversation.conversation_id,
                    run_id=run.id,
                    turn_index=conversation.turn_index,
                    role="assistant",
                    kind="raw",
                    content=final_response,
                )
                record_decision(
                    self._tracer,
                    main_span.id,
                    "MainAgent",
                    "final_response",
                    user_input,
                    "MainAgent devuelve al usuario la respuesta final recibida del LLM final.",
                    available_tools=[selected_action],
                    payload={"response": final_response},
                )
                self._tracer.end_run(run.id, "completed")
                return run.id, final_response, conversation.conversation_id, conversation.turn_index
        except Exception:
            self._tracer.end_run(run.id, "failed")
            raise

    def _execute_selected_action(self, run_id: str, span_id: str, user_input: str, plan: dict[str, Any]) -> dict[str, Any]:
        selected_action = str(plan["selected_action"])
        arguments = _normalize_arguments(plan.get("arguments"))
        delegated_task = str(arguments.get("task") or user_input)

        if selected_action == "math_agent":
            record_decision(
                self._tracer,
                span_id,
                "MainAgent",
                "subagent_call_request",
                user_input,
                "MainAgent delega la tarea matemática completa en MathAgent; no extrae expresiones ni invoca calculator.",
                available_tools=list(_MAIN_ACTIONS),
                selected_tools=["math_agent"],
                payload={"target_agent": "MathAgent", "arguments": {"task": delegated_task}},
            )
            observation = self._math.run(run_id, delegated_task, span_id)
            record_decision(
                self._tracer,
                span_id,
                "MainAgent",
                "subagent_call_response",
                user_input,
                "MainAgent recibe de MathAgent la observación normalizada del cálculo.",
                available_tools=["math_agent"],
                payload=observation,
            )
            return observation

        if selected_action == "time_agent":
            record_decision(
                self._tracer,
                span_id,
                "MainAgent",
                "subagent_call_request",
                user_input,
                "MainAgent delega la tarea temporal completa en TimeAgent; no invoca clock.",
                available_tools=list(_MAIN_ACTIONS),
                selected_tools=["time_agent"],
                payload={"target_agent": "TimeAgent", "arguments": {"task": delegated_task}},
            )
            observation = self._time.run(run_id, delegated_task, span_id)
            record_decision(
                self._tracer,
                span_id,
                "MainAgent",
                "subagent_call_response",
                user_input,
                "MainAgent recibe de TimeAgent la observación normalizada de hora/fecha.",
                available_tools=["time_agent"],
                payload=observation,
            )
            return observation

        if selected_action == "memory_agent":
            operation = memory_operation(user_input)
            if operation is None:
                operation = arguments.get("operation")
            if operation not in {"save", "recall"}:
                raise ValueError(f"operación de memoria no soportada: {operation}")
            record_decision(
                self._tracer,
                span_id,
                "MainAgent",
                "subagent_call_request",
                user_input,
                "MainAgent delega la operación de memoria en MemoryAgent.",
                available_tools=list(_MAIN_ACTIONS),
                selected_tools=["memory_agent"],
                payload={"target_agent": "MemoryAgent", "arguments": {"task": delegated_task, "operation": operation}},
            )
            observation = self._memory.run(run_id, delegated_task, operation, span_id)
            record_decision(
                self._tracer,
                span_id,
                "MainAgent",
                "subagent_call_response",
                user_input,
                "MainAgent recibe de MemoryAgent la observación de memoria.",
                available_tools=["memory_agent"],
                payload=observation,
            )
            return observation

        if selected_action == "researcher_agent":
            topic = str(arguments.get("topic") or delegated_task)
            record_decision(
                self._tracer,
                span_id,
                "MainAgent",
                "subagent_call_request",
                user_input,
                "MainAgent delega en ResearcherAgent y posteriormente WriterAgent para elaborar una respuesta contextual.",
                available_tools=list(_MAIN_ACTIONS),
                selected_tools=["researcher_agent", "writer_agent"],
                payload={"target_agent": "ResearcherAgent", "arguments": {"topic": topic}},
            )
            research_output = self._researcher.run(run_id, topic, span_id)
            final_document = self._writer.run(run_id, topic, research_output, span_id)
            observation = {
                "type": "subagent_result",
                "owner_agent": "MainAgent",
                "subagents": ["ResearcherAgent", "WriterAgent"],
                "arguments": {"topic": topic},
                "result": final_document,
            }
            record_decision(
                self._tracer,
                span_id,
                "MainAgent",
                "subagent_call_response",
                user_input,
                "MainAgent recibe el documento final producido por ResearcherAgent/WriterAgent.",
                available_tools=["researcher_agent", "writer_agent"],
                payload=observation,
            )
            return observation

        record_decision(
            self._tracer,
            span_id,
            "MainAgent",
            "direct_answer_selected",
            user_input,
            "MainAgent no delega en subagentes ni tools de dominio; se generará respuesta directa con LLM final.",
            available_tools=list(_MAIN_ACTIONS),
            payload={"selected_action": "direct_answer", "arguments": {"task": delegated_task}},
        )
        return {"type": "no_subagent", "owner_agent": "MainAgent", "tool": None, "arguments": {"task": delegated_task}, "result": "sin subagente ni herramienta de dominio"}

    def _prepare_conversation(self, user_input: str, conversation_id: str | None) -> ConversationContext:
        ensured_id = self._conversations.ensure_conversation(conversation_id)
        existing_messages = self._conversations.list_messages(ensured_id)
        turn_index = self._conversations.next_turn_index(ensured_id)
        context_result = apply_context_window_policy(
            messages=existing_messages,
            system_prompt=_PLANNER_SYSTEM,
            user_message=user_input,
            extra_components=[", ".join(_MAIN_ACTIONS)],
        )
        if context_result.removed_message_ids:
            self._conversations.delete_messages(context_result.removed_message_ids)
        if context_result.summary_text:
            self._conversations.append_message(
                conversation_id=ensured_id,
                run_id=None,
                turn_index=0,
                role="summary",
                kind="summary",
                content=context_result.summary_text,
            )
        return ConversationContext(
            conversation_id=ensured_id,
            turn_index=turn_index,
            history_text=context_result.history_text,
            remaining_input_tokens=context_result.remaining_input_tokens,
            output_reserve_tokens=context_result.output_reserve_tokens,
            summarized=context_result.summarized,
            truncated=context_result.truncated,
        )

    def _record_conversation_events(self, span_id: str, user_input: str, conversation: ConversationContext) -> None:
        record_decision(
            self._tracer,
            span_id,
            "MainAgent",
            "conversation_turn_started",
            user_input,
            "MainAgent inicia o continúa una conversación persistida para este run.",
            payload={
                "conversation_id": conversation.conversation_id,
                "turn_index": conversation.turn_index,
                "history_preview": conversation.history_text[:400],
            },
        )
        record_decision(
            self._tracer,
            span_id,
            "MainAgent",
            "context_window_evaluated",
            user_input,
            "MainAgent calcula presupuesto de ventana antes de invocar al modelo.",
            payload={
                "conversation_id": conversation.conversation_id,
                "turn_index": conversation.turn_index,
                "remaining_input_tokens": conversation.remaining_input_tokens,
                "output_reserve_tokens": conversation.output_reserve_tokens,
                "history_present": bool(conversation.history_text.strip()),
            },
        )
        if conversation.summarized:
            record_decision(
                self._tracer,
                span_id,
                "MainAgent",
                "context_summarized",
                user_input,
                "MainAgent resume historial antiguo para mantener la conversación dentro de la ventana.",
                payload={"conversation_id": conversation.conversation_id, "turn_index": conversation.turn_index},
            )
        if conversation.truncated:
            record_decision(
                self._tracer,
                span_id,
                "MainAgent",
                "context_truncated",
                user_input,
                "MainAgent descarta historial adicional tras resumir porque el presupuesto seguía excedido.",
                payload={"conversation_id": conversation.conversation_id, "turn_index": conversation.turn_index},
            )

    def _produce_final_response(
        self,
        span_id: str,
        user_input: str,
        plan: dict[str, Any],
        observation: dict[str, Any],
        conversation: ConversationContext,
    ) -> str:
        selected_action = str(plan["selected_action"])
        if selected_action == "direct_answer":
            return self._produce_direct_answer(span_id, user_input, plan, conversation)

        result_text = str(observation.get("result", observation))
        history_block = conversation.history_text or "(sin historial previo)"
        rejected_output: str | None = None

        try:
            for attempt in range(_FINAL_RESPONSE_MAX_ATTEMPTS):
                attempt_number = attempt + 1
                is_retry = attempt > 0
                prompt_context = _build_subagent_final_context(
                    history_block,
                    user_input,
                    result_text,
                    selected_action,
                    is_retry=is_retry,
                    rejected_output=rejected_output,
                )
                purpose = "final_response_retry" if is_retry else "final_response"

                record_decision(
                    self._tracer,
                    span_id,
                    "MainAgent",
                    "final_model_request",
                    user_input,
                    (
                        "MainAgent reintenta la respuesta final con un prompt correctivo."
                        if is_retry
                        else "MainAgent consulta al LLM final con el resultado ya producido por el runtime/subagente."
                    ),
                    available_tools=[selected_action],
                    payload={
                        "prompt": prompt_context.prompt,
                        "system": prompt_context.system,
                        "attempt": attempt_number,
                        "max_attempts": _FINAL_RESPONSE_MAX_ATTEMPTS,
                        "is_retry": is_retry,
                        **({"rejected_output": rejected_output} if rejected_output else {}),
                    },
                )
                final_output, tokens = self._invoke_observed_llm(
                    span_id,
                    prompt_context.prompt,
                    prompt_context.system,
                    purpose=purpose,
                    components={
                        "system_prompt": prompt_context.system,
                        "history": history_block,
                        "user_message": user_input,
                        "observation": result_text,
                        "attempt": str(attempt_number),
                        **({"rejected_output": rejected_output} if rejected_output else {}),
                    },
                    remaining_input_tokens=conversation.remaining_input_tokens,
                    output_reserve_tokens=conversation.output_reserve_tokens,
                    summarized=conversation.summarized,
                    truncated=conversation.truncated,
                )
                record_decision(
                    self._tracer,
                    span_id,
                    "LLM Final",
                    "final_model_response",
                    user_input,
                    "El LLM final devuelve el texto de respuesta a MainAgent.",
                    available_tools=[selected_action],
                    payload={
                        "output": final_output,
                        "attempt": attempt_number,
                        "max_attempts": _FINAL_RESPONSE_MAX_ATTEMPTS,
                        "is_retry": is_retry,
                    },
                )
                violation_type = _final_response_violation(final_output, prompt_context)
                if violation_type is None:
                    return final_output

                rejected_output = final_output
                contract_evidence = prompt_context.contract_evidence or result_text
                if attempt < _FINAL_RESPONSE_MAX_ATTEMPTS - 1:
                    record_retry_flow(
                        self._tracer,
                        span_id,
                        "MainAgent",
                        user_input,
                        phase="final_response",
                        violation_type=violation_type,
                        evidence=contract_evidence,
                        from_value=final_output,
                        attempt=attempt_number,
                        max_attempts=_FINAL_RESPONSE_MAX_ATTEMPTS,
                        next_attempt=attempt_number + 1,
                        rationale=_retry_rationale(violation_type, contract_evidence),
                        before={"output": final_output, "expected": contract_evidence, "violation_type": violation_type},
                        after={"strategy": "llm_corrective_prompt", "next_attempt": attempt_number + 1},
                        available_tools=[selected_action],
                        selected_tools=[selected_action],
                    )

            fallback = _fallback_final_response(plan, observation)
            record_autorepair_flow(
                self._tracer,
                span_id,
                "MainAgent",
                user_input,
                phase="final_response",
                conflict_type="contract_violation_after_retries",
                evidence=contract_evidence,
                from_value=rejected_output or "",
                to_value=fallback,
                before={
                    "llm_output": rejected_output,
                    "expected": contract_evidence,
                    "attempts": _FINAL_RESPONSE_MAX_ATTEMPTS,
                },
                after={"response": fallback},
                rationale=(
                    f"El LLM final no cumplió el contrato tras {_FINAL_RESPONSE_MAX_ATTEMPTS} intentos; "
                    "MainAgent usa la respuesta determinista."
                ),
                available_tools=[selected_action],
                selected_tools=[selected_action],
            )
            return fallback
        except Exception as exc:
            self._tracer.record_error(span_id, exc)
            fallback = _fallback_final_response(plan, observation)
            record_decision(
                self._tracer,
                span_id,
                "MainAgent",
                "fallback_event",
                user_input,
                f"No se pudo generar respuesta final con LLM; MainAgent usa fallback textual: {fallback}",
                available_tools=[selected_action],
                payload={"error": str(exc), "fallback_response": fallback},
            )
            return fallback

    def _produce_direct_answer(
        self,
        span_id: str,
        user_input: str,
        plan: dict[str, Any],
        conversation: ConversationContext,
    ) -> str:
        history_block = conversation.history_text or "(sin historial previo)"
        selected_action = str(plan["selected_action"])
        rejected_output: str | None = None

        try:
            for attempt in range(_FINAL_RESPONSE_MAX_ATTEMPTS):
                attempt_number = attempt + 1
                is_retry = attempt > 0
                prompt_context = _build_direct_answer_context(
                    history_block,
                    user_input,
                    is_retry=is_retry,
                    rejected_output=rejected_output,
                )
                purpose = "final_response_retry" if is_retry else "final_response"

                record_decision(
                    self._tracer,
                    span_id,
                    "MainAgent",
                    "final_model_request",
                    user_input,
                    (
                        "MainAgent reintenta la respuesta directa con un prompt correctivo."
                        if is_retry
                        else "MainAgent consulta al LLM final para responder sin subagente de dominio."
                    ),
                    available_tools=[selected_action],
                    payload={
                        "prompt": prompt_context.prompt,
                        "system": prompt_context.system,
                        "attempt": attempt_number,
                        "max_attempts": _FINAL_RESPONSE_MAX_ATTEMPTS,
                        "is_retry": is_retry,
                        **({"rejected_output": rejected_output} if rejected_output else {}),
                    },
                )
                final_output, tokens = self._invoke_observed_llm(
                    span_id,
                    prompt_context.prompt,
                    prompt_context.system,
                    purpose=purpose,
                    components={
                        "system_prompt": prompt_context.system,
                        "history": history_block,
                        "user_message": user_input,
                        "attempt": str(attempt_number),
                        **({"rejected_output": rejected_output} if rejected_output else {}),
                    },
                    remaining_input_tokens=conversation.remaining_input_tokens,
                    output_reserve_tokens=conversation.output_reserve_tokens,
                    summarized=conversation.summarized,
                    truncated=conversation.truncated,
                )
                record_decision(
                    self._tracer,
                    span_id,
                    "LLM Final",
                    "final_model_response",
                    user_input,
                    "El LLM final devuelve el texto de respuesta a MainAgent.",
                    available_tools=[selected_action],
                    payload={
                        "output": final_output,
                        "attempt": attempt_number,
                        "max_attempts": _FINAL_RESPONSE_MAX_ATTEMPTS,
                        "is_retry": is_retry,
                    },
                )
                violation_type = _final_response_violation(final_output, prompt_context)
                if violation_type is None:
                    return final_output

                rejected_output = final_output
                if attempt < _FINAL_RESPONSE_MAX_ATTEMPTS - 1:
                    record_retry_flow(
                        self._tracer,
                        span_id,
                        "MainAgent",
                        user_input,
                        phase="final_response",
                        violation_type=violation_type,
                        evidence="respuesta sin metadata interna",
                        from_value=final_output,
                        attempt=attempt_number,
                        max_attempts=_FINAL_RESPONSE_MAX_ATTEMPTS,
                        next_attempt=attempt_number + 1,
                        rationale=_retry_rationale(violation_type, "respuesta sin metadata interna"),
                        before={"output": final_output, "violation_type": violation_type},
                        after={"strategy": "llm_corrective_prompt", "next_attempt": attempt_number + 1},
                        available_tools=[selected_action],
                        selected_tools=[selected_action],
                    )

            raise RuntimeError("el LLM final filtró contexto interno tras agotar reintentos")
        except Exception as exc:
            self._tracer.record_error(span_id, exc)
            record_decision(
                self._tracer,
                span_id,
                "MainAgent",
                "fallback_event",
                user_input,
                f"No se pudo generar respuesta directa con LLM: {exc}",
                available_tools=[selected_action],
                payload={"error": str(exc)},
            )
            raise

    def _invoke_observed_llm(
        self,
        span_id: str,
        prompt: str,
        system: str,
        purpose: str,
        components: dict[str, str],
        remaining_input_tokens: int | None = None,
        output_reserve_tokens: int | None = None,
        summarized: bool = False,
        truncated: bool = False,
    ) -> tuple[str, TokenUsage]:
        started = utc_now()
        output, tokens = invoke_llm(prompt, system=system, purpose=purpose)
        ended = utc_now()
        self._tracer.record_model_call(
            span_id,
            build_model_call_record(
                model=get_model_name(),
                system=system,
                prompt=prompt,
                output=output,
                input_tokens=tokens.input,
                output_tokens=tokens.output,
                purpose=purpose,
                components=components,
                remaining_input_tokens=remaining_input_tokens,
                output_reserve_tokens=output_reserve_tokens,
                summarized=summarized,
                truncated=truncated,
                started_at=started,
                ended_at=ended,
            ),
        )
        return output, tokens


def _validate_plan_contract(plan: dict[str, Any], user_input: str) -> dict[str, Any]:
    selected_action = str(plan.get("selected_action", "")).strip()
    if selected_action not in _MAIN_ACTIONS:
        raise ValueError(f"acción no disponible en AgentRegistry: {selected_action}")

    arguments = _normalize_arguments(plan.get("arguments"))
    if selected_action in {"math_agent", "time_agent", "direct_answer", "memory_agent"}:
        arguments = {**arguments, "task": user_input}
    if selected_action == "memory_agent":
        operation = arguments.get("operation") or memory_operation(user_input)
        if operation is None:
            raise ValueError("memory_agent requiere operación save o recall derivable del mensaje")
        arguments = {**arguments, "operation": operation}
    if selected_action == "researcher_agent" and not (arguments.get("topic") or arguments.get("task")):
        arguments = {**arguments, "topic": user_input}

    return {**plan, "arguments": arguments}


def _normalize_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _build_direct_answer_context(
    history_block: str,
    user_input: str,
    *,
    is_retry: bool,
    rejected_output: str | None,
) -> FinalPromptContext:
    sections: dict[str, str] = {"conversation_history": history_block}
    if is_retry and rejected_output:
        sections["rejected_attempt"] = rejected_output
    base_system = _FINAL_RETRY_SYSTEM if is_retry else _DIRECT_ANSWER_SYSTEM
    system, forbidden_echoes = append_internal_context(base_system, **sections)
    return FinalPromptContext(
        system=system,
        prompt=user_input,
        forbidden_echoes=forbidden_echoes,
    )


def _build_subagent_final_context(
    history_block: str,
    user_input: str,
    result: str,
    selected_action: str,
    *,
    is_retry: bool,
    rejected_output: str | None,
) -> FinalPromptContext:
    sections: dict[str, str] = {
        "conversation_history": history_block,
        "runtime_result": result,
    }
    if is_retry and rejected_output:
        sections["rejected_attempt"] = rejected_output
    base_system = _FINAL_RETRY_SYSTEM if is_retry else _FINAL_SYSTEM
    system, forbidden_echoes = append_internal_context(base_system, **sections)
    required_inclusion = result if selected_action in {"math_agent", "time_agent"} else None
    return FinalPromptContext(
        system=system,
        prompt=user_input,
        forbidden_echoes=forbidden_echoes,
        required_inclusion=required_inclusion,
        contract_evidence=required_inclusion or result,
    )


def _retry_rationale(violation_type: str, evidence: str) -> str:
    if violation_type == "echoes_internal_context":
        return "La salida filtró contexto interno; MainAgent reintenta con prompt correctivo."
    return f"La salida no cumple el contrato ({evidence}); MainAgent reintenta con prompt correctivo."


def _fallback_final_response(plan: dict[str, Any], observation: dict[str, Any]) -> str:
    selected_action = str(plan.get("selected_action"))
    if selected_action == "math_agent":
        expression = observation.get("arguments", {}).get("expression", observation.get("arguments", {}).get("task", "la tarea matemática"))
        return f"El resultado de {expression} es {observation.get('result')}."
    if selected_action == "time_agent":
        return f"La hora actual en UTC es {observation.get('result')}."
    if selected_action == "memory_agent":
        return str(observation.get("result", "No se pudo completar la operación de memoria."))
    if selected_action == "researcher_agent":
        return str(observation.get("result", "No se pudo generar una respuesta."))
    raise ValueError(f"no hay fallback determinista para la acción {selected_action}")


def _final_response_violation(llm_output: str, prompt_context: FinalPromptContext) -> str | None:
    actual = llm_output.strip()
    if not actual:
        return "empty_output"

    for marker in prompt_context.forbidden_echoes:
        if marker in actual:
            return "echoes_internal_context"

    required = prompt_context.required_inclusion
    if required and required.lower() not in actual.lower():
        return "missing_expected_result"

    return None
