# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

from datetime import datetime, timezone

from memory.store import MemoryStore
from observability.tracer import Tracer

_store = MemoryStore()


def search_memory(tracer: Tracer, span_id: str, query: str, limit: int = 5, owner_agent: str | None = None, purpose: str | None = None) -> list[str]:
    started_at = datetime.now(timezone.utc)
    results = _store.search(query, limit)
    ended_at = datetime.now(timezone.utc)
    tracer.record_memory_event(
        span_id,
        {
            "operation": "search",
            "query": query,
            "results_count": len(results),
            "owner_agent": owner_agent,
            "purpose": purpose,
            "started_at": started_at,
            "ended_at": ended_at,
        },
    )
    return results


def save_memory(tracer: Tracer, span_id: str, title: str, content: str, owner_agent: str | None = None, purpose: str | None = None) -> None:
    started_at = datetime.now(timezone.utc)
    _store.save(title, content)
    ended_at = datetime.now(timezone.utc)
    tracer.record_memory_event(
        span_id,
        {
            "operation": "save",
            "query": title,
            "results_count": 1,
            "owner_agent": owner_agent,
            "purpose": purpose,
            "started_at": started_at,
            "ended_at": ended_at,
        },
    )
