# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 José Antonio Meira Corbal
# Trabajo de Fin de Estudio — Grado en Ingeniería Informática, UNIR

import os
import json
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Observability API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_CONFIG = {
    "host": os.environ["POSTGRES_HOST"],
    "port": int(os.environ.get("POSTGRES_PORT", 5432)),
    "dbname": os.environ["POSTGRES_DB"],
    "user": os.environ["POSTGRES_USER"],
    "password": os.environ["POSTGRES_PASSWORD"],
}

MEMORY_PLUGIN_ACTOR = "Memoria (mnemo)"

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_events_run_id ON events (run_id);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    input TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ
);
ALTER TABLE runs ADD COLUMN IF NOT EXISTS conversation_id TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS turn_index INTEGER;

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    run_id TEXT REFERENCES runs(id),
    turn_index INTEGER NOT NULL,
    role TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_id
ON conversation_messages (conversation_id, turn_index, id);

CREATE TABLE IF NOT EXISTS spans (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    parent_span_id TEXT,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_spans_run_id ON spans (run_id);

CREATE TABLE IF NOT EXISTS model_calls (
    id SERIAL PRIMARY KEY,
    span_id TEXT NOT NULL REFERENCES spans(id),
    model TEXT NOT NULL,
    input TEXT NOT NULL,
    output TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    purpose TEXT,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE model_calls ADD COLUMN IF NOT EXISTS purpose TEXT;
ALTER TABLE model_calls ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE model_calls ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;
ALTER TABLE model_calls ADD COLUMN IF NOT EXISTS context_metadata JSONB;
CREATE INDEX IF NOT EXISTS idx_model_calls_span_id ON model_calls (span_id);

CREATE TABLE IF NOT EXISTS tool_calls (
    id SERIAL PRIMARY KEY,
    span_id TEXT NOT NULL REFERENCES spans(id),
    tool_name TEXT NOT NULL,
    arguments JSONB NOT NULL,
    result TEXT NOT NULL,
    owner_agent TEXT,
    purpose TEXT,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS owner_agent TEXT;
ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS purpose TEXT;
ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_tool_calls_span_id ON tool_calls (span_id);

CREATE TABLE IF NOT EXISTS memory_events (
    id SERIAL PRIMARY KEY,
    span_id TEXT NOT NULL REFERENCES spans(id),
    operation TEXT NOT NULL,
    query TEXT NOT NULL,
    results_count INTEGER NOT NULL,
    owner_agent TEXT,
    purpose TEXT,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE memory_events ADD COLUMN IF NOT EXISTS owner_agent TEXT;
ALTER TABLE memory_events ADD COLUMN IF NOT EXISTS purpose TEXT;
ALTER TABLE memory_events ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE memory_events ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_memory_events_span_id ON memory_events (span_id);

CREATE TABLE IF NOT EXISTS decision_events (
    id SERIAL PRIMARY KEY,
    span_id TEXT NOT NULL REFERENCES spans(id),
    actor TEXT NOT NULL,
    stage TEXT NOT NULL,
    input TEXT NOT NULL,
    available_tools JSONB NOT NULL,
    selected_tools JSONB NOT NULL,
    rationale TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE decision_events ADD COLUMN IF NOT EXISTS actor TEXT;
ALTER TABLE decision_events ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE decision_events ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE decision_events ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_decision_events_span_id ON decision_events (span_id);

CREATE TABLE IF NOT EXISTS errors (
    id SERIAL PRIMARY KEY,
    span_id TEXT NOT NULL REFERENCES spans(id),
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_errors_span_id ON errors (span_id);
"""


@contextmanager
def get_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


@app.on_event("startup")
def startup():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLES_SQL)


@app.get("/health")
def health():
    return {"status": "ok"}


class EventIn(BaseModel):
    run_id: str
    event_type: str
    payload: Optional[dict] = None


class RunIn(BaseModel):
    id: str
    input: str
    conversation_id: str
    turn_index: int
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None


class RunEndIn(BaseModel):
    status: Literal["running", "completed", "failed"]


class SpanIn(BaseModel):
    id: str
    run_id: str
    parent_span_id: Optional[str] = None
    type: Literal["agent", "tool", "memory", "model"]
    name: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None


class SpanEndIn(BaseModel):
    status: Literal["running", "completed", "failed"]
    ended_at: Optional[datetime] = None


class ModelCallIn(BaseModel):
    span_id: str
    model: str
    input: str
    output: str
    input_tokens: int
    output_tokens: int
    purpose: Optional[str] = None
    context_metadata: Optional[dict] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class ToolCallIn(BaseModel):
    span_id: str
    tool_name: str
    arguments: dict
    result: str
    owner_agent: Optional[str] = None
    purpose: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class MemoryEventIn(BaseModel):
    span_id: str
    operation: str
    query: str
    results_count: int
    owner_agent: Optional[str] = None
    purpose: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class DecisionEventIn(BaseModel):
    span_id: str
    actor: str
    stage: str
    input: str
    available_tools: list[str]
    selected_tools: list[str]
    rationale: str
    payload: dict = {}
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class ErrorIn(BaseModel):
    span_id: str
    error_type: str
    message: str


class ConversationIn(BaseModel):
    id: str
    status: str = "active"


class ConversationMessageIn(BaseModel):
    conversation_id: str
    run_id: Optional[str] = None
    turn_index: int
    role: Literal["system", "user", "assistant", "summary"]
    kind: Literal["raw", "summary"]
    content: str
    token_count: int


class ConversationMessageDeleteIn(BaseModel):
    ids: list[int]


@app.post("/events", status_code=201)
def create_event(event: EventIn):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO events (run_id, event_type, payload) VALUES (%s, %s, %s)",
                (event.run_id, event.event_type, json.dumps(event.payload or {})),
            )
    return {"ok": True}


@app.get("/events")
def list_events(run_id: Optional[str] = Query(default=None)):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if run_id:
                cur.execute(
                    "SELECT * FROM events WHERE run_id = %s ORDER BY created_at ASC",
                    (run_id,),
                )
            else:
                cur.execute("SELECT * FROM events ORDER BY created_at DESC LIMIT 100")
            return cur.fetchall()


@app.post("/conversations", status_code=201)
def create_conversation(body: ConversationIn):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (id, status, created_at, updated_at)
                VALUES (%s, %s, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET updated_at = NOW()
                """,
                (body.id, body.status),
            )
    return {"ok": True}


@app.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM conversations WHERE id = %s", (conversation_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="conversación no encontrada")
    return row


@app.get("/conversations/{conversation_id}/messages")
def list_conversation_messages(conversation_id: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM conversation_messages
                WHERE conversation_id = %s
                ORDER BY turn_index ASC, id ASC
                """,
                (conversation_id,),
            )
            return cur.fetchall()


@app.post("/conversation_messages", status_code=201)
def create_conversation_message(body: ConversationMessageIn):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversation_messages (
                    conversation_id, run_id, turn_index, role, kind, content, token_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    body.conversation_id,
                    body.run_id,
                    body.turn_index,
                    body.role,
                    body.kind,
                    body.content,
                    body.token_count,
                ),
            )
            cur.execute("UPDATE conversations SET updated_at = NOW() WHERE id = %s", (body.conversation_id,))
    return {"ok": True}


@app.post("/conversation_messages/delete", status_code=200)
def delete_conversation_messages(body: ConversationMessageDeleteIn):
    if not body.ids:
        return {"ok": True}
    with get_conn() as conn:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(body.ids))
            cur.execute(f"DELETE FROM conversation_messages WHERE id IN ({placeholders})", body.ids)
    return {"ok": True}


@app.post("/runs", status_code=201)
def create_run(run: RunIn):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO runs (id, input, conversation_id, turn_index, status, started_at, ended_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run.id,
                    run.input,
                    run.conversation_id,
                    run.turn_index,
                    run.status,
                    run.started_at,
                    run.ended_at,
                ),
            )
    return {"ok": True}


@app.post("/runs/{run_id}/end", status_code=200)
def end_run(run_id: str, body: RunEndIn):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE runs SET status = %s, ended_at = NOW()
                WHERE id = %s
                """,
                (body.status, run_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="run no encontrado")
    return {"ok": True}


@app.post("/spans", status_code=201)
def create_span(span: SpanIn):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO spans (id, run_id, parent_span_id, type, name, status, started_at, ended_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    span.id,
                    span.run_id,
                    span.parent_span_id,
                    span.type,
                    span.name,
                    span.status,
                    span.started_at,
                    span.ended_at,
                ),
            )
    return {"ok": True}


@app.post("/spans/{span_id}/end", status_code=200)
def end_span(span_id: str, body: SpanEndIn):
    with get_conn() as conn:
        with conn.cursor() as cur:
            if body.ended_at is not None:
                cur.execute(
                    """
                    UPDATE spans SET status = %s, ended_at = %s
                    WHERE id = %s
                    """,
                    (body.status, body.ended_at, span_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE spans SET status = %s, ended_at = NOW()
                    WHERE id = %s
                    """,
                    (body.status, span_id),
                )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="span no encontrado")
    return {"ok": True}


@app.post("/model_calls", status_code=201)
def create_model_call(model_call: ModelCallIn):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_calls (
                    span_id, model, input, output, input_tokens, output_tokens, purpose, context_metadata, started_at, ended_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    model_call.span_id,
                    model_call.model,
                    model_call.input,
                    model_call.output,
                    model_call.input_tokens,
                    model_call.output_tokens,
                    model_call.purpose,
                    psycopg2.extras.Json(model_call.context_metadata) if model_call.context_metadata is not None else None,
                    model_call.started_at,
                    model_call.ended_at,
                ),
            )
    return {"ok": True}


@app.post("/tool_calls", status_code=201)
def create_tool_call(tool_call: ToolCallIn):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tool_calls (
                    span_id, tool_name, arguments, result, owner_agent, purpose, started_at, ended_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    tool_call.span_id,
                    tool_call.tool_name,
                    json.dumps(tool_call.arguments),
                    tool_call.result,
                    tool_call.owner_agent,
                    tool_call.purpose,
                    tool_call.started_at,
                    tool_call.ended_at,
                ),
            )
    return {"ok": True}


@app.post("/memory_events", status_code=201)
def create_memory_event(memory_event: MemoryEventIn):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memory_events (
                    span_id, operation, query, results_count, owner_agent, purpose, started_at, ended_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    memory_event.span_id,
                    memory_event.operation,
                    memory_event.query,
                    memory_event.results_count,
                    memory_event.owner_agent,
                    memory_event.purpose,
                    memory_event.started_at,
                    memory_event.ended_at,
                ),
            )
    return {"ok": True}


@app.post("/decision_events", status_code=201)
def create_decision_event(decision_event: DecisionEventIn):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO decision_events (
                    span_id, actor, stage, input, available_tools, selected_tools, rationale, payload, started_at, ended_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    decision_event.span_id,
                    decision_event.actor,
                    decision_event.stage,
                    decision_event.input,
                    json.dumps(decision_event.available_tools),
                    json.dumps(decision_event.selected_tools),
                    decision_event.rationale,
                    json.dumps(decision_event.payload),
                    decision_event.started_at,
                    decision_event.ended_at,
                ),
            )
    return {"ok": True}


@app.post("/errors", status_code=201)
def create_error(error: ErrorIn):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO errors (span_id, error_type, message)
                VALUES (%s, %s, %s)
                """,
                (error.span_id, error.error_type, error.message),
            )
    return {"ok": True}


@app.get("/runs")
def list_runs():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, input, conversation_id, turn_index, status, started_at, ended_at
                FROM runs
                ORDER BY started_at DESC
                LIMIT 100
            """)
            return cur.fetchall()


@app.get("/runs/{run_id}/timeline")
def get_run_timeline(run_id: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM runs WHERE id = %s", (run_id,))
            run = cur.fetchone()
            if not run:
                raise HTTPException(status_code=404, detail="run no encontrado")

            cur.execute(
                "SELECT * FROM spans WHERE run_id = %s ORDER BY started_at ASC",
                (run_id,),
            )
            spans = cur.fetchall()
            model_calls: list[dict] = []
            tool_calls: list[dict] = []
            memory_events: list[dict] = []
            decision_events: list[dict] = []
            errors: list[dict] = []
            generic_events: list[dict] = []

            cur.execute(
                "SELECT * FROM events WHERE run_id = %s ORDER BY created_at ASC, id ASC",
                (run_id,),
            )
            generic_events = cur.fetchall()

            if spans:
                span_ids = [s["id"] for s in spans]
                placeholders = ",".join(["%s"] * len(span_ids))

                cur.execute(
                    f"SELECT * FROM model_calls WHERE span_id IN ({placeholders}) ORDER BY COALESCE(started_at, created_at) ASC, id ASC",
                    span_ids,
                )
                model_calls = cur.fetchall()

                cur.execute(
                    f"SELECT * FROM tool_calls WHERE span_id IN ({placeholders}) ORDER BY COALESCE(started_at, created_at) ASC, id ASC",
                    span_ids,
                )
                tool_calls = cur.fetchall()

                cur.execute(
                    f"SELECT * FROM memory_events WHERE span_id IN ({placeholders}) ORDER BY COALESCE(started_at, created_at) ASC, id ASC",
                    span_ids,
                )
                memory_events = cur.fetchall()

                cur.execute(
                    f"SELECT * FROM decision_events WHERE span_id IN ({placeholders}) ORDER BY COALESCE(started_at, created_at) ASC, id ASC",
                    span_ids,
                )
                decision_events = cur.fetchall()

                cur.execute(
                    f"SELECT * FROM errors WHERE span_id IN ({placeholders}) ORDER BY created_at ASC, id ASC",
                    span_ids,
                )
                errors = cur.fetchall()

    timeline = _build_timeline(run, spans, model_calls, tool_calls, memory_events, decision_events, errors, generic_events)
    token_summary = _summarize_turn_tokens(str(run.get("input") or ""), model_calls, decision_events)
    return {"run": run, "timeline": timeline, "token_summary": token_summary}


def _build_timeline(
    run: dict,
    spans: list[dict],
    model_calls: list[dict],
    tool_calls: list[dict],
    memory_events: list[dict],
    decision_events: list[dict],
    errors: list[dict],
    generic_events: list[dict],
) -> list[dict]:
    span_by_id = {span["id"]: span for span in spans}
    span_depths = _span_depths(spans)
    events: list[dict[str, Any]] = []

    def add_event(
        event_id: str,
        kind: str,
        event_type: str,
        title: str,
        subtitle: str,
        span_id: str | None,
        actor: str,
        source_actor: str,
        target_actor: str,
        relation: str,
        started_at: datetime | None,
        ended_at: datetime | None,
        created_at: datetime | None,
        payload: dict,
        description: str | None = None,
        status: str | None = None,
        event_role: str = "annotation",
        content: dict | None = None,
        metrics: dict | None = None,
        visibility: str = "public",
    ) -> None:
        events.append(
            {
                "id": event_id,
                "sequence": 0,
                "kind": kind,
                "event_type": event_type,
                "title": title,
                "subtitle": subtitle,
                "description": description,
                "span_id": span_id,
                "depth": span_depths.get(span_id or "", 0),
                "actor": actor,
                "actor_type": _actor_type(actor),
                "source_actor": source_actor,
                "source_actor_type": _actor_type(source_actor),
                "target_actor": target_actor,
                "target_actor_type": _actor_type(target_actor),
                "relation": relation,
                "event_role": event_role,
                "visibility": visibility,
                "status": status,
                "started_at": started_at,
                "ended_at": ended_at,
                "created_at": created_at,
                "duration_ms": _duration_ms(started_at, ended_at),
                "content": content or {},
                "metrics": metrics or {},
                "payload": payload,
            }
        )

    add_event(
        f"run:{run['id']}:started",
        "input",
        "run_started",
        "Mensaje del usuario",
        "entrada del run",
        None,
        "User",
        "User",
        "MainAgent",
        "envía mensaje",
        run.get("started_at"),
        None,
        run.get("started_at"),
        {"run": run},
        description=str(run.get("input") or ""),
        status=run.get("status"),
        event_role="call",
        content={"input": str(run.get("input") or "")},
    )

    for span_row in spans:
        if span_row.get("type") == "memory":
            continue
        parent_actor = _span_actor(span_by_id.get(span_row.get("parent_span_id"))) if span_row.get("parent_span_id") else "MainAgent"
        actor = _span_actor(span_row)
        add_event(
            f"span:{span_row['id']}:started",
            "span",
            "span_started",
            f"Abre span {actor}",
            f"{span_row['type']} · {span_row['status']}",
            span_row["id"],
            actor,
            parent_actor,
            actor,
            "abre span",
            span_row.get("started_at"),
            None,
            span_row.get("started_at"),
            {"span": span_row},
            description=f"Inicio del tramo observable `{span_row['name']}`.",
            status=span_row.get("status"),
            event_role="annotation",
        )

    for row in decision_events:
        actor = row.get("actor") or _span_actor(span_by_id.get(row["span_id"]))
        source_actor, target_actor = _decision_flow(row, actor)
        selected = _as_list(row.get("selected_tools"))
        available = _as_list(row.get("available_tools"))
        stage = row["stage"]
        is_memory_stage = stage in {"memory_observation", "memory_persistence"}
        payload = row.get("payload") or {}
        results_count = payload.get("results_count")
        memory_title = {
            "memory_observation": "Memoria · observación",
            "memory_persistence": "Memoria · persistencia",
        }.get(stage, stage)
        memory_subtitle = (
            f"determinista · {actor} · {results_count} resultado(s)"
            if is_memory_stage and results_count is not None
            else f"determinista · {actor}"
            if is_memory_stage
            else f"{actor} · {len(selected)} seleccionada(s) de {len(available)} disponible(s)"
        )
        add_event(
            f"decision:{row['id']}",
            "decision",
            "decision_event",
            memory_title if is_memory_stage else stage,
            memory_subtitle,
            row["span_id"],
            actor,
            source_actor,
            target_actor,
            _decision_relation(stage),
            row.get("started_at") or row.get("created_at"),
            row.get("ended_at"),
            row.get("created_at"),
            {"decision": row},
            description=_decision_description(row),
            event_role=_decision_event_role(stage),
            content=_decision_content(row),
            metrics={},
            visibility=str((row.get("payload") or {}).get("visibility") or "public"),
        )

    for row in model_calls:
        requester = _owning_agent(row["span_id"], span_by_id)
        llm_actor = _llm_actor(row.get("purpose"))
        total_tokens = (row.get("input_tokens") or 0) + (row.get("output_tokens") or 0)
        context_meta = row.get("context_metadata") or {}
        if isinstance(context_meta, str):
            context_meta = json.loads(context_meta)
        add_event(
            f"model:{row['id']}",
            "model",
            "model_call",
            row["model"],
            f"{row.get('purpose') or 'llm'} · {total_tokens} tokens",
            row["span_id"],
            llm_actor,
            requester,
            llm_actor,
            "llama modelo",
            row.get("started_at") or row.get("created_at"),
            row.get("ended_at"),
            row.get("created_at"),
            {"model_call": row, "total_tokens": total_tokens, "requester_agent": requester},
            description=_truncate(row.get("output") or row.get("input") or "", 240),
            event_role="execution",
            content={"input": row.get("input"), "output": row.get("output")},
            metrics={
                "input_tokens": row.get("input_tokens") or 0,
                "output_tokens": row.get("output_tokens") or 0,
                "total_tokens": total_tokens,
                "context_window": context_meta.get("context_window") or 0,
                "window_usage_pct": context_meta.get("window_usage_pct") or 0,
            },
        )

    for row in tool_calls:
        owner = row.get("owner_agent") or _owning_agent(row["span_id"], span_by_id)
        add_event(
            f"tool:{row['id']}",
            "tool",
            "tool_call",
            row["tool_name"],
            f"{row.get('purpose') or 'tool'} · owner {owner}",
            row["span_id"],
            row["tool_name"],
            owner,
            row["tool_name"],
            "ejecuta código",
            row.get("started_at") or row.get("created_at"),
            row.get("ended_at"),
            row.get("created_at"),
            {"tool_call": row},
            description=_truncate(str(row.get("result") or ""), 240),
            event_role="execution",
            content={"input": row.get("arguments"), "output": row.get("result")},
        )

    for row in memory_events:
        owner = row.get("owner_agent") or _owning_agent(row["span_id"], span_by_id)
        is_save = row.get("operation") == "save"
        operation = str(row.get("operation") or "memory")
        results_count = row.get("results_count") or 0
        add_event(
            f"memory:{row['id']}",
            "memory",
            "memory_event",
            f"Memoria · {operation}",
            f"determinista · {owner} · {results_count} resultado(s)",
            row["span_id"],
            MEMORY_PLUGIN_ACTOR,
            owner,
            MEMORY_PLUGIN_ACTOR,
            "persiste en plugin" if is_save else "consulta plugin",
            row.get("started_at") or row.get("created_at"),
            row.get("ended_at"),
            row.get("created_at"),
            {
                "memory_event": row,
                "owner_agent": owner,
                "provider": "mnemo",
                "invocation": "deterministic",
            },
            description=str(row.get("query") or ""),
            event_role="execution",
            content={
                "input": row.get("query"),
                "output": {"results_count": results_count},
                "provider": "mnemo",
                "invocation": "deterministic",
            },
            metrics={"results_count": results_count},
        )

    for row in errors:
        actor = _span_actor(span_by_id.get(row["span_id"]))
        add_event(
            f"error:{row['id']}",
            "error",
            "error_event",
            row["error_type"],
            actor,
            row["span_id"],
            actor,
            actor,
            "Observability API",
            "registra error",
            row.get("created_at"),
            None,
            row.get("created_at"),
            {"error": row},
            description=row.get("message"),
            event_role="annotation",
            content={"error": row.get("message")},
        )

    for row in generic_events:
        add_event(
            f"event:{row['id']}",
            "event",
            str(row.get("event_type") or "event"),
            str(row.get("event_type") or "event"),
            "evento genérico",
            None,
            "Runtime",
            "Runtime",
            "Observability API",
            "registra evento",
            row.get("created_at"),
            None,
            row.get("created_at"),
            {"event": row},
            description=_truncate(json.dumps(row.get("payload") or {}, ensure_ascii=False), 240),
            event_role="annotation",
            content={"payload": row.get("payload") or {}},
        )

    for span_row in spans:
        if span_row.get("type") == "memory":
            continue
        actor = _span_actor(span_row)
        add_event(
            f"span:{span_row['id']}:ended",
            "span",
            "span_ended",
            f"Cierra span {actor}",
            f"{span_row['type']} · {span_row['status']}",
            span_row["id"],
            actor,
            actor,
            _span_actor(span_by_id.get(span_row.get("parent_span_id"))) if span_row.get("parent_span_id") else "MainAgent",
            "cierra span",
            span_row.get("started_at"),
            span_row.get("ended_at"),
            span_row.get("ended_at") or span_row.get("started_at"),
            {"span": span_row},
            description=f"Fin del tramo observable `{span_row['name']}`.",
            status=span_row.get("status"),
            event_role="annotation",
        )

    if run.get("ended_at"):
        final_response = _find_final_response(decision_events, model_calls)
        add_event(
            f"run:{run['id']}:ended",
            "output",
            "run_ended",
            "Respuesta final",
            run["status"],
            None,
            "MainAgent",
            "MainAgent",
            "User",
            "devuelve respuesta",
            run.get("started_at"),
            run.get("ended_at"),
            run.get("ended_at"),
            {"run": run, "response": final_response},
            description=_truncate(final_response or "Run finalizado sin respuesta final registrada.", 300),
            status=run.get("status"),
            event_role="response",
            content={"response": final_response},
        )

    events.sort(key=lambda event: (_event_time(event), _event_sort_weight(event)))
    for index, event in enumerate(events, start=1):
        event["sequence"] = index
    return events


def _span_depths(spans: list[dict]) -> dict[str, int]:
    by_id = {span["id"]: span for span in spans}
    depths: dict[str, int] = {}

    def depth(span_id: str) -> int:
        if span_id in depths:
            return depths[span_id]
        span = by_id.get(span_id)
        parent = span.get("parent_span_id") if span else None
        depths[span_id] = 0 if not parent else depth(parent) + 1
        return depths[span_id]

    for span in spans:
        depth(span["id"])
    return depths


def _span_actor(span: dict | None) -> str:
    if not span:
        return "Runtime"
    span_type = str(span.get("type") or "")
    name = str(span.get("name") or "Runtime")
    if span_type == "model":
        return _llm_actor(name.removeprefix("llm:"))
    if span_type == "tool":
        return name.removeprefix("tool:")
    if span_type == "memory":
        return "Memory"
    return "".join(part.capitalize() for part in name.split("_"))


def _owning_agent(span_id: str, span_by_id: dict[str, dict]) -> str:
    span = span_by_id.get(span_id)
    if not span:
        return "Runtime"
    if span.get("type") == "agent":
        return _span_actor(span)
    parent_span_id = span.get("parent_span_id")
    if not parent_span_id:
        return _span_actor(span)
    return _owning_agent(parent_span_id, span_by_id)


def _actor_type(actor: str | None) -> str:
    if not actor:
        return "runtime"
    normalized = actor.casefold()
    if normalized == "user":
        return "user"
    if normalized.startswith("llm"):
        return "llm"
    if normalized.startswith("memoria") or normalized in {"memory", "vectorstore"}:
        return "memory"
    if normalized in {"calculator", "clock", "web_search", "file_reader"}:
        return "tool"
    if actor.endswith("Agent"):
        return "agent" if actor == "MainAgent" else "subagent"
    return "runtime"


def _decision_flow(row: dict, actor: str) -> tuple[str, str]:
    stage = str(row.get("stage") or "")
    payload = row.get("payload") or {}
    selected = _as_list(row.get("selected_tools"))
    target_agent = payload.get("target_agent")
    tool_name = payload.get("tool_name") or payload.get("tool") or (selected[0] if selected else None)

    if stage == "message_received":
        return "User", "MainAgent"
    if stage == "conversation_turn_started":
        return "User", "MainAgent"
    if stage == "context_window_evaluated":
        return "MainAgent", "MainAgent"
    if stage in {"context_summarized", "context_truncated"}:
        return "MainAgent", "MainAgent"
    if stage == "planning_context_received":
        return "MainAgent", "PlannerAgent"
    if stage in {"planning_assessment_request", "planning_decision_request"}:
        return "PlannerAgent", "LLM Planner"
    if stage in {"planning_assessment_response", "planning_decision_response"}:
        return "LLM Planner", "PlannerAgent"
    if stage in {
        "planning_context_enrichment",
        "planning_assessment_parse_repair",
        "planning_decision_parse_repair",
        "planning_decision_verified",
        "hidden_reasoning_generated",
        "planning_finalized",
    }:
        return "PlannerAgent", "PlannerAgent"
    if stage == "planner_request":
        return actor, "LLM Planner"
    if stage in {"planner_response", "planner_observation"}:
        return "LLM Planner", "MainAgent" if actor == "LLM Planner" else actor
    if stage == "subagent_call_request":
        return "MainAgent", str(target_agent or _selected_agent(selected) or "SubAgent")
    if stage == "subagent_call_response":
        if actor != "MainAgent":
            return actor, "MainAgent"
        if payload.get("source_agent"):
            return str(payload["source_agent"]), "MainAgent"
        subagents = payload.get("subagents") if isinstance(payload.get("subagents"), list) else []
        return str(payload.get("owner_agent") or ", ".join(subagents) or "SubAgent"), "MainAgent"
    if stage == "subagent_received":
        return "MainAgent", actor
    if stage == "tool_call_request":
        return actor, str(tool_name or "Tool")
    if stage == "tool_selection":
        return actor, actor
    if stage == "tool_observation":
        return str(tool_name or "Tool"), actor
    if stage == "model_call_request":
        if actor == "PlannerAgent":
            return actor, "LLM Planner"
        return actor, "LLM"
    if stage == "model_observation":
        return "LLM", actor
    if stage == "final_model_request":
        return "MainAgent", "LLM Final"
    if stage in {"final_model_response", "final_model_observation"}:
        return "LLM Final", "MainAgent"
    if stage == "final_response":
        return "MainAgent", "User"
    if stage == "memory_observation":
        return MEMORY_PLUGIN_ACTOR, actor
    if stage == "memory_persistence":
        return actor, MEMORY_PLUGIN_ACTOR
    return actor, actor


def _decision_event_role(stage: str) -> str:
    if stage.endswith("_request") or stage in {"message_received", "subagent_received", "planning_context_received", "conversation_turn_started"}:
        return "call"
    if stage.endswith("_response") or stage.endswith("_observation") or stage in {"final_response", "planning_finalized"}:
        return "response"
    if stage in {
        "tool_selection",
        "decision_validation",
        "catalog_read",
        "tool_catalog_read",
        "memory_persistence",
        "planning_context_enrichment",
        "planning_assessment_parse_repair",
        "planning_decision_parse_repair",
        "planning_decision_verified",
        "hidden_reasoning_generated",
    }:
        return "annotation"
    return "annotation"


def _decision_description(row: dict) -> str:
    stage = str(row.get("stage") or "")
    payload = row.get("payload") or {}
    if stage in {"planner_response", "planner_observation", "final_model_response", "final_model_observation"}:
        output = payload.get("output")
        if output:
            return _truncate(str(output), 300)
    if stage == "final_response":
        response = payload.get("response")
        if response:
            return _truncate(str(response), 300)
    if payload.get("hidden_reasoning"):
        return _truncate(f"Razonamiento oculto: {len(payload.get('hidden_reasoning') or [])} pasos registrados.", 300)
    return str(row.get("rationale") or "")


def _decision_content(row: dict) -> dict:
    stage = str(row.get("stage") or "")
    payload = row.get("payload") or {}
    content = {"rationale": row.get("rationale")}
    if "prompt" in payload:
        content["input"] = payload.get("prompt")
    if "output" in payload:
        content["output"] = payload.get("output")
    if "plan" in payload:
        content["output"] = payload.get("plan")
    if "assessment" in payload:
        content["assessment"] = payload.get("assessment")
    if "decision" in payload:
        content["decision"] = payload.get("decision")
    if "planning_context" in payload:
        content["planning_context"] = payload.get("planning_context")
    if "hidden_reasoning" in payload:
        content["hidden_reasoning"] = payload.get("hidden_reasoning")
        content["visibility"] = payload.get("visibility", "hidden")
    if "selected_action" in payload:
        content["selected_action"] = payload.get("selected_action")
    if stage == "final_response" and "response" in payload:
        content["response"] = payload.get("response")
    if stage in {"final_model_response", "final_model_observation"} and "output" in payload:
        content["response"] = payload.get("output")
    return content


def _find_final_response(decision_events: list[dict], model_calls: list[dict]) -> str:
    candidates: list[tuple[float, str]] = []
    for row in decision_events:
        payload = row.get("payload") or {}
        response = None
        if row.get("stage") == "final_response":
            response = payload.get("response")
        elif row.get("stage") == "final_model_response":
            response = payload.get("output")
        if response:
            candidates.append((_row_time(row), str(response)))

    for row in model_calls:
        if row.get("purpose") == "final_response" and row.get("output"):
            candidates.append((_row_time(row), str(row.get("output"))))

    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: item[0])[-1][1]


def _row_time(row: dict) -> float:
    for key in ("ended_at", "started_at", "created_at"):
        value = row.get(key)
        if isinstance(value, datetime):
            return value.timestamp()
    return 0.0


def _selected_agent(selected: list[str]) -> str | None:
    if not selected:
        return None
    mapping = {
        "math_agent": "MathAgent",
        "time_agent": "TimeAgent",
        "researcher_agent": "ResearcherAgent",
        "writer_agent": "WriterAgent",
    }
    return mapping.get(selected[0], selected[0])


def _llm_actor(purpose: str | None) -> str:
    mapping = {
        "planner": "LLM Planner",
        "planner_assessment": "LLM Planner",
        "planner_decision": "LLM Planner",
        "final_response": "LLM Final",
        "research_synthesis": "LLM Synthesis",
        "writer_draft": "LLM Draft",
    }
    return mapping.get(str(purpose or ""), "LLM")


def _decision_relation(stage: str) -> str:
    return {
        "message_received": "recibe",
        "catalog_read": "consulta catálogo",
        "tool_catalog_read": "consulta tools propias",
        "tool_selection": "selecciona tool propia",
        "planner_request": "pregunta al planner",
        "planner_response": "devuelve decisión",
        "planner_observation": "devuelve decisión",
        "planning_context_received": "recibe contexto",
        "conversation_turn_started": "abre turno",
        "context_window_evaluated": "evalúa ventana",
        "context_summarized": "resume contexto",
        "context_truncated": "trunca contexto",
        "planning_assessment_request": "solicita assessment",
        "planning_assessment_response": "devuelve assessment",
        "planning_assessment_parse_repair": "repara assessment",
        "planning_context_enrichment": "enriquece contexto",
        "planning_decision_request": "solicita decisión final",
        "planning_decision_response": "devuelve decisión final",
        "planning_decision_parse_repair": "repara decisión final",
        "planning_decision_verified": "verifica decisión",
        "hidden_reasoning_generated": "genera razonamiento oculto",
        "planning_finalized": "finaliza planificación",
        "decision_validation": "valida decisión",
        "fallback_event": "fallback",
        "subagent_call_request": "delega subagente",
        "subagent_received": "recibe delegación",
        "subagent_call_response": "devuelve observación",
        "direct_answer_selected": "responde directo",
        "tool_call_request": "solicita tool",
        "tool_observation": "devuelve resultado",
        "model_call_request": "solicita modelo",
        "model_observation": "devuelve salida modelo",
        "final_model_request": "solicita respuesta final",
        "final_model_response": "devuelve respuesta final",
        "final_model_observation": "devuelve respuesta final",
        "final_response": "responde",
        "memory_observation": "devuelve resultados del plugin",
        "memory_persistence": "confirma persistencia en plugin",
    }.get(stage, "registra decisión")


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    return []


def _duration_ms(started_at: datetime | None, ended_at: datetime | None) -> int | None:
    if not started_at or not ended_at:
        return None
    return int((ended_at - started_at).total_seconds() * 1000)


def _event_time(event: dict) -> float:
    if event.get("event_type") in {"span_ended", "run_ended"}:
        value = event.get("ended_at") or event.get("created_at")
        if isinstance(value, datetime):
            return value.timestamp()
    for key in ("started_at", "created_at", "ended_at"):
        value = event.get(key)
        if isinstance(value, datetime):
            return value.timestamp()
    return 0.0


def _event_sort_weight(event: dict) -> int:
    order = {
        "run_started": 0,
        "span_started": 1,
        "decision_event": 2,
        "model_call": 3,
        "tool_call": 3,
        "memory_event": 3,
        "error_event": 4,
        "span_ended": 8,
        "run_ended": 9,
    }
    return order.get(str(event.get("event_type")), 5)


def _truncate(value: str, max_length: int) -> str:
    return value if len(value) <= max_length else f"{value[: max_length - 1]}…"


_FINAL_PURPOSE = "final_response"


def _estimate_tokens(text: str) -> int:
    trimmed = text.strip()
    if not trimmed:
        return 0
    return max(1, (len(trimmed) + 3) // 4)


def _breakdown_value(metadata: dict | None, key: str) -> int:
    if not metadata:
        return 0
    breakdown = metadata.get("breakdown")
    if not isinstance(breakdown, dict):
        return 0
    value = breakdown.get(key)
    return int(value) if isinstance(value, (int, float)) else 0


def _context_from_run(model_calls: list[dict], decision_events: list[dict]) -> dict[str, Any]:
    for row in decision_events:
        if row.get("stage") != "context_window_evaluated":
            continue
        payload = row.get("payload") or {}
        return {
            "context_window": 0,
            "remaining_input_tokens": payload.get("remaining_input_tokens"),
            "output_reserve_tokens": payload.get("output_reserve_tokens"),
        }

    for row in model_calls:
        metadata = row.get("context_metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        if not isinstance(metadata, dict):
            continue
        return {
            "context_window": metadata.get("context_window") or 0,
            "remaining_input_tokens": metadata.get("remaining_input_tokens"),
            "output_reserve_tokens": metadata.get("output_reserve_tokens"),
        }

    return {
        "context_window": 0,
        "remaining_input_tokens": None,
        "output_reserve_tokens": None,
    }


def _summarize_turn_tokens(user_input: str, model_calls: list[dict], decision_events: list[dict]) -> dict[str, Any]:
    context = _context_from_run(model_calls, decision_events)
    user_input_tokens = 0
    final_output_tokens = 0
    internal_input_tokens = 0
    internal_output_tokens = 0
    context_window = int(context.get("context_window") or 0)

    for row in model_calls:
        purpose = str(row.get("purpose") or "")
        input_tokens = int(row.get("input_tokens") or 0)
        output_tokens = int(row.get("output_tokens") or 0)
        metadata = row.get("context_metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        if isinstance(metadata, dict) and metadata.get("context_window"):
            context_window = int(metadata["context_window"])

        if purpose == _FINAL_PURPOSE:
            final_output_tokens = output_tokens
            user_input_tokens = _breakdown_value(metadata, "user_message") or _estimate_tokens(user_input)
            continue

        internal_input_tokens += input_tokens
        internal_output_tokens += output_tokens

    if user_input_tokens == 0:
        user_input_tokens = _estimate_tokens(user_input)

    return {
        "user_input_tokens": user_input_tokens,
        "final_output_tokens": final_output_tokens,
        "internal_input_tokens": internal_input_tokens,
        "internal_output_tokens": internal_output_tokens,
        "context_window": context_window,
        "remaining_input_tokens": context.get("remaining_input_tokens"),
        "output_reserve_tokens": context.get("output_reserve_tokens"),
    }
