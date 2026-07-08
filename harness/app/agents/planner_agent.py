# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import json
import re
from typing import Any

from agents.model_call_builder import build_model_call_record
from agents.observability_helpers import record_decision, utc_now
from agents.registry import action_names
from llm.gateway import get_model_name, invoke_llm_structured
from llm.planner_schemas import PlannerAssessment, PlannerDecision
from observability.decorators import span
from observability.models import TokenUsage
from observability.tracer import Tracer

_MAIN_ACTIONS = action_names()
_MATH_EXPRESSION = re.compile(
    r"(?<!\w)(\d+(?:\.\d+)?(?:\s*(?:[-+*/]|\*\*)\s*\d+(?:\.\d+)?)+)(?!\w)"
)
_TIME_KEYWORDS = ("hora", "fecha actual", "tiempo actual", "current time", "current date", "clock")

_PLANNER_SYSTEM = (
    "Planner del runtime. Elige una acción del catálogo para la petición del usuario. "
    "Incluye hidden_reasoning breve (thought, evidence, decision_impact)."
)


class PlannerAgent:
    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def run(
        self,
        run_id: str,
        user_input: str,
        catalog: list[dict],
        parent_span_id: str,
        conversation_history: str,
        conversation: Any,
    ) -> dict[str, Any]:
        with span(self._tracer, run_id, "planner_agent", "agent", parent_span_id) as planner_span:
            planning_context = _planning_context(user_input, catalog, conversation_history)
            record_decision(
                self._tracer,
                planner_span.id,
                "PlannerAgent",
                "planning_context_received",
                user_input,
                "PlannerAgent recibe de MainAgent el contexto inicial de planificación.",
                available_tools=list(_MAIN_ACTIONS),
                payload={"planning_context": planning_context},
            )

            try:
                assessment = self._run_assessment(planner_span.id, user_input, planning_context, conversation)
                enriched_context = _enrich_context(planning_context, assessment)
                record_decision(
                    self._tracer,
                    planner_span.id,
                    "PlannerAgent",
                    "planning_context_enrichment",
                    user_input,
                    "PlannerAgent agrega señales derivadas del registry/runtime antes de pedir la decisión final.",
                    available_tools=list(_MAIN_ACTIONS),
                    payload={
                        "planning_context": enriched_context,
                        "hidden_reasoning": _runtime_hidden_reasoning(enriched_context),
                        "visibility": "hidden",
                    },
                )

                raw_plan = self._run_decision(planner_span.id, user_input, enriched_context, assessment, conversation)
                plan = _validate_or_repair_plan(raw_plan, user_input)
                if plan != raw_plan:
                    record_decision(
                        self._tracer,
                        planner_span.id,
                        "PlannerAgent",
                        "planning_decision_verified",
                        user_input,
                        "PlannerAgent corrige la decisión del LLM planner porque contradice una intención inequívoca del usuario.",
                        available_tools=list(_MAIN_ACTIONS),
                        selected_tools=[] if plan["selected_action"] == "direct_answer" else [plan["selected_action"]],
                        payload={
                            "planner_plan": raw_plan,
                            "validated_plan": plan,
                            "overridden": True,
                            "hidden_reasoning": plan.get("hidden_reasoning", []),
                            "visibility": "hidden",
                        },
                    )

                combined_hidden_reasoning = _combine_hidden_reasoning(assessment, plan)
                record_decision(
                    self._tracer,
                    planner_span.id,
                    "PlannerAgent",
                    "hidden_reasoning_generated",
                    user_input,
                    "PlannerAgent consolida el razonamiento oculto generado durante la planificación.",
                    available_tools=list(_MAIN_ACTIONS),
                    selected_tools=[] if plan["selected_action"] == "direct_answer" else [plan["selected_action"]],
                    payload={
                        "hidden_reasoning": combined_hidden_reasoning,
                        "visibility": "hidden",
                        "selected_action": plan["selected_action"],
                    },
                )
                record_decision(
                    self._tracer,
                    planner_span.id,
                    "PlannerAgent",
                    "planning_finalized",
                    user_input,
                    "PlannerAgent finaliza la planificación y prepara el plan estructurado para MainAgent.",
                    available_tools=list(_MAIN_ACTIONS),
                    selected_tools=[] if plan["selected_action"] == "direct_answer" else [plan["selected_action"]],
                    payload={
                        "plan": plan,
                        "hidden_reasoning": combined_hidden_reasoning,
                        "visibility": "hidden",
                    },
                )
                record_decision(
                    self._tracer,
                    planner_span.id,
                    "PlannerAgent",
                    "subagent_call_response",
                    user_input,
                    "PlannerAgent devuelve el plan estructurado a MainAgent.",
                    available_tools=list(_MAIN_ACTIONS),
                    selected_tools=[] if plan["selected_action"] == "direct_answer" else [plan["selected_action"]],
                    payload={"plan": plan, "hidden_reasoning": combined_hidden_reasoning, "visibility": "hidden"},
                )
                return plan
            except Exception as exc:
                self._tracer.record_error(planner_span.id, exc)
                fallback = _validate_or_repair_plan(_fallback_plan(user_input), user_input)
                record_decision(
                    self._tracer,
                    planner_span.id,
                    "PlannerAgent",
                    "fallback_event",
                    user_input,
                    "PlannerAgent no pudo obtener/parsear un plan válido y devuelve un fallback estructural.",
                    available_tools=list(_MAIN_ACTIONS),
                    selected_tools=[],
                    payload={"error": str(exc), "fallback_plan": fallback, "hidden_reasoning": fallback["hidden_reasoning"], "visibility": "hidden"},
                )
                record_decision(
                    self._tracer,
                    planner_span.id,
                    "PlannerAgent",
                    "subagent_call_response",
                    user_input,
                    "PlannerAgent devuelve fallback estructurado a MainAgent.",
                    available_tools=list(_MAIN_ACTIONS),
                    selected_tools=[],
                    payload={"plan": fallback, "hidden_reasoning": fallback["hidden_reasoning"], "visibility": "hidden"},
                )
                return fallback

    def _run_assessment(
        self,
        span_id: str,
        user_input: str,
        planning_context: dict[str, Any],
        conversation: Any,
    ) -> dict[str, Any]:
        history = str(planning_context.get("conversation_history") or "(sin historial previo)")
        prompt = (
            f"Historial:\n{history}\n\n"
            f"Usuario: {user_input}\n"
            f"Acciones: {', '.join(_MAIN_ACTIONS)}\n"
            "Assessment de planificación."
        )
        record_decision(
            self._tracer,
            span_id,
            "PlannerAgent",
            "planning_assessment_request",
            user_input,
            "PlannerAgent pregunta al LLM qué entiende de la tarea, qué candidatos existen y qué información falta.",
            available_tools=["llm_planner"],
            selected_tools=["llm_planner"],
            payload={"prompt": prompt, "system": _PLANNER_SYSTEM},
        )
        parse_error = None
        output = ""
        tokens = TokenUsage(input=0, output=0)
        try:
            assessment_model, output, tokens = self._invoke_observed_structured_llm(
                span_id,
                prompt,
                _PLANNER_SYSTEM,
                "planner_assessment",
                PlannerAssessment,
                {
                    "system_prompt": _PLANNER_SYSTEM,
                    "history": history,
                    "user_message": user_input,
                    "catalog": ", ".join(_MAIN_ACTIONS),
                },
                remaining_input_tokens=conversation.remaining_input_tokens,
                output_reserve_tokens=conversation.output_reserve_tokens,
                summarized=conversation.summarized,
                truncated=conversation.truncated,
            )
            assessment = _normalize_assessment(assessment_model.model_dump(), user_input, planning_context)
        except Exception as exc:
            parse_error = str(exc)
            self._tracer.record_error(span_id, exc)
            assessment = _fallback_assessment(user_input, planning_context, parse_error)
            record_decision(
                self._tracer,
                span_id,
                "PlannerAgent",
                "planning_assessment_parse_repair",
                user_input,
                "PlannerAgent no pudo obtener salida estructurada del LLM y reconstruye un assessment observable desde señales del runtime.",
                available_tools=list(_MAIN_ACTIONS),
                selected_tools=[assessment["preliminary_action"]] if assessment.get("preliminary_action") not in {None, "direct_answer"} else [],
                payload={
                    "output": output,
                    "parse_error": parse_error,
                    "assessment": assessment,
                    "hidden_reasoning": _hidden_reasoning(assessment),
                    "visibility": "hidden",
                },
            )
        record_decision(
            self._tracer,
            span_id,
            "PlannerAgent",
            "planning_assessment_response",
            user_input,
            "PlannerAgent recibe/normaliza el assessment inicial con razonamiento oculto estructurado.",
            available_tools=list(_MAIN_ACTIONS),
            payload={
                "assessment": assessment,
                "output": output,
                "parse_error": parse_error,
                "hidden_reasoning": _hidden_reasoning(assessment),
                "visibility": "hidden",
            },
        )
        return assessment

    def _run_decision(
        self,
        span_id: str,
        user_input: str,
        enriched_context: dict[str, Any],
        assessment: dict[str, Any],
        conversation: Any,
    ) -> dict[str, Any]:
        signals = enriched_context.get("derived_signals", {})
        history = str(enriched_context.get("conversation_history") or "(sin historial previo)")
        prompt = (
            f"Historial:\n{history}\n\n"
            f"Usuario: {user_input}\n"
            f"Acciones: {', '.join(_MAIN_ACTIONS)}\n"
            f"Señales: math={signals.get('math_expression')}, time={signals.get('asks_for_time')}\n"
            f"Preliminar: {assessment.get('preliminary_action')}\n"
            "Decisión final de planificación."
        )
        record_decision(
            self._tracer,
            span_id,
            "PlannerAgent",
            "planning_decision_request",
            user_input,
            "PlannerAgent vuelve a consultar al LLM con contexto enriquecido para obtener decisión final.",
            available_tools=["llm_planner"],
            selected_tools=["llm_planner"],
            payload={"prompt": prompt, "system": _PLANNER_SYSTEM},
        )
        parse_error = None
        output = ""
        tokens = TokenUsage(input=0, output=0)
        parsed: dict[str, Any] = {}
        plan: dict[str, Any] = {}
        try:
            decision_model, output, tokens = self._invoke_observed_structured_llm(
                span_id,
                prompt,
                _PLANNER_SYSTEM,
                "planner_decision",
                PlannerDecision,
                {
                    "system_prompt": _PLANNER_SYSTEM,
                    "history": history,
                    "user_message": user_input,
                    "catalog": ", ".join(_MAIN_ACTIONS),
                    "assessment": json.dumps(assessment, ensure_ascii=False),
                    "tools": json.dumps(enriched_context, ensure_ascii=False),
                },
                remaining_input_tokens=conversation.remaining_input_tokens,
                output_reserve_tokens=conversation.output_reserve_tokens,
                summarized=conversation.summarized,
                truncated=conversation.truncated,
            )
            parsed = decision_model.model_dump()
            plan = _plan_from_decision(parsed, user_input)
        except Exception as exc:
            parse_error = str(exc)
            self._tracer.record_error(span_id, exc)
            plan = _fallback_plan(user_input, parse_error)
            parsed = _decision_from_plan(plan, parse_error)
            record_decision(
                self._tracer,
                span_id,
                "PlannerAgent",
                "planning_decision_parse_repair",
                user_input,
                "PlannerAgent no pudo obtener salida estructurada del LLM y reconstruye un plan observable desde señales del runtime.",
                available_tools=list(_MAIN_ACTIONS),
                selected_tools=[] if plan["selected_action"] == "direct_answer" else [plan["selected_action"]],
                payload={
                    "output": output,
                    "parse_error": parse_error,
                    "decision": parsed,
                    "plan": plan,
                    "hidden_reasoning": _hidden_reasoning(plan),
                    "visibility": "hidden",
                },
            )
        record_decision(
            self._tracer,
            span_id,
            "PlannerAgent",
            "planning_decision_response",
            user_input,
            "PlannerAgent recibe/normaliza la decisión final con razonamiento oculto estructurado.",
            available_tools=list(_MAIN_ACTIONS),
            selected_tools=[] if plan["selected_action"] == "direct_answer" else [plan["selected_action"]],
            payload={
                "decision": parsed,
                "plan": plan,
                "output": output,
                "parse_error": parse_error,
                "hidden_reasoning": _hidden_reasoning(parsed),
                "visibility": "hidden",
            },
        )
        return plan

    def _invoke_observed_structured_llm(
        self,
        span_id: str,
        prompt: str,
        system: str,
        purpose: str,
        schema: type[PlannerAssessment] | type[PlannerDecision],
        components: dict[str, str],
        remaining_input_tokens: int | None = None,
        output_reserve_tokens: int | None = None,
        summarized: bool = False,
        truncated: bool = False,
    ) -> tuple[PlannerAssessment | PlannerDecision, str, TokenUsage]:
        started = utc_now()
        parsed, output, tokens = invoke_llm_structured(prompt, system=system, schema=schema, purpose=purpose)
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
        return parsed, output, tokens


