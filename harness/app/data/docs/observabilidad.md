# Observabilidad en sistemas agénticos

La observabilidad en sistemas agénticos basados en LLM requiere reconstruir el flujo interno de ejecución: entrada del usuario, construcción del contexto, llamadas al modelo, uso de herramientas, acceso a memoria y respuesta final.

Los eventos estructurados (runs, spans, model_calls, tool_calls, memory_events) permiten auditar qué ocurrió en cada paso sin depender de logs planos.

El arnés no decide ni razona: observa, envuelve y registra la ejecución del agente.
