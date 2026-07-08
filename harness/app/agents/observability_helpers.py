# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

from datetime import datetime, timezone
from typing import Any

from observability.tracer import Tracer


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def record_decision(
    tracer: Tracer,
    span_id: str,
    actor: str,
    stage: str,
    input_text: str,
    rationale: str,
    available_tools: list[str] | None = None,
    selected_tools: list[str] | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    event_time = utc_now()
    tracer.record_decision_event(
        span_id,
        {
            "actor": actor,
            "stage": stage,
            "input": input_text,
            "available_tools": available_tools or [],
            "selected_tools": selected_tools or [],
            "rationale": rationale,
            "payload": payload or {},
            "started_at": event_time,
            "ended_at": event_time,
        },
    )


def record_autorepair_flow(
    tracer: Tracer,
    span_id: str,
    actor: str,
    user_input: str,
    *,
    phase: str,
    conflict_type: str,
    evidence: str,
    from_value: str,
    to_value: str,
    before: dict[str, Any],
    after: dict[str, Any],
    rationale: str,
    available_tools: list[str] | None = None,
    selected_tools: list[str] | None = None,
) -> None:
    base = {"phase": phase, "visibility": "public"}
    record_decision(
        tracer,
        span_id,
        actor,
        "autorepair_conflict_detected",
        user_input,
        f"Se detecta un conflicto en {phase}: {conflict_type}.",
        available_tools=available_tools,
        selected_tools=selected_tools,
        payload={
            **base,
            "conflict_type": conflict_type,
            "evidence": evidence,
            "from_value": from_value,
            "to_value": to_value,
            "before": before,
        },
    )
    record_decision(
        tracer,
        span_id,
        actor,
        "autorepair_decision",
        user_input,
        f"{actor} decide aplicar autoreparación determinista.",
        available_tools=available_tools,
        selected_tools=selected_tools,
        payload={
            **base,
            "strategy": "deterministic_override",
            "conflict_type": conflict_type,
            "from_value": from_value,
            "to_value": to_value,
            "rationale": rationale,
        },
    )
    record_decision(
        tracer,
        span_id,
        actor,
        "autorepair_applied",
        user_input,
        f"Autoreparación aplicada en {phase}: {from_value} → {to_value}.",
        available_tools=available_tools,
        selected_tools=selected_tools,
        payload={
            **base,
            "conflict_type": conflict_type,
            "from_value": from_value,
            "to_value": to_value,
            "before": before,
            "after": after,
            "result": after,
        },
    )


def record_retry_flow(
    tracer: Tracer,
    span_id: str,
    actor: str,
    user_input: str,
    *,
    phase: str,
    violation_type: str,
    evidence: str,
    from_value: str,
    attempt: int,
    max_attempts: int,
    next_attempt: int,
    rationale: str,
    before: dict[str, Any],
    after: dict[str, Any],
    available_tools: list[str] | None = None,
    selected_tools: list[str] | None = None,
) -> None:
    base = {
        "phase": phase,
        "visibility": "public",
        "attempt": attempt,
        "max_attempts": max_attempts,
        "next_attempt": next_attempt,
    }
    record_decision(
        tracer,
        span_id,
        actor,
        "retry_conflict_detected",
        user_input,
        f"La salida no cumple el contrato en {phase}: {violation_type}.",
        available_tools=available_tools,
        selected_tools=selected_tools,
        payload={
            **base,
            "violation_type": violation_type,
            "evidence": evidence,
            "from_value": from_value,
            "before": before,
        },
    )
    record_decision(
        tracer,
        span_id,
        actor,
        "retry_decision",
        user_input,
        f"{actor} decide reintentar la respuesta con prompt correctivo.",
        available_tools=available_tools,
        selected_tools=selected_tools,
        payload={
            **base,
            "strategy": "llm_corrective_prompt",
            "violation_type": violation_type,
            "from_value": from_value,
            "rationale": rationale,
        },
    )
    record_decision(
        tracer,
        span_id,
        actor,
        "retry_applied",
        user_input,
        f"Reintento {next_attempt}/{max_attempts} programado en {phase}.",
        available_tools=available_tools,
        selected_tools=selected_tools,
        payload={
            **base,
            "violation_type": violation_type,
            "from_value": from_value,
            "before": before,
            "after": after,
        },
    )
