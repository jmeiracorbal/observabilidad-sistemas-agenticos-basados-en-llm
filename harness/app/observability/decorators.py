# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

from contextlib import contextmanager
from typing import Iterator

from observability.context import get_current_span, reset_current_span, set_current_span
from observability.models import Span, SpanType
from observability.tracer import Tracer


@contextmanager
def span(
    tracer: Tracer,
    run_id: str,
    name: str,
    span_type: SpanType,
    parent_span_id: str | None = None,
) -> Iterator[Span]:
    current = get_current_span()
    resolved_parent = parent_span_id if parent_span_id is not None else (current.id if current else None)
    opened = tracer.start_span(run_id, name, span_type, resolved_parent)
    token = set_current_span(opened)
    try:
        yield opened
        tracer.end_span(opened.id, "completed")
    except Exception as exc:
        tracer.record_error(opened.id, exc)
        tracer.end_span(opened.id, "failed")
        raise
    finally:
        reset_current_span(token)