def _planning_context(user_input: str, catalog: list[dict], conversation_history: str) -> dict[str, Any]:
    return {
        "user_input": user_input,
        "actions": [item["action"] for item in catalog],
        "conversation_history": conversation_history,
    }


def _normalize_assessment(
    assessment: dict[str, Any],
    user_input: str,
    planning_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        **assessment,
        "available_context": {"user_input": user_input, "actions": planning_context.get("actions", [])},
        "candidate_actions": assessment.get("candidate_actions", []),
        "missing_information": assessment.get("missing_information", []),
    }


def _enrich_context(planning_context: dict[str, Any], assessment: dict[str, Any]) -> dict[str, Any]:
    user_input = str(planning_context.get("user_input") or "")
    return {
        **planning_context,
        "assessment": assessment,
        "derived_signals": {
            "math_expression": _extract_math_expression(user_input),
            "asks_for_time": _asks_for_time(user_input),
            "candidate_actions_from_assessment": assessment.get("candidate_actions", []),
        },
    }


def _runtime_hidden_reasoning(enriched_context: dict[str, Any]) -> list[dict[str, Any]]:
    signals = enriched_context.get("derived_signals", {})
    reasoning = []
    if signals.get("math_expression"):
        reasoning.append(
            {
                "step": 1,
                "thought": "Se detecta una expresión matemática directa en la entrada.",
                "evidence": signals["math_expression"],
                "decision_impact": "Aumenta prioridad de math_agent.",
            }
        )
    if signals.get("asks_for_time"):
        reasoning.append(
            {
                "step": len(reasoning) + 1,
                "thought": "Se detecta una petición temporal directa.",
                "evidence": "keyword temporal en user_input",
                "decision_impact": "Aumenta prioridad de time_agent.",
            }
        )
    if not reasoning:
        reasoning.append(
            {
                "step": 1,
                "thought": "No se detectan señales deterministas de cálculo u hora; se mantiene evaluación del LLM planner.",
                "evidence": "derived_signals sin math_expression ni asks_for_time",
                "decision_impact": "Se conserva la decisión del planner salvo error estructural.",
            }
        )
    return reasoning


