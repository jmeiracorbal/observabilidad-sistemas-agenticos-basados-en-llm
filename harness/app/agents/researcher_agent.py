# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

from agents.model_call_builder import build_model_call_record
from agents.observability_helpers import record_decision, utc_now
from llm.gateway import get_model_name, invoke_llm
from llm.prompt_xml import append_internal_context
from memory.service import search_memory
from observability.decorators import span
from observability.tracer import Tracer
from tools.file_reader import file_reader
from tools.web_search import web_search

_SEEDED_DOC = "observabilidad.md"
_RESEARCH_TOOLS = ("memory.search", "web_search", "file_reader", "llm_synthesis")

_RESEARCHER_SYSTEM = (
    "Sintetiza en un párrafo lo relevante sobre el tema del usuario. "
    "Usa el bloque <internal_context>; devuelve solo la síntesis, sin etiquetas XML."
)


class ResearcherAgent:
    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def run(self, run_id: str, topic: str, parent_span_id: str) -> str:
        with span(self._tracer, run_id, "researcher_agent", "agent", parent_span_id) as researcher_span:
            record_decision(
                self._tracer,
                researcher_span.id,
                "ResearcherAgent",
                "subagent_received",
                topic,
                "ResearcherAgent recibe una petición de investigación delegada por MainAgent.",
                payload={"topic": topic},
            )
            record_decision(
                self._tracer,
                researcher_span.id,
                "ResearcherAgent",
                "tool_catalog_read",
                topic,
                "ResearcherAgent consulta su catálogo propio: memoria, búsqueda simulada, documento local y síntesis LLM.",
                available_tools=list(_RESEARCH_TOOLS),
                selected_tools=list(_RESEARCH_TOOLS),
            )
            memory_results = search_memory(
                self._tracer,
                researcher_span.id,
                topic,
                owner_agent="ResearcherAgent",
                purpose="memory_search",
            )
            memory_context = "\n".join(memory_results) if memory_results else "(sin resultados previos)"
            record_decision(
                self._tracer,
                researcher_span.id,
                "ResearcherAgent",
                "memory_observation",
                topic,
                f"La búsqueda de memoria devolvió {len(memory_results)} resultados.",
                available_tools=["memory.search"],
                payload={"results_count": len(memory_results), "results": memory_results},
            )

            web_started = utc_now()
            web_results = web_search(topic)
            web_ended = utc_now()
            self._tracer.record_tool_call(
                researcher_span.id,
                {
                    "tool_name": "web_search",
                    "arguments": {"query": topic},
                    "result": web_results,
                    "owner_agent": "ResearcherAgent",
                    "purpose": "web_search",
                    "started_at": web_started,
                    "ended_at": web_ended,
                },
            )
            web_context = "\n".join(web_results)
            record_decision(
                self._tracer,
                researcher_span.id,
                "ResearcherAgent",
                "tool_observation",
                topic,
                f"web_search devolvió {len(web_results)} resultados simulados.",
                available_tools=["web_search"],
                payload={"results": web_results},
            )

            file_started = utc_now()
            doc_content = file_reader(_SEEDED_DOC)
            file_ended = utc_now()
            self._tracer.record_tool_call(
                researcher_span.id,
                {
                    "tool_name": "file_reader",
                    "arguments": {"path": _SEEDED_DOC},
                    "result": doc_content,
                    "owner_agent": "ResearcherAgent",
                    "purpose": "file_read",
                    "started_at": file_started,
                    "ended_at": file_ended,
                },
            )
            record_decision(
                self._tracer,
                researcher_span.id,
                "ResearcherAgent",
                "tool_observation",
                topic,
                f"file_reader cargó {_SEEDED_DOC} con {len(doc_content.split())} palabras aproximadas.",
                available_tools=["file_reader"],
                payload={"path": _SEEDED_DOC, "words": len(doc_content.split())},
            )

            system, _ = append_internal_context(
                _RESEARCHER_SYSTEM,
                memory_results=memory_context,
                web_search_results=web_context,
                local_document=doc_content,
            )
            prompt = topic
            record_decision(
                self._tracer,
                researcher_span.id,
                "ResearcherAgent",
                "model_call_request",
                topic,
                "ResearcherAgent solicita al LLM sintetizar memoria, búsqueda simulada y documento local.",
                available_tools=["llm_synthesis"],
                selected_tools=["llm_synthesis"],
                payload={"prompt": prompt, "system": system},
            )
            llm_started = utc_now()
            output, tokens = invoke_llm(prompt, system=system, purpose="research_synthesis")
            llm_ended = utc_now()
            self._tracer.record_model_call(
                researcher_span.id,
                build_model_call_record(
                    model=get_model_name(),
                    system=system,
                    prompt=prompt,
                    output=output,
                    input_tokens=tokens.input,
                    output_tokens=tokens.output,
                    purpose="research_synthesis",
                    components={
                        "user_message": topic,
                        "memory": memory_context,
                        "rag": web_context,
                        "document": doc_content,
                    },
                    started_at=llm_started,
                    ended_at=llm_ended,
                ),
            )
            record_decision(
                self._tracer,
                researcher_span.id,
                "ResearcherAgent",
                "model_observation",
                topic,
                f"El modelo sintetizó la investigación con {tokens.input} tokens de entrada y {tokens.output} tokens de salida.",
                available_tools=["llm_synthesis"],
            )
            return output
