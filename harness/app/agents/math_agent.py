# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import re

from observability.decorators import span
from observability.tracer import Tracer
from tools.calculator import calculator

from agents.observability_helpers import record_decision, utc_now

_MATH_TOOLS = ("calculator",)
_MATH_EXPRESSION = re.compile(
    r"(?<!\w)(\d+(?:\.\d+)?(?:\s*(?:[-+*/]|\*\*)\s*\d+(?:\.\d+)?)+)(?!\w)"
)


class MathAgent:
    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def run(self, run_id: str, task: str, parent_span_id: str) -> dict:
        with span(self._tracer, run_id, "math_agent", "agent", parent_span_id) as math_span:
            record_decision(
                self._tracer,
                math_span.id,
                "MathAgent",
                "subagent_received",
                task,
                "MathAgent recibe una tarea matemática delegada por MainAgent.",
                payload={"task": task},
            )
            record_decision(
                self._tracer,
                math_span.id,
                "MathAgent",
                "tool_catalog_read",
                task,
                "MathAgent consulta su catálogo propio de herramientas matemáticas.",
                available_tools=list(_MATH_TOOLS),
            )

            expression = _extract_expression(task)
            record_decision(
                self._tracer,
                math_span.id,
                "MathAgent",
                "tool_selection",
                task,
                "MathAgent interpreta la tarea delegada, extrae la expresión matemática y selecciona calculator.",
                available_tools=list(_MATH_TOOLS),
                selected_tools=["calculator"],
                payload={"task": task, "selected_tool": "calculator", "arguments": {"expression": expression}},
            )
            record_decision(
                self._tracer,
                math_span.id,
                "MathAgent",
                "tool_call_request",
                task,
                f"MathAgent solicita ejecutar calculator con expression={expression!r}.",
                available_tools=list(_MATH_TOOLS),
                selected_tools=["calculator"],
                payload={"tool_name": "calculator", "arguments": {"expression": expression}},
            )
            started = utc_now()
            result = calculator(expression)
            ended = utc_now()
            self._tracer.record_tool_call(
                math_span.id,
                {
                    "tool_name": "calculator",
                    "arguments": {"expression": expression},
                    "result": result,
                    "owner_agent": "MathAgent",
                    "purpose": "calculator_execution",
                    "started_at": started,
                    "ended_at": ended,
                },
            )
            observation = {
                "type": "tool_result",
                "owner_agent": "MathAgent",
                "tool": "calculator",
                "arguments": {"task": task, "expression": expression},
                "result": result,
            }
            record_decision(
                self._tracer,
                math_span.id,
                "MathAgent",
                "tool_observation",
                task,
                f"calculator devolvió {result}; MathAgent normaliza la observación y la devuelve a MainAgent.",
                available_tools=["calculator"],
                payload=observation,
            )
            return observation


def _extract_expression(task: str) -> str:
    match = _MATH_EXPRESSION.search(task)
    if match:
        return match.group(1).strip()

    compact = task.strip().strip("¿?¡! ")
    if re.fullmatch(r"[0-9.\s+\-*/()]+", compact):
        return compact

    raise ValueError(f"MathAgent no pudo extraer una expresión matemática de la tarea: {task}")