def _plan_from_decision(parsed: dict[str, Any], user_input: str) -> dict[str, Any]:
    selected_action = str(parsed.get("selected_action", "")).strip()
    if selected_action not in _MAIN_ACTIONS:
        raise ValueError(f"acción no soportada por planner: {selected_action}")

    arguments = _normalize_arguments(parsed.get("arguments"))
    if selected_action in {"math_agent", "time_agent", "direct_answer"}:
        arguments["task"] = user_input
    if selected_action == "researcher_agent" and not (arguments.get("topic") or arguments.get("task")):
        arguments["topic"] = user_input

    hidden_reasoning = _hidden_reasoning(parsed)
    return {
        "available_actions": list(_MAIN_ACTIONS),
        "evaluated_options": [],
        "candidate_actions": [],
        "selected_action": selected_action,
        "arguments": arguments,
        "confidence": parsed.get("confidence", 0.0),
        "rationale": str(parsed.get("rationale") or "El planner seleccionó la acción indicada."),
        "task_understanding": parsed.get("task_understanding"),
        "hidden_reasoning": hidden_reasoning,
        "decision_status": "final",
        "missing_information": [],
    }


def _normalize_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _fallback_assessment(user_input: str, planning_context: dict[str, Any], parse_error: str) -> dict[str, Any]:
    expression = _extract_math_expression(user_input)
    asks_time = _asks_for_time(user_input)
    if expression:
        preliminary_action = "math_agent"
        candidate_actions = [
            {"action": "math_agent", "applicable": True, "reason": f"Se detectó expresión aritmética: {expression}."},
            {"action": "time_agent", "applicable": False, "reason": "No hay petición temporal."},
            {"action": "researcher_agent", "applicable": False, "reason": "No requiere investigación."},
            {"action": "direct_answer", "applicable": False, "reason": "Existe subagente de dominio más específico."},
        ]
        confidence = 0.9
    elif asks_time:
        preliminary_action = "time_agent"
        candidate_actions = [
            {"action": "math_agent", "applicable": False, "reason": "No hay expresión aritmética."},
            {"action": "time_agent", "applicable": True, "reason": "Se detectó una petición de hora/fecha actual."},
            {"action": "researcher_agent", "applicable": False, "reason": "No requiere investigación."},
            {"action": "direct_answer", "applicable": False, "reason": "Existe subagente temporal más específico."},
        ]
        confidence = 0.9
    else:
        preliminary_action = "direct_answer"
        candidate_actions = [{"action": action, "applicable": action == "direct_answer", "reason": "Assessment reparado sin señal de dominio inequívoca."} for action in _MAIN_ACTIONS]
        confidence = 0.2

    return {
        "task_understanding": f"Assessment reparado para: {user_input}",
        "available_context": {
            "user_input": user_input,
            "catalog_seen": bool(planning_context.get("actions")),
            "parse_error": parse_error,
        },
        "candidate_actions": candidate_actions,
        "hidden_reasoning": [
            {
                "step": 1,
                "thought": "El proveedor no devolvió salida estructurada válida para el assessment.",
                "evidence": parse_error,
                "decision_impact": "Activar reparación observable en PlannerAgent.",
            },
            {
                "step": 2,
                "thought": "Se evalúan señales deterministas del runtime sin que MainAgent ejecute tools de dominio.",
                "evidence": f"math_expression={expression!r}, asks_for_time={asks_time}",
                "decision_impact": f"Preseleccionar {preliminary_action}.",
            },
        ],
        "missing_information": [],
        "decision_status": "ready",
        "preliminary_action": preliminary_action,
        "confidence": confidence,
    }


