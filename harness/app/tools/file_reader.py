# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

from pathlib import Path

_DOCS_BASE = Path(__file__).resolve().parent.parent / "data" / "docs"


def file_reader(filename: str) -> str:
    base = _DOCS_BASE.resolve()
    target = (base / filename).resolve()
    if base not in target.parents and target != base:
        raise ValueError(f"ruta fuera del directorio permitido: {filename}")
    if not target.is_file():
        raise FileNotFoundError(f"documento no encontrado: {filename}")
    return target.read_text(encoding="utf-8")
