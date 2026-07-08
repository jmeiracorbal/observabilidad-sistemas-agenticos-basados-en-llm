import { useEffect, useMemo, useRef, useState } from 'react';

import { getRunTimeline, invokeAgentStream } from '../api';
import { config } from '../config';
import { ConversationContextBar } from './ConversationContextBar';
import { LiveStreamCard } from './LiveStreamCard';
import type { ModelCall, TimelineItem, TurnTokenSummary } from '../types';
import type { InvokeStreamState, LlmStreamState } from '../types-stream';

const PURPOSE_LABELS: Record<string, string> = {
  planner_assessment: 'análisis',
  planner_decision: 'decisión',
  final_response: 'Respuesta',
  research_synthesis: 'Investigación',
  writer_draft: 'Redacción',
};

const DECISION_PURPOSES = new Set(['planner_assessment', 'planner_decision']);

const STREAM_ORDER = [
  'planner_assessment',
  'planner_decision',
  'research_synthesis',
  'writer_draft',
  'final_response',
];

function initialState(): InvokeStreamState {
  return { status: 'idle', llmStreams: {} };
}

function upsertStream(
  streams: Record<string, LlmStreamState>,
  purpose: string,
  patch: Partial<LlmStreamState>,
): Record<string, LlmStreamState> {
  const current = streams[purpose] ?? { purpose, text: '', status: 'idle' };
  return { ...streams, [purpose]: { ...current, ...patch, purpose } };
}

function sortStreams(streams: LlmStreamState[]): LlmStreamState[] {
  return [...streams].sort((left, right) => {
    const leftIndex = STREAM_ORDER.indexOf(left.purpose);
    const rightIndex = STREAM_ORDER.indexOf(right.purpose);
    return (leftIndex === -1 ? STREAM_ORDER.length : leftIndex) - (rightIndex === -1 ? STREAM_ORDER.length : rightIndex);
  });
}

function completePriorStreams(
  streams: Record<string, LlmStreamState>,
  purpose: string,
): Record<string, LlmStreamState> {
  const purposeIndex = STREAM_ORDER.indexOf(purpose);
  if (purposeIndex <= 0) {
    return streams;
  }

  let next = streams;
  for (const earlierPurpose of STREAM_ORDER.slice(0, purposeIndex)) {
    const stream = next[earlierPurpose];
    if (stream?.status === 'streaming') {
      next = upsertStream(next, earlierPurpose, { status: 'completed' });
    }
  }
  return next;
}

function finalizeStreamingStreams(
  streams: Record<string, LlmStreamState>,
): Record<string, LlmStreamState> {
  let next = streams;
  for (const [purpose, stream] of Object.entries(streams)) {
    if (stream.status !== 'streaming') {
      continue;
    }
    next = upsertStream(next, purpose, { status: 'completed' });
  }
  return next;
}

function modelCallFromTimelineItem(item: TimelineItem): ModelCall | undefined {
  const payload = item.payload as { model_call?: ModelCall } | undefined;
  return payload?.model_call;
}

function hydrateStreamsFromTimeline(
  streams: Record<string, LlmStreamState>,
  timeline: TimelineItem[],
): Record<string, LlmStreamState> {
  let next = streams;
  for (const item of timeline) {
    if (item.kind !== 'model') {
      continue;
    }
    const call = modelCallFromTimelineItem(item);
    if (!call?.purpose) {
      continue;
    }
    const existing = next[call.purpose];
    if (existing?.text.trim()) {
      continue;
    }
    next = upsertStream(next, call.purpose, {
      model: call.model,
      text: call.output || '',
      status: 'completed',
      input_tokens: call.input_tokens ?? item.metrics?.input_tokens,
      output_tokens: call.output_tokens ?? item.metrics?.output_tokens,
    });
  }
  return next;
}

