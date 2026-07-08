# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import os
from collections.abc import Callable
from typing import Any, TypeVar

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from llm.planner_schemas import HiddenReasoningStep, PlannerAssessment, PlannerDecision
from observability.models import TokenUsage
from observability.run_events import emit_run_event

T = TypeVar("T", bound=BaseModel)


def _chat_model():
    from langchain_openai import ChatOpenAI

    litellm_base_url = os.environ["LITELLM_BASE_URL"]
    llm_model = os.environ["LLM_MODEL"]
    litellm_master_key = os.environ["LITELLM_MASTER_KEY"]
    return ChatOpenAI(
        base_url=f"{litellm_base_url}/v1",
        api_key=litellm_master_key,
        model=llm_model,
        stream_usage=True,
    )


def _token_usage_from_message(message: AIMessage) -> TokenUsage:
    usage = message.usage_metadata
    if not usage:
        return TokenUsage(input=0, output=0)
    return TokenUsage(
        input=int(usage.get("input_tokens", 0)),
        output=int(usage.get("output_tokens", 0)),
    )


def _build_messages(prompt: str, system: str | None) -> list:
    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))
    return messages


def _emit_llm_started(purpose: str) -> None:
    emit_run_event("llm_started", {"purpose": purpose, "model": get_model_name()})


def _emit_llm_delta(purpose: str, delta: str, text: str) -> None:
    emit_run_event("llm_delta", {"purpose": purpose, "delta": delta, "text": text})


def _emit_llm_completed(purpose: str, output: str, tokens: TokenUsage) -> None:
    emit_run_event(
        "llm_completed",
        {
            "purpose": purpose,
            "output": output,
            "input_tokens": tokens.input,
            "output_tokens": tokens.output,
        },
    )


def _stream_gateway_llm(messages: list, on_chunk: Callable[[str], None]) -> tuple[str, TokenUsage]:
    llm = _chat_model()
    parts: list[str] = []
    tokens = TokenUsage(input=0, output=0)
    for chunk in llm.stream(messages):
        if chunk.content:
            piece = str(chunk.content)
            parts.append(piece)
            on_chunk(piece)
        if chunk.usage_metadata:
            tokens = _token_usage_from_message(chunk)
    return "".join(parts), tokens


def _mock_stream(output: str, on_chunk: Callable[[str], None]) -> None:
    for piece in output.split(" "):
        on_chunk(f"{piece} ")


def invoke_llm(prompt: str, system: str | None = None, purpose: str | None = None) -> tuple[str, TokenUsage]:
    model_provider = os.environ["MODEL_PROVIDER"]

    if purpose is not None:
        _emit_llm_started(purpose)

    if model_provider == "mock":
        output = f"[mock] Respuesta a: '{prompt}'"
        if purpose is not None:
            accumulated = ""

            def capture(delta: str) -> None:
                nonlocal accumulated
                accumulated += delta
                _emit_llm_delta(purpose, delta, accumulated)

            _mock_stream(output, capture)
        tokens = TokenUsage(input=len(prompt.split()), output=len(output.split()))
        if purpose is not None:
            _emit_llm_completed(purpose, output, tokens)
        return output, tokens

    if model_provider == "gateway":
        messages = _build_messages(prompt, system)
        if purpose is not None:
            accumulated = ""

            def on_chunk(delta: str) -> None:
                nonlocal accumulated
                accumulated += delta
                _emit_llm_delta(purpose, delta, accumulated)

            output, tokens = _stream_gateway_llm(messages, on_chunk)
        else:
            response = _chat_model().invoke(messages)
            output = str(response.content)
            tokens = _token_usage_from_message(response)

        if purpose is not None:
            _emit_llm_completed(purpose, output, tokens)
        return output, tokens

    raise ValueError(f"MODEL_PROVIDER no soportado: {model_provider}")


def _unwrap_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    if "properties" in args and isinstance(args["properties"], dict):
        return dict(args["properties"])
    return args


def _parse_structured_response(response: dict[str, Any], schema: type[T]) -> T | None:
    parsed = response.get("parsed")
    if parsed is not None:
        return parsed

    raw_message = response.get("raw")
    tool_calls = getattr(raw_message, "tool_calls", None) or []
    for tool_call in tool_calls:
        raw_args = tool_call.get("args") if isinstance(tool_call, dict) else getattr(tool_call, "args", None)
        if not isinstance(raw_args, dict):
            continue
        try:
            return schema.model_validate(_unwrap_tool_args(raw_args))
        except Exception:
            continue

    content = getattr(raw_message, "content", None)
    if isinstance(content, str) and content.strip():
        try:
            return schema.model_validate_json(content)
        except Exception:
            pass
    return None


def _invoke_gateway_structured(messages: list, schema: type[T]) -> tuple[T, str, TokenUsage]:
    methods = ("json_schema", "function_calling")
    last_error: object = None
    for method in methods:
        structured_llm = _chat_model().with_structured_output(schema, method=method, include_raw=True)
        response = structured_llm.invoke(messages)
        parsed = _parse_structured_response(response, schema)
        if parsed is not None:
            raw_message = response["raw"]
            output = parsed.model_dump_json(ensure_ascii=False)
            tokens = _token_usage_from_message(raw_message)
            return parsed, output, tokens
        last_error = response.get("parsing_error")
    raise ValueError(f"el proveedor no devolvió salida estructurada válida: {last_error}")


def invoke_llm_structured(prompt: str, system: str | None, schema: type[T], purpose: str) -> tuple[T, str, TokenUsage]:
    model_provider = os.environ["MODEL_PROVIDER"]
    _emit_llm_started(purpose)

    if model_provider == "mock":
        parsed = _mock_structured_response(schema, prompt)
        output = parsed.model_dump_json(ensure_ascii=False)
        tokens = TokenUsage(input=len(prompt.split()), output=len(output.split()))
        _emit_llm_completed(purpose, output, tokens)
        return parsed, output, tokens

    if model_provider == "gateway":
        messages = _build_messages(prompt, system)
        parsed, output, tokens = _invoke_gateway_structured(messages, schema)
        _emit_llm_completed(purpose, output, tokens)
        return parsed, output, tokens

    raise ValueError(f"MODEL_PROVIDER no soportado: {model_provider}")


def get_model_name() -> str:
    model_provider = os.environ["MODEL_PROVIDER"]
    if model_provider == "mock":
        return "mock"
    if model_provider == "gateway":
        return os.environ["LLM_MODEL"]
    raise ValueError(f"MODEL_PROVIDER no soportado: {model_provider}")


def _mock_structured_response(schema: type[T], prompt: str) -> T:
    if schema is PlannerAssessment:
        return PlannerAssessment(
            task_understanding=f"[mock] assessment para: {prompt[:120]}",
            hidden_reasoning=[
                HiddenReasoningStep(
                    step=1,
                    thought="mock assessment",
                    evidence="MODEL_PROVIDER=mock",
                    decision_impact="usar direct_answer",
                )
            ],
            decision_status="ready",
            preliminary_action="direct_answer",
            confidence=0.5,
        )
    if schema is PlannerDecision:
        return PlannerDecision(
            selected_action="direct_answer",
            arguments={"task": prompt},
            hidden_reasoning=[
                HiddenReasoningStep(
                    step=1,
                    thought="mock decision",
                    evidence="MODEL_PROVIDER=mock",
                    decision_impact="seleccionar direct_answer",
                )
            ],
            confidence=0.5,
            rationale="decisión mock",
        )
    raise ValueError(f"mock no implementado para schema {schema.__name__}")
