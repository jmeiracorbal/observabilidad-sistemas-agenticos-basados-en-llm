import type { TurnTokenSummary } from '../types';

function formatTokens(value: number): string {
  return `${value.toLocaleString('es-ES')} tokens`;
}

export function ConversationContextBar({ summary }: { summary: TurnTokenSummary }) {
  if (!summary.context_window) {
    return null;
  }

  const window = summary.context_window;
  const hasRemaining =
    summary.remaining_input_tokens !== null && summary.remaining_input_tokens !== undefined;
  const hasReserve =
    summary.output_reserve_tokens !== null && summary.output_reserve_tokens !== undefined;

  const inputUsed =
    hasRemaining && hasReserve
      ? Math.max(0, window - summary.output_reserve_tokens! - summary.remaining_input_tokens!)
      : Math.max(0, summary.user_input_tokens + summary.internal_input_tokens);

  const outputUsed = Math.max(0, summary.final_output_tokens);
  const totalUsed = inputUsed + outputUsed;
  const freeTokens = Math.max(0, window - totalUsed);
  const inputPercent = Math.min(100, Math.max(0, (inputUsed / window) * 100));
  const outputPercent = Math.min(100 - inputPercent, Math.max(0, (outputUsed / window) * 100));
  const freePercent = Math.max(0, 100 - inputPercent - outputPercent);

  return (
    <header
      className="conversation-context-bar"
      aria-label="Uso de la ventana de contexto"
      title={`${formatTokens(freeTokens)} libres · ${formatTokens(inputUsed)} entrada · ${formatTokens(outputUsed)} salida`}
    >
      <div className="conversation-context-bar__summary">
        <span>ctx {formatTokens(window)}</span>
        <span>uso {formatTokens(inputUsed)}</span>
        <span>out {formatTokens(outputUsed)}</span>
      </div>
      <div
        className="context-window-bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={window}
        aria-valuenow={totalUsed}
      >
        <span className="context-window-bar__used" style={{ width: `${inputPercent}%` }} />
        <span className="context-window-bar__output" style={{ width: `${outputPercent}%` }} />
        <span className="context-window-bar__free" style={{ width: `${freePercent}%` }} />
      </div>
    </header>
  );
}