export function LiveInvokePanel({
  activeConversationId,
  sessionKey,
  contextSummary,
  onConversationChanged,
  onRunningChange,
  onRunStarted,
  onRunCompleted,
}: {
  activeConversationId?: string;
  sessionKey: number;
  contextSummary?: TurnTokenSummary | null;
  onConversationChanged: (conversationId: string | undefined) => void;
  onRunningChange: (running: boolean) => void;
  onRunStarted: (runId: string) => void;
  onRunCompleted: (runId: string) => void;
}) {
  const [message, setMessage] = useState('');
  const [state, setState] = useState<InvokeStreamState>(initialState);
  const [decisionsOpen, setDecisionsOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const streamEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    streamEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [state.llmStreams, state.status]);

  useEffect(() => {
    onRunningChange(state.status === 'running');
  }, [state.status, onRunningChange]);

  useEffect(() => {
    abortRef.current?.abort();
    setState(initialState());
    setDecisionsOpen(false);
    setMessage('');
  }, [sessionKey]);

  useEffect(() => {
    if (state.status === 'running') {
      setDecisionsOpen(true);
    }
  }, [state.status]);

  async function handleSubmit() {
    const trimmed = message.trim();
    if (!trimmed || state.status === 'running') {
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setState({ status: 'running', message: trimmed, llmStreams: {} });
    setDecisionsOpen(true);
    setMessage('');

    try {
      await invokeAgentStream(
        trimmed,
        activeConversationId,
        (event, data) => {
          if (event === 'run_started') {
            const runId = String(data.run_id);
            const conversationId = String(data.conversation_id ?? '');
            const turnIndex = Number(data.turn_index ?? 0);
            setState((current) => ({
              ...current,
              runId,
              conversationId,
              turnIndex,
              remainingInputTokens: Number(data.remaining_input_tokens ?? 0),
              outputReserveTokens: Number(data.output_reserve_tokens ?? 0),
            }));
            if (conversationId) {
              onConversationChanged(conversationId);
            }
            onRunStarted(runId);
            return;
          }

          if (event === 'llm_started') {
            const purpose = String(data.purpose);
            setState((current) => ({
              ...current,
              llmStreams: upsertStream(completePriorStreams(current.llmStreams, purpose), purpose, {
                model: String(data.model ?? ''),
                text: '',
                status: 'streaming',
              }),
            }));
            return;
          }

          if (event === 'llm_delta') {
            const purpose = String(data.purpose);
            setState((current) => ({
              ...current,
              llmStreams: upsertStream(current.llmStreams, purpose, {
                text: String(data.text ?? ''),
                status: 'streaming',
              }),
            }));
            return;
          }

          if (event === 'llm_completed') {
            const purpose = String(data.purpose);
            setState((current) => ({
              ...current,
              llmStreams: upsertStream(completePriorStreams(current.llmStreams, purpose), purpose, {
                text: String(data.output ?? ''),
                status: 'completed',
                input_tokens: Number(data.input_tokens ?? 0),
                output_tokens: Number(data.output_tokens ?? 0),
              }),
            }));
            return;
          }

          if (event === 'run_completed') {
            const runId = String(data.run_id);
            const conversationId = String(data.conversation_id ?? '');
            const response = String(data.response ?? '');
            setState((current) => ({
              ...current,
              status: 'completed',
              runId,
              conversationId,
              turnIndex: Number(data.turn_index ?? current.turnIndex ?? 0),
              response,
              llmStreams: finalizeStreamingStreams(current.llmStreams),
            }));
            if (conversationId) {
              onConversationChanged(conversationId);
            }
            onRunCompleted(runId);
            void getRunTimeline(runId)
              .then((timeline) => {
                setState((current) => {
                  if (current.runId !== runId) {
                    return current;
                  }
                  return {
                    ...current,
                    llmStreams: hydrateStreamsFromTimeline(current.llmStreams, timeline.timeline),
                  };
                });
              })
              .catch(() => undefined);
            return;
          }

          if (event === 'run_failed') {
            setState((current) => ({
              ...current,
              status: 'failed',
              error: String(data.error ?? 'fallo desconocido'),
              llmStreams: finalizeStreamingStreams(current.llmStreams),
            }));
          }
        },
        controller.signal,
      );
    } catch (error) {
      if (controller.signal.aborted) {
        return;
      }
      setState((current) => ({
        ...current,
        status: 'failed',
        error: error instanceof Error ? error.message : 'no se pudo invocar al agente',
      }));
    }
  }

  const streamEntries = sortStreams(Object.values(state.llmStreams));
  const decisionStreams = streamEntries.filter((stream) => DECISION_PURPOSES.has(stream.purpose));
  const visibleStreams = streamEntries.filter((stream) => !DECISION_PURPOSES.has(stream.purpose));
  const responseStream = visibleStreams.find((stream) => stream.purpose === 'final_response');
  const pipelineStreams = visibleStreams.filter((stream) => stream.purpose !== 'final_response');
  const decisionsStreaming = decisionStreams.some((stream) => stream.status === 'streaming');

  const conversationContext = useMemo<TurnTokenSummary>(() => {
    const base = contextSummary ?? {
      user_input_tokens: 0,
      final_output_tokens: 0,
      internal_input_tokens: 0,
      internal_output_tokens: 0,
      context_window: config.contextWindow,
      remaining_input_tokens: null,
      output_reserve_tokens: null,
    };

    const liveOutputTokens = responseStream?.output_tokens ?? 0;

    if (state.remainingInputTokens !== undefined && state.outputReserveTokens !== undefined) {
      return {
        ...base,
        context_window: base.context_window || config.contextWindow,
        remaining_input_tokens: state.remainingInputTokens,
        output_reserve_tokens: state.outputReserveTokens,
        final_output_tokens: Math.max(base.final_output_tokens, liveOutputTokens),
      };
    }

    return {
      ...base,
      context_window: base.context_window || config.contextWindow,
      remaining_input_tokens: base.remaining_input_tokens,
      output_reserve_tokens: base.output_reserve_tokens,
      final_output_tokens: Math.max(base.final_output_tokens, liveOutputTokens),
    };
  }, [contextSummary, state.remainingInputTokens, state.outputReserveTokens, responseStream?.output_tokens]);

  return (
    <section className="panel live-invoke-panel">
      <ConversationContextBar summary={conversationContext} />
      <div className="live-invoke-panel__body">
      <p className="live-invoke-meta muted">Turno {state.turnIndex ?? 0}</p>

      <div className="live-invoke-compose">
        <textarea
          className="live-invoke-input"
          rows={2}
          value={message}
          placeholder="Escribe tu mensaje…"
          disabled={state.status === 'running'}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void handleSubmit();
            }
          }}
        />
        <button
          className="live-invoke-submit"
          type="button"
          disabled={!message.trim() || state.status === 'running'}
          onClick={() => void handleSubmit()}
        >
          {state.status === 'running' ? '…' : 'Enviar'}
        </button>
      </div>

      {state.error && <div className="alert alert-error">{state.error}</div>}

      {(state.status === 'running' || streamEntries.length > 0) && (
        <div className="live-stream-stack">
          {decisionStreams.length > 0 && (
            <details
              className="live-stream-decisions"
              open={decisionsOpen}
              onToggle={(event) => setDecisionsOpen(event.currentTarget.open)}
            >
              <summary className="live-stream-decisions__summary">
                <span>Planificación</span>
                <span className="muted">
                  {decisionStreams.length} paso(s)
                  {decisionsStreaming ? ' · en curso' : ''}
                </span>
              </summary>
              {decisionsOpen && (
                <div className="live-stream-decisions__list live-stream-decisions__list--scroll custom-scroll">
                  {decisionStreams.map((stream) => (
                    <LiveStreamCard
                      key={stream.purpose}
                      stream={stream}
                      label={PURPOSE_LABELS[stream.purpose] ?? stream.purpose}
                      lazy
                    />
                  ))}
                </div>
              )}
            </details>
          )}

          {pipelineStreams.map((stream) => (
            <LiveStreamCard
              key={stream.purpose}
              stream={stream}
              label={PURPOSE_LABELS[stream.purpose] ?? stream.purpose}
            />
          ))}

          {responseStream && (
            <LiveStreamCard
              key={responseStream.purpose}
              stream={responseStream}
              label={PURPOSE_LABELS[responseStream.purpose] ?? responseStream.purpose}
            />
          )}
          <div ref={streamEndRef} />
        </div>
      )}
      </div>
    </section>
  );
}
