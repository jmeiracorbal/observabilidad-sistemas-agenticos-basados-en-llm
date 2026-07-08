# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import json
from dataclasses import dataclass
from typing import Any

from agents.model_call_builder import build_model_call_record
from agents.math_agent import MathAgent
from agents.observability_helpers import record_decision, utc_now
from agents.planner_agent import PlannerAgent, _PLANNER_SYSTEM, _validate_or_repair_plan
from agents.registry import action_names, public_catalog
from agents.researcher_agent import ResearcherAgent
from agents.time_agent import TimeAgent
from agents.writer_agent import WriterAgent
from conversation.context_window import apply_context_window_policy
from conversation.service import ConversationService
from llm.gateway import get_model_name, invoke_llm
from observability.decorators import span
from observability.models import TokenUsage
from observability.run_events import emit_run_event
from observability.tracer import Tracer

_MAIN_ACTIONS = action_names()

_FINAL_SYSTEM = "Responde al usuario con la observación recibida. Sé breve."


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
                plan = _validate_or_repair_plan(plan, user_input)
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
        result = observation.get("result", observation)
        history_block = conversation.history_text or "(sin historial previo)"
        final_prompt = (
            f"Historial:\n{history_block}\n\n"
            f"Usuario: {user_input}\n"
            f"Observación: {result}\n"
            "Respuesta:"
        )
        record_decision(
            self._tracer,
            span_id,
            "MainAgent",
            "final_model_request",
            user_input,
            "MainAgent consulta al LLM final con la observación ya producida por el runtime/subagente.",
            available_tools=[str(plan["selected_action"])],
            payload={"prompt": final_prompt, "system": _FINAL_SYSTEM},
        )
        try:
            final_output, tokens = self._invoke_observed_llm(
                span_id,
                final_prompt,
                _FINAL_SYSTEM,
                purpose="final_response",
                components={
                    "system_prompt": _FINAL_SYSTEM,
                    "history": history_block,
                    "user_message": user_input,
                    "observation": str(result),
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
                available_tools=[str(plan["selected_action"])],
                payload={"output": final_output},
            )
            return final_output
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
                available_tools=[str(plan["selected_action"])],
                payload={"error": str(exc), "fallback_response": fallback},
            )
            return fallback

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
    if selected_action in {"math_agent", "time_agent", "direct_answer"}:
        arguments = {**arguments, "task": user_input}
    if selected_action == "researcher_agent" and not (arguments.get("topic") or arguments.get("task")):
        arguments = {**arguments, "topic": user_input}

    return {**plan, "arguments": arguments}


def _normalize_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _fallback_final_response(plan: dict[str, Any], observation: dict[str, Any]) -> str:
    selected_action = str(plan.get("selected_action"))
    if selected_action == "math_agent":
        expression = observation.get("arguments", {}).get("expression", observation.get("arguments", {}).get("task", "la tarea matemática"))
        return f"El resultado de {expression} es {observation.get('result')}."
    if selected_action == "time_agent":
        return f"La hora actual en UTC es {observation.get('result')}."
    if selected_action == "researcher_agent":
        return str(observation.get("result", "No se pudo generar una respuesta."))
    return str(observation.get("result", "Respuesta generada sin herramienta externa."))
