export type StreamEventName =
  | 'run_started'
  | 'llm_started'
  | 'llm_delta'
  | 'llm_completed'
  | 'run_completed'
  | 'run_failed';

export interface LlmStreamState {
  purpose: string;
  model?: string;
  text: string;
  status: 'idle' | 'streaming' | 'completed';
  input_tokens?: number;
  output_tokens?: number;
}

export interface InvokeStreamState {
  status: 'idle' | 'running' | 'completed' | 'failed';
  runId?: string;
  conversationId?: string;
  turnIndex?: number;
  remainingInputTokens?: number;
  outputReserveTokens?: number;
  estimatedInputTokens?: number;
  historyMessageCount?: number;
  message?: string;
  response?: string;
  error?: string;
  llmStreams: Record<string, LlmStreamState>;
}
