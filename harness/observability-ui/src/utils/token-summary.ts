import type { ModelCall, TimelineItem, TurnTokenSummary } from '../types';

export type { TurnTokenSummary };

const FINAL_PURPOSE = 'final_response';

function modelCallFromItem(item: TimelineItem): ModelCall | undefined {
  const payload = item.payload as { model_call?: ModelCall } | undefined;
  return payload?.model_call;
}

function breakdownValue(metadata: Record<string, unknown> | null | undefined, key: string): number {
  const breakdown = metadata?.breakdown;
  if (!breakdown || typeof breakdown !== 'object') {
    return 0;
  }
  const value = (breakdown as Record<string, unknown>)[key];
  return typeof value === 'number' ? value : 0;
}

function estimateTokens(text: string): number {
  const trimmed = text.trim();
  if (!trimmed) {
    return 0;
  }
  return Math.max(1, Math.ceil(trimmed.length / 4));
}

function contextFromTimeline(timeline: TimelineItem[]): Pick<TurnTokenSummary, 'context_window' | 'remaining_input_tokens' | 'output_reserve_tokens'> {
  for (const item of timeline) {
    if (item.kind !== 'decision') {
      continue;
    }
    const decision = (item.payload as { decision?: { stage?: string; payload?: Record<string, unknown> } } | undefined)?.decision;
    if (decision?.stage !== 'context_window_evaluated') {
      continue;
    }
    const payload = decision.payload ?? {};
    return {
      context_window: 0,
      remaining_input_tokens: typeof payload.remaining_input_tokens === 'number' ? payload.remaining_input_tokens : null,
      output_reserve_tokens: typeof payload.output_reserve_tokens === 'number' ? payload.output_reserve_tokens : null,
    };
  }

  for (const item of timeline) {
    if (item.kind !== 'model') {
      continue;
    }
    const call = modelCallFromItem(item);
    const metadata = call?.context_metadata;
    if (!metadata || typeof metadata !== 'object') {
      continue;
    }
    return {
      context_window: typeof metadata.context_window === 'number' ? metadata.context_window : 0,
      remaining_input_tokens:
        typeof metadata.remaining_input_tokens === 'number' ? metadata.remaining_input_tokens : null,
      output_reserve_tokens:
        typeof metadata.output_reserve_tokens === 'number' ? metadata.output_reserve_tokens : null,
    };
  }

  return {
    context_window: 0,
    remaining_input_tokens: null,
    output_reserve_tokens: null,
  };
}

export function summarizeTurnTokens(timeline: TimelineItem[], userInput: string): TurnTokenSummary {
  const context = contextFromTimeline(timeline);
  let user_input_tokens = 0;
  let final_output_tokens = 0;
  let internal_input_tokens = 0;
  let internal_output_tokens = 0;
  let context_window = context.context_window;

  for (const item of timeline) {
    if (item.kind !== 'model') {
      continue;
    }
    const call = modelCallFromItem(item);
    if (!call) {
      continue;
    }

    const purpose = call.purpose ?? '';
    const inputTokens = call.input_tokens ?? item.metrics?.input_tokens ?? 0;
    const outputTokens = call.output_tokens ?? item.metrics?.output_tokens ?? 0;
    const metadata = call.context_metadata;

    if (typeof metadata?.context_window === 'number' && metadata.context_window > 0) {
      context_window = metadata.context_window;
    }

    if (purpose === FINAL_PURPOSE) {
      final_output_tokens = outputTokens;
      user_input_tokens = breakdownValue(metadata, 'user_message') || estimateTokens(userInput);
      continue;
    }

    internal_input_tokens += inputTokens;
    internal_output_tokens += outputTokens;
  }

  if (user_input_tokens === 0) {
    user_input_tokens = estimateTokens(userInput);
  }

  return {
    user_input_tokens,
    final_output_tokens,
    internal_input_tokens,
    internal_output_tokens,
    context_window,
    remaining_input_tokens: context.remaining_input_tokens,
    output_reserve_tokens: context.output_reserve_tokens,
  };
}
