# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

from contextvars import ContextVar, Token

from observability.models import Span

_current_span: ContextVar[Span | None] = ContextVar("current_span", default=None)


def get_current_span() -> Span | None:
    return _current_span.get()


def set_current_span(span: Span | None) -> Token:
    return _current_span.set(span)


def reset_current_span(token: Token) -> None:
    _current_span.reset(token)
