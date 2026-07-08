import type { LlmStreamState } from '../types-stream';
import type { ModelCall, TimelineItem } from '../types';
import { extractAutorepairFlows, type AutorepairFlow } from './planning';

const FINAL_RESPONSE_PURPOSES = new Set(['final_response', 'final_response_retry']);

const PURPOSE_ORDER = ['final_response', 'final_response_retry'];

function modelCallFromItem(item: TimelineItem): ModelCall | undefined {
  const payload = item.payload as { model_call?: ModelCall } | undefined;
  return payload?.model_call;
}

function decisionFromItem(item: TimelineItem) {
  const payload = item.payload as { decision?: { stage?: string; payload?: Record<string, unknown> } } | undefined;
  return payload?.decision;
}

function flowStage(item: TimelineItem): string | undefined {
  const decision = decisionFromItem(item);
  if (decision?.stage) {
    return decision.stage;
  }
  return item.title;
}

function flowPayload(item: TimelineItem): Record<string, unknown> {
  const decision = decisionFromItem(item);
  return (decision?.payload ?? item.content ?? {}) as Record<string, unknown>;
}

export interface RetryFlow {
  phase: string;
  conflict: TimelineItem;
  decision: TimelineItem;
  applied: TimelineItem;
}

export function extractFinalResponseStreams(timeline: TimelineItem[]): LlmStreamState[] {
  const streams: LlmStreamState[] = [];

  for (const item of timeline) {
    if (item.kind !== 'model') {
      continue;
    }
    const call = modelCallFromItem(item);
    if (!call?.purpose || !FINAL_RESPONSE_PURPOSES.has(call.purpose)) {
      continue;
    }
    const completed = Boolean(call.output) || item.status === 'completed';
    streams.push({
      purpose: call.purpose,
      model: call.model,
      text: call.output || item.description || '',
      status: completed ? 'completed' : 'streaming',
      input_tokens: call.input_tokens ?? item.metrics?.input_tokens,
      output_tokens: call.output_tokens ?? item.metrics?.output_tokens,
    });
  }

  return streams.sort((left, right) => {
    const leftIndex = PURPOSE_ORDER.indexOf(left.purpose);
    const rightIndex = PURPOSE_ORDER.indexOf(right.purpose);
    return (leftIndex === -1 ? PURPOSE_ORDER.length : leftIndex) - (rightIndex === -1 ? PURPOSE_ORDER.length : rightIndex);
  });
}

export function extractRetryFlows(timeline: TimelineItem[]): RetryFlow[] {
  const flows: RetryFlow[] = [];
  let current: Partial<RetryFlow> = {};

  for (const item of timeline) {
    if (item.kind !== 'decision') {
      continue;
    }
    const stage = flowStage(item);
    if (stage === 'retry_conflict_detected') {
      if (current.conflict && current.decision && current.applied) {
        flows.push(current as RetryFlow);
      }
      current = {
        phase: String(flowPayload(item).phase ?? 'unknown'),
        conflict: item,
      };
      continue;
    }
    if (stage === 'retry_decision' && current.conflict) {
      current.decision = item;
      continue;
    }
    if (stage === 'retry_applied' && current.decision) {
      flows.push(current as RetryFlow);
      current = {};
    }
  }

  return flows;
}

export function extractFinalResponseAutorepairFlows(timeline: TimelineItem[]): AutorepairFlow[] {
  return extractAutorepairFlows(timeline).filter((flow) => flow.phase === 'final_response');
}

const PHASE_LABELS: Record<string, string> = {
  final_response: 'Respuesta final',
};

export function responsePhaseLabel(phase: string): string {
  return PHASE_LABELS[phase] ?? phase;
}

export function hasResponseData(timeline: TimelineItem[]): boolean {
  if (extractFinalResponseStreams(timeline).length > 0) {
    return true;
  }
  if (extractRetryFlows(timeline).length > 0) {
    return true;
  }
  return extractFinalResponseAutorepairFlows(timeline).length > 0;
}
