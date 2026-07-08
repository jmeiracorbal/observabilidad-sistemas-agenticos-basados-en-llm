import type { TurnTokenSummary } from '../types';

export function ConversationContextBar({ summary }: { summary: TurnTokenSummary }) {
  if (!summary.context_window) {
    return null;
  }

  const window = summary.context_window;
  const remaining =
    summary.remaining_input_tokens ?? Math.max(0, window - (summary.output_reserve_tokens ?? 0));
  const used = Math.max(0, window - remaining);
  const usedPercent = Math.min(100, Math.max(0, (used / window) * 100));
  const freePercent = 100 - usedPercent;

  return (
    <header
      className="conversation-context-bar"
      aria-label="Uso de la ventana de contexto"
      title={`${remaining.toLocaleString('es-ES')} tokens libres · ${used.toLocaleString('es-ES')} en uso`}
    >
      <div className="conversation-context-bar__summary">
        <span>ctx {window.toLocaleString('es-ES')}</span>
        <span>uso {used.toLocaleString('es-ES')}</span>
        <span>out {summary.output_reserve_tokens?.toLocaleString('es-ES') ?? '—'}</span>
      </div>
      <div
        className="context-window-bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={window}
        aria-valuenow={remaining}
      >
        <span className="context-window-bar__used" style={{ width: `${usedPercent}%` }} />
        <span className="context-window-bar__free" style={{ width: `${freePercent}%` }} />
      </div>
    </header>
  );
}
