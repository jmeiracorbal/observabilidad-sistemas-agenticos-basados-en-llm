import { useMemo } from 'react';

import type { Run } from '../types';
import { formatTime } from '../utils/time';

interface Props {
  runs: Run[];
  activeConversationId?: string;
  loading: boolean;
  error?: string | null;
  onSelectConversation: (conversationId: string) => void;
}

export function RunsSidebar({
  runs,
  activeConversationId,
  loading,
  error,
  onSelectConversation,
}: Props) {
  const conversations = useMemo(() => {
    const groups = runs.reduce<Record<string, Run[]>>((acc, run) => {
      const key = run.conversation_id ?? 'sin-conversacion';
      acc[key] = acc[key] ? [...acc[key], run] : [run];
      return acc;
    }, {});
    return Object.entries(groups)
      .map(([conversationId, conversationRuns]) => ({
        conversationId,
        runs: conversationRuns.sort((a, b) => b.turn_index - a.turn_index),
      }))
      .sort((a, b) => new Date(b.runs[0].started_at).getTime() - new Date(a.runs[0].started_at).getTime());
  }, [runs]);

  return (
    <aside className="runs-sidebar">
      <div className="sidebar-header">
        <h2>Historial</h2>
      </div>

      <div className="runs-sidebar__scroll custom-scroll">
        {error && <div className="alert alert-error">{error}</div>}
        {loading && runs.length === 0 && <div className="muted pad">Cargando…</div>}

        <div className="run-list run-list--compact">
        {conversations.map(({ conversationId, runs: conversationRuns }) => {
          const latest = conversationRuns[0];
          const title = conversationId === 'sin-conversacion' ? 'Sin agrupar' : `Chat ${conversationId.slice(0, 8)}`;
          const messageCount = conversationRuns.length;
          return (
            <button
              key={conversationId}
              className={`conversation-card conversation-card--compact ${activeConversationId === conversationId ? 'conversation-card--active' : ''}`}
              type="button"
              onClick={() => onSelectConversation(conversationId)}
            >
              <span className="conversation-card__id">{title}</span>
              <span className="conversation-card__meta muted">
                <span>{messageCount} msg</span>
                <span aria-hidden>·</span>
                <span>{formatTime(latest?.started_at)}</span>
              </span>
            </button>
          );
        })}
        </div>
      </div>
    </aside>
  );
}
