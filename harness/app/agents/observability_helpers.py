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
