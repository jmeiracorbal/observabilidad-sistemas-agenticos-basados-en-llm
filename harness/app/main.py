# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import asyncio
import json
import os
import queue
import threading
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.main_agent import MainAgent
from observability.run_events import reset_run_event_emitter, set_run_event_emitter
from observability.tracer import Tracer

app = FastAPI(title="Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InvokeRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class InvokeResponse(BaseModel):
    run_id: str
    conversation_id: str
    turn_index: int
    response: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/invoke", response_model=InvokeResponse)
def invoke(req: InvokeRequest):
    tracer = Tracer()
    agent = MainAgent(tracer)
    run_id, response, conversation_id, turn_index = agent.run(req.message, req.conversation_id)
    return InvokeResponse(run_id=run_id, conversation_id=conversation_id, turn_index=turn_index, response=response)


def _format_sse(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/invoke/stream")
async def invoke_stream(req: InvokeRequest):
    event_queue: queue.Queue[str | None] = queue.Queue()

    def emit(event_type: str, data: dict[str, Any]) -> None:
        event_queue.put(_format_sse(event_type, data))

    def run_agent() -> None:
        token = set_run_event_emitter(emit)
        try:
            tracer = Tracer()
            agent = MainAgent(tracer)
            run_id, response, conversation_id, turn_index = agent.run(req.message, req.conversation_id)
            emit(
                "run_completed",
                {
                    "run_id": run_id,
                    "conversation_id": conversation_id,
                    "turn_index": turn_index,
                    "response": response,
                },
            )
        except Exception as exc:
            emit("run_failed", {"error": str(exc)})
        finally:
            reset_run_event_emitter(token)
            event_queue.put(None)

    threading.Thread(target=run_agent, daemon=True).start()

    async def event_generator():
        while True:
            item = await asyncio.to_thread(event_queue.get)
            if item is None:
                break
            yield item

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
