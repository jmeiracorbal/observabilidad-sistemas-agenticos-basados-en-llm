import type { LlmStreamState } from '../types-stream';
import type { ModelCall, TimelineItem } from '../types';

const PLANNER_PURPOSES = new Set(['planner_assessment', 'planner_decision']);

const PURPOSE_ORDER = ['planner_assessment', 'planner_decision'];

function modelCallFromItem(item: TimelineItem): ModelCall | undefined {
  const payload = item.payload as { model_call?: ModelCall } | undefined;
  return payload?.model_call;
}

function decisionFromItem(item: TimelineItem) {
  const payload = item.payload as { decision?: { stage?: string; payload?: Record<string, unknown> } } | undefined;
  return payload?.decision;
}

export function extractPlannerStreams(timeline: TimelineItem[]): LlmStreamState[] {
  const streams: LlmStreamState[] = [];

  for (const item of timeline) {
    if (item.kind !== 'model') {
      continue;
    }
    const call = modelCallFromItem(item);
    if (!call?.purpose || !PLANNER_PURPOSES.has(call.purpose)) {
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

export interface PlanningOutcome {
  selectedAction?: string;
  plan?: Record<string, unknown>;
  hiddenReasoning: unknown[];
}

export function extractPlanningOutcome(timeline: TimelineItem[]): PlanningOutcome | null {
  for (let index = timeline.length - 1; index >= 0; index -= 1) {
    const decision = decisionFromItem(timeline[index]);
    if (decision?.stage !== 'planning_finalized') {
      continue;
    }
    const payload = decision.payload ?? {};
    const plan = payload.plan;
    return {
      selectedAction: typeof payload.selected_action === 'string' ? payload.selected_action : undefined,
      plan: plan && typeof plan === 'object' ? (plan as Record<string, unknown>) : undefined,
      hiddenReasoning: Array.isArray(payload.hidden_reasoning) ? payload.hidden_reasoning : [],
    };
  }

  for (let index = timeline.length - 1; index >= 0; index -= 1) {
    const item = timeline[index];
    if (item.kind !== 'decision') {
      continue;
    }
    const reasoning = item.content?.hidden_reasoning;
    if (!Array.isArray(reasoning) || reasoning.length === 0) {
      continue;
    }
    return {
      selectedAction: typeof item.content?.selected_action === 'string' ? item.content.selected_action : undefined,
      plan: item.content?.decision && typeof item.content.decision === 'object'
        ? (item.content.decision as Record<string, unknown>)
        : undefined,
      hiddenReasoning: reasoning,
    };
  }

  return null;
}

export function hasPlanningData(timeline: TimelineItem[]): boolean {
  if (extractPlannerStreams(timeline).length > 0) {
    return true;
  }
  return extractPlanningOutcome(timeline) !== null;
}

export function isPlanningComplete(timeline: TimelineItem[]): boolean {
  return timeline.some((item) => {
    if (decisionFromItem(item)?.stage === 'planning_finalized') {
      return true;
    }
    return item.kind === 'decision' && item.title === 'planning_finalized';
  });
}

export function shouldShowRunSummaryStats(runStatus: string, timeline: TimelineItem[]): boolean {
  if (runStatus === 'completed' || runStatus === 'failed') {
    return true;
  }
  return isPlanningComplete(timeline);
}
