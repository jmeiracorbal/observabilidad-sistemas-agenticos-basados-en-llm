export function formatTokenMetrics(input?: number, output?: number): string {
  if (input === undefined && output === undefined) {
    return '';
  }
  return ` · in: ${input ?? 0} · out: ${output ?? 0}`;
}

export function formatStreamTokenMetrics(purpose: string, input?: number, output?: number): string {
  if (purpose === 'final_response') {
    return ` · respuesta: ${output ?? 0}`;
  }
  return formatTokenMetrics(input, output);
}

export function formatTurnTokenLine(summary: {
  user_input_tokens: number;
  final_output_tokens: number;
  internal_input_tokens: number;
  internal_output_tokens: number;
}): string {
  const pipeline = summary.internal_input_tokens + summary.internal_output_tokens;
  return `msg ${summary.user_input_tokens} · resp ${summary.final_output_tokens} · pipe ${pipeline}`;
}
