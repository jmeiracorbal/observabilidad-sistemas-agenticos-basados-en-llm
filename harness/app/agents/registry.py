# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

AGENT_REGISTRY: dict[str, dict] = {
    "math_agent": {
        "owner": "MainAgent",
        "target_agent": "MathAgent",
        "capabilities": [
            "Resolver cálculos aritméticos, expresiones numéricas y preguntas matemáticas directas.",
            "Decidir internamente qué herramienta matemática usar y cómo construir sus argumentos.",
        ],
        "public_tools": [
            {
                "name": "calculator",
                "owner_agent": "MathAgent",
                "description": "Evalúa expresiones aritméticas seguras.",
            }
        ],
        "task_contract": {"task": "texto original o tarea matemática solicitada por el usuario"},
    },
    "time_agent": {
        "owner": "MainAgent",
        "target_agent": "TimeAgent",
        "capabilities": [
            "Resolver preguntas sobre hora o fecha actual.",
            "Decidir internamente si debe ejecutar su herramienta temporal.",
        ],
        "public_tools": [
            {
                "name": "clock",
                "owner_agent": "TimeAgent",
                "description": "Obtiene la hora actual UTC.",
            }
        ],
        "task_contract": {"task": "texto original o tarea temporal solicitada por el usuario"},
    },
    "researcher_agent": {
        "owner": "MainAgent",
        "target_agent": "ResearcherAgent",
        "capabilities": [
            "Investigar preguntas que requieran contexto, memoria, búsqueda simulada, lectura local o síntesis.",
            "Preparar una síntesis para que WriterAgent redacte una respuesta persistible.",
        ],
        "public_tools": [
            {"name": "memory.search", "owner_agent": "ResearcherAgent", "description": "Consulta memoria persistente."},
            {"name": "web_search", "owner_agent": "ResearcherAgent", "description": "Búsqueda simulada determinista."},
            {"name": "file_reader", "owner_agent": "ResearcherAgent", "description": "Lee documentos locales sembrados."},
            {"name": "llm_synthesis", "owner_agent": "ResearcherAgent", "description": "Sintetiza contexto con LLM."},
        ],
        "task_contract": {"topic": "tema a investigar o texto original del usuario"},
    },
    "direct_answer": {
        "owner": "MainAgent",
        "target_agent": "LLM Final",
        "capabilities": [
            "Responder sin herramienta de dominio cuando no se requiere subagente.",
        ],
        "public_tools": [],
        "task_contract": {"task": "texto original del usuario"},
    },
    "memory_agent": {
        "owner": "MainAgent",
        "target_agent": "MemoryAgent",
        "capabilities": [
            "Guardar hechos del usuario en memoria persistente (mnemo).",
            "Recuperar hechos previamente guardados del usuario.",
        ],
        "public_tools": [
            {"name": "memory.search", "owner_agent": "MemoryAgent", "description": "Consulta memoria persistente."},
            {"name": "memory.save", "owner_agent": "MemoryAgent", "description": "Persiste un hecho del usuario en memoria."},
        ],
        "task_contract": {
            "task": "texto original del usuario",
            "operation": "save | recall",
        },
    },
}


def action_names() -> tuple[str, ...]:
    return tuple(AGENT_REGISTRY.keys())


def public_catalog() -> list[dict]:
    return [
        {
            "action": action,
            "owner": definition["owner"],
            "target_agent": definition["target_agent"],
            "capabilities": definition["capabilities"],
            "public_tools": definition["public_tools"],
            "task_contract": definition["task_contract"],
        }
        for action, definition in AGENT_REGISTRY.items()
    ]
