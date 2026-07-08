# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

from agents.model_call_builder import build_model_call_record
from agents.observability_helpers import record_decision, utc_now
from llm.gateway import get_model_name, invoke_llm
from llm.prompt_xml import append_internal_context
from memory.service import save_memory
from observability.decorators import span
from observability.tracer import Tracer

_WRITER_TOOLS = ("llm_draft", "memory.save")

_WRITER_SYSTEM = (
    "Redacta un documento breve y estructurado sobre el tema del usuario. "
    "Usa el bloque <internal_context>; devuelve solo el documento, sin etiquetas XML."
)


class WriterAgent:
    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def run(self, run_id: str, topic: str, research_output: str, parent_span_id: str) -> str:
        with span(self._tracer, run_id, "writer_agent", "agent", parent_span_id) as writer_span:
            record_decision(
                self._tracer,
                writer_span.id,
                "WriterAgent",
                "subagent_received",
                topic,
                "WriterAgent recibe una síntesis de investigación delegada para redactar y persistir la respuesta.",
                payload={"topic": topic, "research_output_preview": research_output[:240]},
            )
            record_decision(
                self._tracer,
                writer_span.id,
                "WriterAgent",
                "tool_catalog_read",
                topic,
                "WriterAgent consulta su catálogo propio: borrador LLM y guardado en memoria.",
                available_tools=list(_WRITER_TOOLS),
                selected_tools=list(_WRITER_TOOLS),
            )
            system, _ = append_internal_context(
                _WRITER_SYSTEM,
                research_output=research_output,
            )
            prompt = topic
            record_decision(
                self._tracer,
                writer_span.id,
                "WriterAgent",
                "model_call_request",
                topic,
                "WriterAgent solicita al LLM redactar el documento final a partir de la investigación.",
                available_tools=["llm_draft"],
                selected_tools=["llm_draft"],
                payload={"prompt": prompt, "system": system},
            )
            llm_started = utc_now()
            output, tokens = invoke_llm(prompt, system=system, purpose="writer_draft")
            llm_ended = utc_now()
            self._tracer.record_model_call(
                writer_span.id,
                build_model_call_record(
                    model=get_model_name(),
                    system=system,
                    prompt=prompt,
                    output=output,
                    input_tokens=tokens.input,
                    output_tokens=tokens.output,
                    purpose="writer_draft",
                    components={
                        "user_message": topic,
                        "history": research_output,
                    },
                    started_at=llm_started,
                    ended_at=llm_ended,
                ),
            )
            record_decision(
                self._tracer,
                writer_span.id,
                "WriterAgent",
                "model_observation",
                topic,
                f"El modelo redactó el documento con {tokens.input} tokens de entrada y {tokens.output} tokens de salida.",
                available_tools=["llm_draft"],
            )
            save_memory(
                self._tracer,
                writer_span.id,
                f"documento: {topic}",
                output,
                owner_agent="WriterAgent",
                purpose="memory_save",
            )
            record_decision(
                self._tracer,
                writer_span.id,
                "WriterAgent",
                "memory_persistence",
                topic,
                "El documento final fue persistido en memoria para futuras ejecuciones.",
                available_tools=["memory.save"],
                payload={"title": f"documento: {topic}"},
            )
            return output
