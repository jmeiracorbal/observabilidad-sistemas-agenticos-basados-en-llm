# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import json
from typing import Any, Literal

from pydantic import BaseModel, field_validator


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            raise ValueError("valor no convertible a dict")
        return parsed
    raise ValueError("valor no convertible a dict")


def _coerce_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        parsed = json.loads(stripped)
        if not isinstance(parsed, list):
            raise ValueError("valor no convertible a list")
        return parsed
    raise ValueError("valor no convertible a list")


def _coerce_list_lenient(value: Any) -> list[Any]:
    if value is None:
        return []
    try:
        return _coerce_list(value)
    except (ValueError, json.JSONDecodeError):
        return []


class HiddenReasoningStep(BaseModel):
    step: int = 1
    thought: str = ""
    evidence: str = ""
    decision_impact: str = ""


class PlannerAssessment(BaseModel):
    task_understanding: str = ""
    hidden_reasoning: list[HiddenReasoningStep] = []
    decision_status: Literal["needs_more_context", "ready"] = "ready"
    preliminary_action: Literal["math_agent", "time_agent", "researcher_agent", "direct_answer"] | None = None
    confidence: float = 0.0

    @field_validator("hidden_reasoning", mode="before")
    @classmethod
    def validate_hidden_reasoning(cls, value: Any) -> list[Any]:
        return _coerce_list_lenient(value)


class PlannerDecision(BaseModel):
    selected_action: Literal["math_agent", "time_agent", "researcher_agent", "direct_answer"]
    arguments: dict[str, Any] = {}
    hidden_reasoning: list[HiddenReasoningStep] = []
    rationale: str = ""
    confidence: float = 0.0

    @field_validator("hidden_reasoning", mode="before")
    @classmethod
    def validate_hidden_reasoning(cls, value: Any) -> list[Any]:
        return _coerce_list_lenient(value)

    @field_validator("arguments", mode="before")
    @classmethod
    def validate_arguments(cls, value: Any) -> dict[str, Any]:
        return _coerce_dict(value)