def _fallback_plan(text: str, parse_error: str | None = None) -> dict[str, Any]:
    expression = _extract_math_expression(text)
    asks_time = _asks_for_time(text)
    if expression:
        selected_action = "math_agent"
        arguments = {"task": text}
        reason = f"Se detectó una expresión aritmética inequívoca: {expression}."
        confidence = 0.9
    elif asks_time:
        selected_action = "time_agent"
        arguments = {"task": text}
        reason = "Se detectó una petición inequívoca de hora/fecha actual."
        confidence = 0.9
    else:
        selected_action = "direct_answer"
        arguments = {"task": text}
        reason = "No se detectó señal de dominio inequívoca para subagente."
        confidence = 0.2

    hidden_reasoning = [
        {
            "step": 1,
            "thought": "El proveedor no devolvió salida estructurada válida; se usa reparación observable.",
            "evidence": parse_error or "excepción al parsear JSON o acción no soportada",
            "decision_impact": "Evitar una ejecución contradictoria y seleccionar la acción más segura según señales del runtime.",
        },
        {
            "step": 2,
            "thought": "La reparación mantiene a MainAgent fuera del dominio: solo selecciona subagente o respuesta directa.",
            "evidence": reason,
            "decision_impact": f"Seleccionar {selected_action}.",
        }
    ]
    return {
        "available_actions": list(_MAIN_ACTIONS),
        "evaluated_options": [{"action": action, "applicable": action == selected_action, "reason": reason if action == selected_action else "No seleccionado por reparación observable."} for action in _MAIN_ACTIONS],
        "candidate_actions": [{"action": action, "applicable": action == selected_action, "reason": reason if action == selected_action else "No seleccionado por reparación observable."} for action in _MAIN_ACTIONS],
        "selected_action": selected_action,
        "arguments": arguments,
        "confidence": confidence,
        "rationale": f"PlannerAgent reparó la decisión final tras un fallo de parseo/contrato: {reason}",
        "hidden_reasoning": hidden_reasoning,
        "decision_status": "final",
        "missing_information": [],
    }


