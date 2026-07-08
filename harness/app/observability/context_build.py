# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import os
from typing import Any

COMPONENT_LABELS: dict[str, str] = {
    "system_prompt": "System prompt",
    "user_message": "Mensaje usuario",
    "catalog": "Catálogo / acciones",
    "memory": "Memoria",
    "rag": "RAG / búsqueda",
    "tools": "Herramientas",
    "history": "Historial / contexto previo",
    "assessment": "Assessment planner",
    "observation": "Observación subagente",
    "document": "Documento local",
}


def context_window_size() -> int:
    return int(os.environ["LLM_CONTEXT_WINDOW"])


def allocate_token_breakdown(components: dict[str, str], input_tokens: int) -> dict[str, int]:
    non_empty = {key: value for key, value in components.items() if value}
    if not non_empty:
        return {}
    if input_tokens <= 0:
        return {key: 0 for key in non_empty}

    weights = {key: len(text) for key, text in non_empty.items()}
    total_weight = sum(weights.values())
    if total_weight == 0:
        even = input_tokens // len(non_empty)
        breakdown = {key: even for key in non_empty}
        breakdown[next(iter(non_empty))] += input_tokens - sum(breakdown.values())
        return breakdown

    breakdown = {key: int(input_tokens * weight / total_weight) for key, weight in weights.items()}
    remainder = input_tokens - sum(breakdown.values())
    if remainder:
        largest = max(weights, key=weights.get)
        breakdown[largest] += remainder
    return breakdown


def build_context_metadata(
    *,
    components: dict[str, str],
    input_tokens: int,
    output_tokens: int,
    remaining_input_tokens: int | None = None,
    output_reserve_tokens: int | None = None,
    summarized: bool = False,
    truncated: bool = False,
    request_index: int | None = None,
) -> dict[str, Any]:
    breakdown = allocate_token_breakdown(components, input_tokens)
    window = context_window_size()
    return {
        "breakdown": breakdown,
        "breakdown_labels": {key: COMPONENT_LABELS.get(key, key) for key in breakdown},
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "context_window": window,
        "window_usage_pct": round(100 * input_tokens / window, 2) if window else 0.0,
        "remaining_input_tokens": remaining_input_tokens,
        "output_reserve_tokens": output_reserve_tokens,
        "summarized": summarized,
        "truncated": truncated,
        "request_index": request_index,
    }
