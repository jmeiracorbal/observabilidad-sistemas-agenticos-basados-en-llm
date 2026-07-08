# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import os
import uuid
from typing import Any

import httpx


def estimate_text_tokens(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, round(len(stripped) / 4))


class ConversationService:
    def __init__(self) -> None:
        self._base_url = os.environ["OBSERVABILITY_API_URL"]

    def _get(self, path: str) -> Any:
        response = httpx.get(f"{self._base_url}{path}", timeout=10.0)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        response = httpx.post(f"{self._base_url}{path}", json=payload, timeout=10.0)
        response.raise_for_status()
        return response.json()

    def ensure_conversation(self, conversation_id: str | None) -> str:
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())
        self._post("/conversations", {"id": conversation_id, "status": "active"})
        return conversation_id

    def list_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        return list(self._get(f"/conversations/{conversation_id}/messages"))

    def next_turn_index(self, conversation_id: str) -> int:
        messages = self.list_messages(conversation_id)
        if not messages:
            return 1
        return max(int(message["turn_index"]) for message in messages) + 1

    def append_message(
        self,
        *,
        conversation_id: str,
        run_id: str | None,
        turn_index: int,
        role: str,
        kind: str,
        content: str,
    ) -> None:
        self._post(
            "/conversation_messages",
            {
                "conversation_id": conversation_id,
                "run_id": run_id,
                "turn_index": turn_index,
                "role": role,
                "kind": kind,
                "content": content,
                "token_count": estimate_text_tokens(content),
            },
        )

    def delete_messages(self, ids: list[int]) -> None:
        self._post("/conversation_messages/delete", {"ids": ids})