def _decision_from_plan(plan: dict[str, Any], parse_error: str | None) -> dict[str, Any]:
    return {
        "task_understanding": plan.get("task_understanding") or "Decisión reparada desde señales del runtime.",
        "available_context": {"parse_error": parse_error},
        "candidate_actions": plan.get("candidate_actions", []),
        "hidden_reasoning": plan.get("hidden_reasoning", []),
        "missing_information": plan.get("missing_information", []),
        "decision_status": plan.get("decision_status", "final"),
        "selected_action": plan.get("selected_action"),
        "arguments": plan.get("arguments", {}),
        "confidence": plan.get("confidence", 0.0),
        "rationale": plan.get("rationale", ""),
    }


def _validate_or_repair_plan(plan: dict[str, Any], user_input: str) -> dict[str, Any]:
    expression = _extract_math_expression(user_input)
    asks_time = _asks_for_time(user_input)

    if expression and plan.get("selected_action") != "math_agent":
        hidden_reasoning = _hidden_reasoning(plan) + [
            {
                "step": len(_hidden_reasoning(plan)) + 1,
                "thought": "La decisión del LLM contradice una señal matemática inequívoca.",
                "evidence": expression,
                "decision_impact": "Reparar selected_action a math_agent.",
            }
        ]
        return {
            **plan,
            "selected_action": "math_agent",
            "arguments": {"task": user_input},
            "confidence": max(_safe_confidence(plan.get("confidence")), 0.9),
            "rationale": (
                "PlannerAgent validó que la entrada contiene una operación aritmética inequívoca "
                f"({expression}) y seleccionó MathAgent."
            ),
            "hidden_reasoning": hidden_reasoning,
        }

    if not expression and asks_time and plan.get("selected_action") != "time_agent":
        hidden_reasoning = _hidden_reasoning(plan) + [
            {
                "step": len(_hidden_reasoning(plan)) + 1,
                "thought": "La decisión del LLM contradice una petición temporal inequívoca.",
                "evidence": "keyword temporal en user_input",
                "decision_impact": "Reparar selected_action a time_agent.",
            }
        ]
        return {
            **plan,
            "selected_action": "time_agent",
            "arguments": {"task": user_input},
            "confidence": max(_safe_confidence(plan.get("confidence")), 0.9),
            "rationale": "PlannerAgent validó que la entrada solicita hora/fecha actual y seleccionó TimeAgent.",
            "hidden_reasoning": hidden_reasoning,
        }

    selected_action = plan.get("selected_action")
    if selected_action == "math_agent" and not expression:
        return _repair_invalid_subagent_selection(
            plan,
            user_input,
            from_action="math_agent",
            evidence="derived_signals sin math_expression",
            rationale=(
                "PlannerAgent rechazó math_agent porque la entrada no contiene una expresión "
                "aritmética inequívoca; se usará respuesta directa."
            ),
        )

    if selected_action == "time_agent" and not asks_time:
        return _repair_invalid_subagent_selection(
            plan,
            user_input,
            from_action="time_agent",
            evidence="derived_signals sin asks_for_time",
            rationale=(
                "PlannerAgent rechazó time_agent porque la entrada no solicita hora/fecha actual; "
                "se usará respuesta directa."
            ),
        )

    return plan


