# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import re
from typing import Literal

from agents.observability_helpers import record_decision
from memory.service import save_memory, search_memory
from observability.decorators import span
from observability.tracer import Tracer

_MEMORY_TOOLS = ("memory.search", "memory.save")

_MEMORY_SAVE_PATTERNS = (
    "guardar en memoria",
    "guarda en memoria",
    "guárdame en memoria",
    "guardame en memoria",
    "guárdalo en memoria",
    "guardalo en memoria",
    "persiste en memoria",
    "recuérdame",
    "recuerdame",
    "recuerda que",
)

_MEMORY_RECALL_PATTERNS = (
    "cómo me llamo",
    "como me llamo",
    "cuál es mi nombre",
    "cual es mi nombre",
    "qué sabes de mí",
    "que sabes de mi",
    "recuerdas mi nombre",
    "recuerdas cómo me llamo",
    "recuerdas como me llamo",
)

_NAME_FACT = re.compile(
    r"(?:me llamo|mi nombre es)\s+([^\.\!\?\n,;]+)",
    re.IGNORECASE,
)

MemoryOperation = Literal["save", "recall"]


def memory_operation(text: str) -> MemoryOperation | None:
    normalized = text.strip().lower()
    if any(pattern in normalized for pattern in _MEMORY_SAVE_PATTERNS):
        return "save"
    if any(pattern in normalized for pattern in _MEMORY_RECALL_PATTERNS):
        return "recall"
    return None


def requests_memory_save(text: str) -> bool:
    return memory_operation(text) == "save"


def requests_memory_recall(text: str) -> bool:
    return memory_operation(text) == "recall"


class MemoryAgent:
    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def run(self, run_id: str, task: str, operation: MemoryOperation, parent_span_id: str) -> dict:
        with span(self._tracer, run_id, "memory_agent", "agent", parent_span_id) as memory_span:
            record_decision(
                self._tracer,
                memory_span.id,
                "MemoryAgent",
                "subagent_received",
                task,
                "MemoryAgent recibe una operación de memoria delegada por MainAgent.",
                payload={"task": task, "operation": operation},
            )
            record_decision(
                self._tracer,
                memory_span.id,
                "MemoryAgent",
                "tool_catalog_read",
                task,
                "MemoryAgent consulta su catálogo propio: búsqueda y persistencia en mnemo.",
                available_tools=list(_MEMORY_TOOLS),
            )

            if operation == "save":
                return self._run_save(memory_span.id, task)
            return self._run_recall(memory_span.id, task)

    def _run_save(self, span_id: str, task: str) -> dict:
        title, content = _build_memory_fact(task)
        record_decision(
            self._tracer,
            span_id,
            "MemoryAgent",
            "tool_selection",
            task,
            "MemoryAgent selecciona memory.save para persistir un hecho factual del usuario.",
            available_tools=list(_MEMORY_TOOLS),
            selected_tools=["memory.save"],
            payload={"selected_tool": "memory.save", "title": title, "content": content},
        )
        record_decision(
            self._tracer,
            span_id,
            "MemoryAgent",
            "tool_call_request",
            task,
            f"MemoryAgent solicita persistir el hecho {title!r}.",
            available_tools=list(_MEMORY_TOOLS),
            selected_tools=["memory.save"],
            payload={"tool_name": "memory.save", "arguments": {"title": title, "content": content}},
        )
        save_memory(
            self._tracer,
            span_id,
            title,
            content,
            owner_agent="MemoryAgent",
            purpose="memory_save",
        )
        observation = {
            "type": "memory_result",
            "owner_agent": "MemoryAgent",
            "tool": "memory.save",
            "arguments": {"task": task, "operation": "save", "title": title},
            "result": content,
        }
        record_decision(
            self._tracer,
            span_id,
            "MemoryAgent",
            "tool_observation",
            task,
            "memory.save confirmó la persistencia del hecho.",
            available_tools=["memory.save"],
            payload=observation,
        )
        record_decision(
            self._tracer,
            span_id,
            "MemoryAgent",
            "memory_persistence",
            task,
            "MemoryAgent confirma la persistencia del hecho en mnemo.",
            available_tools=["memory.save"],
            payload={"title": title, "content": content},
        )
        return observation

    def _run_recall(self, span_id: str, task: str) -> dict:
        query = _recall_query(task)
        record_decision(
            self._tracer,
            span_id,
            "MemoryAgent",
            "tool_selection",
            task,
            "MemoryAgent selecciona memory.search para recuperar hechos del usuario.",
            available_tools=list(_MEMORY_TOOLS),
            selected_tools=["memory.search"],
            payload={"selected_tool": "memory.search", "query": query},
        )
        record_decision(
            self._tracer,
            span_id,
            "MemoryAgent",
            "tool_call_request",
            task,
            f"MemoryAgent solicita memory.search con query={query!r}.",
            available_tools=list(_MEMORY_TOOLS),
            selected_tools=["memory.search"],
            payload={"tool_name": "memory.search", "arguments": {"query": query}},
        )
        results = search_memory(
            self._tracer,
            span_id,
            query,
            owner_agent="MemoryAgent",
            purpose="memory_search",
        )
        result_text = _format_recall_results(results)
        observation = {
            "type": "memory_result",
            "owner_agent": "MemoryAgent",
            "tool": "memory.search",
            "arguments": {"task": task, "operation": "recall", "query": query},
            "result": result_text,
        }
        record_decision(
            self._tracer,
            span_id,
            "MemoryAgent",
            "tool_observation",
            task,
            f"memory.search devolvió {len(results)} resultado(s).",
            available_tools=["memory.search"],
            payload=observation,
        )
        record_decision(
            self._tracer,
            span_id,
            "MemoryAgent",
            "memory_observation",
            task,
            f"MemoryAgent recuperó {len(results)} resultado(s) desde mnemo.",
            available_tools=["memory.search"],
            payload={"query": query, "results": results, "results_count": len(results)},
        )
        return observation


def _build_memory_fact(task: str) -> tuple[str, str]:
    name_match = _NAME_FACT.search(task)
    if name_match:
        name = name_match.group(1).strip()
        return f"nombre: {name}", f"El usuario se llama {name}."
    normalized = task.strip()
    return "hecho usuario", normalized


def _recall_query(task: str) -> str:
    normalized = task.strip().lower()
    if any(pattern in normalized for pattern in ("cómo me llamo", "como me llamo", "mi nombre", "recuerdas mi nombre")):
        return "nombre usuario"
    return task.strip()


def _format_recall_results(results: list[str]) -> str:
    if not results:
        return "No encontré nada en memoria sobre eso."
    return "Según la memoria: " + " · ".join(results)
