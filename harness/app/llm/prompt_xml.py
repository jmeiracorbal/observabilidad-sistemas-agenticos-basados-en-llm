# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

from xml.sax.saxutils import escape

INTERNAL_CONTEXT_TAG = "internal_context"


def escape_xml_text(value: str) -> str:
    return escape(value, entities={'"': "&quot;", "'": "&apos;"})


def xml_element(tag: str, content: str, *, raw: bool = False) -> str:
    body = content if raw else escape_xml_text(content)
    return f"<{tag}>\n{body}\n</{tag}>"


def build_internal_context(sections: dict[str, str]) -> str:
    active = {tag: content for tag, content in sections.items() if content.strip()}
    if not active:
        return xml_element(INTERNAL_CONTEXT_TAG, "")
    children = "\n".join(xml_element(tag, content) for tag, content in active.items())
    return xml_element(INTERNAL_CONTEXT_TAG, children, raw=True)


def forbidden_xml_tags(*tags: str) -> tuple[str, ...]:
    markers: list[str] = []
    for tag in tags:
        markers.append(f"<{tag}>")
        markers.append(f"</{tag}>")
    return tuple(markers)


def append_internal_context(system: str, **sections: str) -> tuple[str, tuple[str, ...]]:
    active = {tag: content for tag, content in sections.items() if content.strip()}
    block = build_internal_context(active)
    tags = (INTERNAL_CONTEXT_TAG,) + tuple(active.keys())
    return f"{system.rstrip()}\n\n{block}", forbidden_xml_tags(*tags)
