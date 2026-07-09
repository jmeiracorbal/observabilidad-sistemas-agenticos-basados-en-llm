import type { ReactNode } from 'react';

import type { TurnTokenSummary } from '../types';

function formatTokens(value: number): string {
  return `${value.toLocaleString('es-ES')} tokens`;
}

function formatPercent(value: number): string {
  return `${value.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`;
}

function LegendItem({ tone, children }: { tone: 'conv' | 'reserve' | 'free'; children: ReactNode }) {
  return (
    <span className={`conversation-context-bar__legend conversation-context-bar__legend--${tone}`}>
      <span className="conversation-context-bar__swatch" aria-hidden="true" />
      <span>{children}</span>
    </span>
  );
}

function resolveConversationInput(summary: TurnTokenSummary): number {
  if (typeof summary.conversation_input_tokens === 'number' && summary.conversation_input_tokens > 0) {
    return summary.conversation_input_tokens;
  }

  const window = summary.context_window;
  const hasRemaining =
    summary.remaining_input_tokens !== null && summary.remaining_input_tokens !== undefined;
  const hasReserve =
    summary.output_reserve_tokens !== null && summary.output_reserve_tokens !== undefined;

  if (hasRemaining && hasReserve) {
    return Math.max(0, window - summary.output_reserve_tokens! - summary.remaining_input_tokens!);
  }

  return Math.max(0, summary.user_input_tokens + summary.internal_input_tokens);
}

export function ConversationContextBar({ summary }: { summary: TurnTokenSummary }) {
  if (!summary.context_window) {
    return null;
  }

  const window = summary.context_window;
  const reserve = summary.output_reserve_tokens ?? 0;
  const conversationInput = resolveConversationInput(summary);
  const hasRemaining =
    summary.remaining_input_tokens !== null && summary.remaining_input_tokens !== undefined;
  const freeTokens = hasRemaining ? summary.remaining_input_tokens! : Math.max(0, window - conversationInput - reserve);
  const occupied = Math.max(0, window - freeTokens);
  const usagePercent = Math.min(100, Math.max(0, (occupied / window) * 100));
  const conversationPercent = Math.min(100, Math.max(0, (conversationInput / window) * 100));
  const reservePercent = Math.min(100 - conversationPercent, Math.max(0, (reserve / window) * 100));
  const freePercent = Math.max(0, 100 - conversationPercent - reservePercent);
  const historyCount = summary.history_message_count ?? 0;
  const historyLabel =
    historyCount > 0
      ? `${historyCount} msg historial`
      : summary.turn_index && summary.turn_index > 1
        ? `turno ${summary.turn_index}`
        : 'sin historial';

  return (
    <header
      className="conversation-context-bar"
      aria-label="Uso de la ventana de contexto de la conversación"
      title={[
        `Ventana total: ${formatTokens(window)}`,
        `Conversación acumulada: ${formatTokens(conversationInput)} (${historyLabel})`,
        `Reserva de salida: ${formatTokens(reserve)}`,
        `Libre: ${formatTokens(freeTokens)}`,
        `Ocupación: ${formatPercent(usagePercent)}`,
      ].join(' · ')}
    >
      <div className="conversation-context-bar__summary">
        <span>ctx {formatTokens(window)}</span>
        <LegendItem tone="conv">
          conv {formatTokens(conversationInput)}
          {historyCount > 0 ? ` · ${historyCount} msgs` : ''}
        </LegendItem>
        <LegendItem tone="reserve">reserva {formatTokens(reserve)}</LegendItem>
        <LegendItem tone="free">libre {formatTokens(freeTokens)}</LegendItem>
        <span className="conversation-context-bar__percent">{formatPercent(usagePercent)}</span>
      </div>
      <div
        className="context-window-bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={window}
        aria-valuenow={occupied}
        aria-valuetext={`Conversación ${formatTokens(conversationInput)}, reserva ${formatTokens(reserve)}, libre ${formatTokens(freeTokens)}`}
      >
        <span className="context-window-bar__used" style={{ width: `${conversationPercent}%` }} />
        <span className="context-window-bar__output" style={{ width: `${reservePercent}%` }} />
        <span className="context-window-bar__free" style={{ width: `${freePercent}%` }} />
      </div>
    </header>
  );
}
