# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import os
from dataclasses import dataclass

from conversation.service import estimate_text_tokens


@dataclass
class ContextWindowResult:
    history_text: str
    remaining_input_tokens: int
    output_reserve_tokens: int
    summarized: bool
    truncated: bool
    removed_message_ids: list[int]
    summary_text: str
    estimated_input_tokens: int


def context_window_size() -> int:
    return int(os.environ["LLM_CONTEXT_WINDOW"])


def output_token_reserve() -> int:
    return int(os.environ["LLM_OUTPUT_TOKEN_RESERVE"])


def apply_context_window_policy(
    *,
    messages: list[dict],
    system_prompt: str,
    user_message: str,
    extra_components: list[str],
) -> ContextWindowResult:
    window = context_window_size()
    reserve = output_token_reserve()
    preserved_tail = 4
    removed_message_ids: list[int] = []
    summary_text = ""
    summarized = False
    truncated = False

    working_messages = list(messages)

    def serialize(items: list[dict]) -> str:
        parts: list[str] = []
        for item in items:
            role = str(item["role"]).upper()
            content = str(item["content"])
            parts.append(f"{role}\n{content}")
        return "\n\n".join(parts)

    def estimated_input(history_text: str) -> int:
        total = estimate_text_tokens(system_prompt) + estimate_text_tokens(user_message)
        total += estimate_text_tokens(history_text)
        total += sum(estimate_text_tokens(component) for component in extra_components if component)
        return total

    history_text = serialize(working_messages)
    current_input = estimated_input(history_text)

    if current_input + reserve <= window:
        return ContextWindowResult(
            history_text=history_text,
            remaining_input_tokens=max(0, window - reserve - current_input),
            output_reserve_tokens=reserve,
            summarized=False,
            truncated=False,
            removed_message_ids=[],
            summary_text="",
            estimated_input_tokens=current_input,
        )

    if len(working_messages) > preserved_tail:
        head = working_messages[:-preserved_tail]
        tail = working_messages[-preserved_tail:]
        summary_lines = []
        for item in head:
            role = str(item["role"]).upper()
            compact = " ".join(str(item["content"]).split())
            summary_lines.append(f"{role}: {compact[:160]}")
            if item.get("id") is not None:
                removed_message_ids.append(int(item["id"]))
        summary_text = "Resumen conversacional previo:\n" + "\n".join(summary_lines)
        working_messages = [{"role": "summary", "content": summary_text}] + tail
        summarized = True
        history_text = serialize(working_messages)
        current_input = estimated_input(history_text)

    if current_input + reserve > window:
        while current_input + reserve > window and len(working_messages) > 1:
            removed = working_messages.pop(0)
            if removed.get("id") is not None:
                removed_message_ids.append(int(removed["id"]))
            truncated = True
            history_text = serialize(working_messages)
            current_input = estimated_input(history_text)

    return ContextWindowResult(
        history_text=history_text,
        remaining_input_tokens=max(0, window - reserve - current_input),
        output_reserve_tokens=reserve,
        summarized=summarized,
        truncated=truncated,
        removed_message_ids=removed_message_ids,
        summary_text=summary_text,
        estimated_input_tokens=current_input,
    )
