export type Status = 'running' | 'completed' | 'failed' | string;
export type SpanType = 'agent' | 'tool' | 'memory' | 'model' | string;

export interface Run {
  id: string;
  input: string;
  conversation_id: string;
  turn_index: number;
  status: Status;
  started_at: string;
  ended_at?: string | null;
}

export interface Span {
  id: string;
  run_id: string;
  parent_span_id?: string | null;
  type: SpanType;
  name: string;
  status: Status;
  started_at: string;
  ended_at?: string | null;
}

export interface ModelCall {
  id?: number;
  span_id: string;
  model: string;
  input: string;
  output: string;
  input_tokens: number;
  output_tokens: number;
  purpose?: string | null;
  context_metadata?: Record<string, unknown> | null;
  started_at?: string | null;
  ended_at?: string | null;
  created_at?: string;
}

export interface ToolCall {
  id?: number;
  span_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  result: string;
  owner_agent?: string | null;
  purpose?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  created_at?: string;
}

export interface MemoryEvent {
  id?: number;
  span_id: string;
  operation: string;
  query: string;
  results_count: number;
  owner_agent?: string | null;
  purpose?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  created_at?: string;
}

export interface DecisionEvent {
  id?: number;
  span_id: string;
  actor?: string | null;
  stage: string;
  input: string;
  available_tools: string[];
  selected_tools: string[];
  rationale: string;
  payload?: Record<string, unknown>;
  started_at?: string | null;
  ended_at?: string | null;
  created_at?: string;
}

export interface ErrorEvent {
  id?: number;
  span_id: string;
  error_type: string;
  message: string;
  created_at?: string;
}

export interface SpanNode {
  span: Span;
  model_calls: ModelCall[];
  tool_calls: ToolCall[];
  memory_events: MemoryEvent[];
  decision_events: DecisionEvent[];
  errors: ErrorEvent[];
  children: SpanNode[];
}

export type TimelineItemKind = 'input' | 'output' | 'span' | 'decision' | 'model' | 'tool' | 'memory' | 'error' | 'event';

export interface TimelineItem {
  id: string;
  sequence: number;
  kind: TimelineItemKind;
  event_type: string;
  title: string;
  subtitle: string;
  description?: string | null;
  status?: Status;
  span_id?: string | null;
  depth: number;
  actor: string;
  actor_type: string;
  source_actor: string;
  source_actor_type: string;
  target_actor: string;
  target_actor_type: string;
  relation: string;
  event_role?: 'annotation' | 'call' | 'response' | 'execution' | string;
  visibility?: 'public' | 'hidden' | string;
  started_at?: string | null;
  ended_at?: string | null;
  created_at?: string | null;
  duration_ms?: number | null;
  content?: Record<string, unknown>;
  metrics?: Record<string, number>;
  payload: unknown;
}

export interface RunTimelineResponse {
  run: Run;
  timeline: TimelineItem[];
  token_summary?: TurnTokenSummary;
}

export interface TurnTokenSummary {
  user_input_tokens: number;
  final_output_tokens: number;
  internal_input_tokens: number;
  internal_output_tokens: number;
  context_window: number;
  remaining_input_tokens: number | null;
  output_reserve_tokens: number | null;
}
