# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import os
import re
import subprocess


_ENTRY_HEADER = re.compile(r"^\[\d+\] #\d+ \([^)]+\) — (.+)$")
_METADATA_LINE = re.compile(r"^\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+\|")


class MemoryStore:
    def __init__(self) -> None:
        self._project = os.environ["MNEMO_PROJECT"]

    def search(self, query: str, limit: int) -> list[str]:
        completed = subprocess.run(
            ["mnemo", "search", query, "--project", self._project, "--limit", str(limit)],
            capture_output=True,
            text=True,
            check=True,
        )
        output = completed.stdout
        if "No memories found" in output:
            return []
        return _parse_search_output(output)

    def save(self, title: str, content: str) -> None:
        subprocess.run(
            ["mnemo", "save", title, content, "--project", self._project],
            capture_output=True,
            text=True,
            check=True,
        )


def _parse_search_output(output: str) -> list[str]:
    results: list[str] = []
    current_title: str | None = None
    content_lines: list[str] = []

    for line in output.splitlines():
        match = _ENTRY_HEADER.match(line)
        if match:
            if current_title is not None:
                results.append(_format_entry(current_title, content_lines))
            current_title = match.group(1).strip()
            content_lines = []
            continue
        if current_title is None:
            continue
        if not line.strip() or line.startswith("Found "):
            continue
        if _METADATA_LINE.match(line):
            continue
        content_lines.append(line.strip())

    if current_title is not None:
        results.append(_format_entry(current_title, content_lines))

    return results


def _format_entry(title: str, content_lines: list[str]) -> str:
    snippet = " ".join(content_lines).strip()
    if snippet:
        return f"{title}: {snippet}"
    return title
