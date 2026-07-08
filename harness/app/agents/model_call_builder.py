# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

from datetime import datetime
from typing import Any

from observability.context_build import build_context_metadata


def build_model_call_record(
    *,
    model: str,
    system: str,
    prompt: str,
    output: str,
    input_tokens: int,
    output_tokens: int,
    purpose: str,
    components: dict[str, str],
    started_at: datetime,
    ended_at: datetime,
    remaining_input_tokens: int | None = None,
    output_reserve_tokens: int | None = None,
    summarized: bool = False,
    truncated: bool = False,
    request_index: int | None = None,
) -> dict[str, Any]:
    return {
        "model": model,
        "input": f"SYSTEM:\n{system}\n\nUSER:\n{prompt}" if system else prompt,
        "output": output,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "purpose": purpose,
        "started_at": started_at,
        "ended_at": ended_at,
        "context_metadata": build_context_metadata(
            components=components,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            remaining_input_tokens=remaining_input_tokens,
            output_reserve_tokens=output_reserve_tokens,
            summarized=summarized,
            truncated=truncated,
            request_index=request_index,
        ),
    }
