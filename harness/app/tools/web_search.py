# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

def web_search(query: str) -> list[str]:
    # simulada: resultados deterministas locales, sin red
    return [
        f"[simulado] Definicion de '{query}' en fuente local A",
        f"[simulado] Caso de uso de '{query}' en sistemas distribuidos",
        f"[simulado] Buenas practicas sobre '{query}' en agentes LLM",
    ]
