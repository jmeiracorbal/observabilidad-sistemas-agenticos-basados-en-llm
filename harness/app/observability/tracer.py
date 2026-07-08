# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import os
import json
import uuid
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

import httpx

from observability.context import get_current_span
from observability.models import (
    DecisionEvent,
    ErrorEvent,
    MemoryEvent,
    ModelCall,
    Run,
    RunStatus,
    Span,
    SpanStatus,
    SpanType,
    ToolCall,
)


class Tracer:
    def __init__(self) -> None:
        self._base_url = os.environ["OBSERVABILITY_API_URL"]

    def _post(self, path: str, payload: dict) -> None:
        response = httpx.post(f"{self._base_url}{path}", json=payload, timeout=5.0)
        response.raise_for_status()

    def _resolve_run_id(self, parent_span_id: str) -> str:
        current = get_current_span()
        if current is None:
            raise ValueError("no hay span activo en contexto para crear span hijo")
        if current.id != parent_span_id:
            raise ValueError(f"span activo {current.id} no coincide con parent_span_id {parent_span_id}")
        return current.run_id

    @contextmanager
    def _execution_span(
        self,
        parent_span_id: str,
        span_type: SpanType,
        name: str,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> Iterator[str]:
        run_id = self._resolve_run_id(parent_span_id)
        opened = self.start_span(run_id, name, span_type, parent_span_id, started_at=started_at)
        try:
            yield opened.id
            self.end_span(opened.id, "completed", ended_at=ended_at)
        except Exception as exc:
            self.record_error(opened.id, exc)
            self.end_span(opened.id, "failed", ended_at=ended_at)
            raise

    def start_run(self, input_text: str, conversation_id: str, turn_index: int) -> Run:
        run = Run(
            id=str(uuid.uuid4()),
            input=input_text,
            conversation_id=conversation_id,
            turn_index=turn_index,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self._post("/runs", run.model_dump(mode="json"))
        return run

    def end_run(self, run_id: str, status: RunStatus) -> None:
        self._post(f"/runs/{run_id}/end", {"status": status})

    def start_span(
        self,
        run_id: str,
        name: str,
        span_type: SpanType,
        parent_span_id: str | None = None,
        started_at: datetime | None = None,
    ) -> Span:
        span = Span(
            id=str(uuid.uuid4()),
            run_id=run_id,
            parent_span_id=parent_span_id,
            type=span_type,
            name=name,
            status="running",
            started_at=started_at or datetime.now(timezone.utc),
        )
        self._post("/spans", span.model_dump(mode="json"))
        return span

    def end_span(self, span_id: str, status: SpanStatus, ended_at: datetime | None = None) -> None:
        payload: dict[str, Any] = {"status": status}
        if ended_at is not None:
            payload["ended_at"] = ended_at.isoformat()
        self._post(f"/spans/{span_id}/end", payload)

    def record_model_call(self, parent_span_id: str, data: dict) -> None:
        purpose = data["purpose"]
        with self._execution_span(
            parent_span_id,
            "model",
            f"llm:{purpose}",
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
        ) as execution_span_id:
            model_call = ModelCall(span_id=execution_span_id, **data)
            self._post("/model_calls", model_call.model_dump(mode="json"))

    def record_tool_call(self, parent_span_id: str, data: dict) -> None:
        tool_name = data["tool_name"]
        normalized = {**data, "result": _stringify_result(data.get("result", ""))}
        with self._execution_span(
            parent_span_id,
            "tool",
            f"tool:{tool_name}",
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
        ) as execution_span_id:
            tool_call = ToolCall(span_id=execution_span_id, **normalized)
            self._post("/tool_calls", tool_call.model_dump(mode="json"))

    def record_memory_event(self, parent_span_id: str, data: dict) -> None:
        operation = data["operation"]
        with self._execution_span(
            parent_span_id,
            "memory",
            f"memory:{operation}",
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
        ) as execution_span_id:
            memory_event = MemoryEvent(span_id=execution_span_id, **data)
            self._post("/memory_events", memory_event.model_dump(mode="json"))

    def record_decision_event(self, span_id: str, data: dict) -> None:
        decision_event = DecisionEvent(span_id=span_id, **data)
        self._post("/decision_events", decision_event.model_dump(mode="json"))

    def record_error(self, span_id: str, error: Exception) -> None:
        error_event = ErrorEvent(
            span_id=span_id,
            error_type=type(error).__name__,
            message=str(error),
        )
        self._post("/errors", error_event.model_dump(mode="json"))


def _stringify_result(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)
