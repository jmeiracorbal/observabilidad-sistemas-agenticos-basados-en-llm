# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

from contextvars import ContextVar, Token
from typing import Any, Callable

RunEventEmitter = Callable[[str, dict[str, Any]], None]

_emitter: ContextVar[RunEventEmitter | None] = ContextVar("run_event_emitter", default=None)


def set_run_event_emitter(emitter: RunEventEmitter | None) -> Token:
    return _emitter.set(emitter)


def reset_run_event_emitter(token: Token) -> None:
    _emitter.reset(token)


def emit_run_event(event_type: str, data: dict[str, Any]) -> None:
    emitter = _emitter.get()
    if emitter is None:
        return
    emitter(event_type, data)
