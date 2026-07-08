# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

from observability.decorators import span
from observability.tracer import Tracer
from tools.clock import clock

from agents.observability_helpers import record_decision, utc_now

_TIME_TOOLS = ("clock",)


class TimeAgent:
    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def run(self, run_id: str, task: str, parent_span_id: str) -> dict:
        with span(self._tracer, run_id, "time_agent", "agent", parent_span_id) as time_span:
            record_decision(
                self._tracer,
                time_span.id,
                "TimeAgent",
                "subagent_received",
                task,
                "TimeAgent recibe una tarea temporal delegada por MainAgent.",
                payload={"task": task},
            )
            record_decision(
                self._tracer,
                time_span.id,
                "TimeAgent",
                "tool_catalog_read",
                task,
                "TimeAgent consulta su catálogo propio de herramientas de tiempo.",
                available_tools=list(_TIME_TOOLS),
            )
            record_decision(
                self._tracer,
                time_span.id,
                "TimeAgent",
                "tool_selection",
                task,
                "TimeAgent interpreta la tarea delegada y selecciona clock como herramienta temporal.",
                available_tools=list(_TIME_TOOLS),
                selected_tools=["clock"],
                payload={"task": task, "selected_tool": "clock", "arguments": {}},
            )
            record_decision(
                self._tracer,
                time_span.id,
                "TimeAgent",
                "tool_call_request",
                task,
                "TimeAgent solicita ejecutar clock para obtener la hora UTC.",
                available_tools=list(_TIME_TOOLS),
                selected_tools=["clock"],
                payload={"tool_name": "clock", "arguments": {}},
            )
            started = utc_now()
            result = clock()
            ended = utc_now()
            self._tracer.record_tool_call(
                time_span.id,
                {
                    "tool_name": "clock",
                    "arguments": {},
                    "result": result,
                    "owner_agent": "TimeAgent",
                    "purpose": "clock_execution",
                    "started_at": started,
                    "ended_at": ended,
                },
            )
            observation = {"type": "tool_result", "owner_agent": "TimeAgent", "tool": "clock", "arguments": {"task": task}, "result": result}
            record_decision(
                self._tracer,
                time_span.id,
                "TimeAgent",
                "tool_observation",
                task,
                f"clock devolvió {result}; TimeAgent normaliza la observación y la devuelve a MainAgent.",
                available_tools=["clock"],
                payload=observation,
            )
            return observation
