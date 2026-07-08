import { config } from './config';
import type { Run, RunTimelineResponse } from './types';
import type { StreamEventName } from './types-stream';

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const baseUrl = config.observabilityApiUrl.replace(/\/$/, '');
  const response = await fetch(`${baseUrl}${path}`, {
    headers: { Accept: 'application/json' },
    signal,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text || response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export function listRuns(signal?: AbortSignal): Promise<Run[]> {
  return request<Run[]>('/runs', signal);
}

export function getRunTimeline(runId: string, signal?: AbortSignal): Promise<RunTimelineResponse> {
  return request<RunTimelineResponse>(`/runs/${encodeURIComponent(runId)}/timeline`, signal);
}

function parseSseBlock(block: string): { event: StreamEventName; data: unknown } | null {
  let eventName = 'message';
  const dataLines: string[] = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  return {
    event: eventName as StreamEventName,
    data: JSON.parse(dataLines.join('\n')),
  };
}

export async function invokeAgentStream(
  message: string,
  conversationId: string | undefined,
  onEvent: (event: StreamEventName, data: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const baseUrl = config.agentApiUrl.replace(/\/$/, '');
  const response = await fetch(`${baseUrl}/invoke/stream`, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text || response.statusText}`);
  }

  if (!response.body) {
    throw new Error('el agente no devolvió un stream de eventos');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';
    for (const block of blocks) {
      const parsed = parseSseBlock(block.trim());
      if (parsed) {
        onEvent(parsed.event, parsed.data as Record<string, unknown>);
      }
    }
  }

  const tail = buffer.trim();
  if (tail) {
    const parsed = parseSseBlock(tail);
    if (parsed) {
      onEvent(parsed.event, parsed.data as Record<string, unknown>);
    }
  }
}