def _repair_invalid_subagent_selection(
    plan: dict[str, Any],
    user_input: str,
    from_action: str,
    evidence: str,
    rationale: str,
) -> dict[str, Any]:
    hidden_reasoning = _hidden_reasoning(plan) + [
        {
            "step": len(_hidden_reasoning(plan)) + 1,
            "thought": f"La decisión del LLM seleccionó {from_action} sin señal determinista de dominio.",
            "evidence": evidence,
            "decision_impact": "Reparar selected_action a direct_answer.",
        }
    ]
    return {
        **plan,
        "selected_action": "direct_answer",
        "arguments": {"task": user_input},
        "confidence": min(_safe_confidence(plan.get("confidence")), 0.3),
        "rationale": rationale,
        "hidden_reasoning": hidden_reasoning,
    }


def _combine_hidden_reasoning(assessment: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    combined = _hidden_reasoning(assessment) + _hidden_reasoning(plan)
    return [{**step, "step": index} for index, step in enumerate(combined, start=1)]


def _hidden_reasoning(value: dict[str, Any]) -> list[dict[str, Any]]:
    reasoning = value.get("hidden_reasoning")
    if not isinstance(reasoning, list):
        return []
    normalized = []
    for index, item in enumerate(reasoning, start=1):
        if isinstance(item, dict):
            normalized.append(
                {
                    "step": item.get("step", index),
                    "thought": str(item.get("thought", "")),
                    "evidence": str(item.get("evidence", "")),
                    "decision_impact": str(item.get("decision_impact", "")),
                }
            )
    return normalized


def _extract_math_expression(text: str) -> str | None:
    match = _MATH_EXPRESSION.search(text)
    if match:
        return match.group(1).strip()
    compact = text.strip().strip("¿?¡! ")
    if re.fullmatch(r"[0-9.\s+\-*/()]+", compact):
        return compact
    return None


def _asks_for_time(text: str) -> bool:
    normalized = text.casefold()
    return any(keyword in normalized for keyword in _TIME_KEYWORDS)


def _safe_confidence(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
