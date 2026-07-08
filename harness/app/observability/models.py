# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

SpanType = Literal["agent", "tool", "memory", "model"]
RunStatus = Literal["running", "completed", "failed"]
SpanStatus = Literal["running", "completed", "failed"]


class TokenUsage(BaseModel):
    input: int
    output: int


class Run(BaseModel):
    id: str
    input: str
    conversation_id: str
    turn_index: int
    status: RunStatus
    started_at: datetime
    ended_at: Optional[datetime] = None


class Span(BaseModel):
    id: str
    run_id: str
    parent_span_id: Optional[str] = None
    type: SpanType
    name: str
    status: SpanStatus
    started_at: datetime
    ended_at: Optional[datetime] = None


class ModelCall(BaseModel):
    span_id: str
    model: str
    input: str
    output: str
    input_tokens: int
    output_tokens: int
    purpose: Optional[str] = None
    context_metadata: Optional[dict] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class ToolCall(BaseModel):
    span_id: str
    tool_name: str
    arguments: dict
    result: str
    owner_agent: Optional[str] = None
    purpose: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class MemoryEvent(BaseModel):
    span_id: str
    operation: str
    query: str
    results_count: int
    owner_agent: Optional[str] = None
    purpose: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class DecisionEvent(BaseModel):
    span_id: str
    actor: str
    stage: str
    input: str
    available_tools: list[str]
    selected_tools: list[str]
    rationale: str
    payload: dict = {}
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class ErrorEvent(BaseModel):
    span_id: str
    error_type: str
    message: str
