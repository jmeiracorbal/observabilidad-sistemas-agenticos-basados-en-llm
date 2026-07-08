import { useMemo } from 'react';

import { EmptyState } from '../components/EmptyState';
import { LiveInvokePanel } from '../components/LiveInvokePanel';
import { RunSummaryCard } from '../components/RunSummaryCard';
import type { Run, TurnTokenSummary } from '../types';

export function ConversationPage({
  runs,
  runsLoading,
  activeConversationId,
  invokeSessionKey,
  turnTokenSummary,
  idleTurnIndex,
  onConversationChanged,
  onRunningChange,
  onRunStarted,
  onRunCompleted,
}: {
  runs: Run[];
  runsLoading: boolean;
  activeConversationId?: string;
  invokeSessionKey: number;
  turnTokenSummary: TurnTokenSummary | null;
  idleTurnIndex?: number;
  onConversationChanged: (conversationId: string | undefined) => void;
  onRunningChange: (running: boolean) => void;
  onRunStarted: (runId: string) => void;
  onRunCompleted: (runId: string) => void;
}) {
  const conversationRuns = useMemo(() => {
    if (!activeConversationId) {
      return [];
    }
    return runs
      .filter((run) => run.conversation_id === activeConversationId)
      .sort((a, b) => b.turn_index - a.turn_index);
  }, [runs, activeConversationId]);

  return (
    <>
      <LiveInvokePanel
        activeConversationId={activeConversationId}
        sessionKey={invokeSessionKey}
        contextSummary={turnTokenSummary}
        idleTurnIndex={idleTurnIndex}
        onConversationChanged={onConversationChanged}
        onRunningChange={onRunningChange}
        onRunStarted={onRunStarted}
        onRunCompleted={onRunCompleted}
      />

      {!activeConversationId && !runsLoading && (
        <EmptyState title="Sin actividad" description="Escribe un mensaje arriba para empezar." />
      )}

      {activeConversationId && conversationRuns.length === 0 && !runsLoading && (
        <EmptyState title="Sin mensajes" description="Esta conversación aún no tiene turnos registrados." />
      )}

      <div className="conversation-messages">
        {conversationRuns.map((run) => (
          <RunSummaryCard key={run.id} runId={run.id} to={`/messages/${run.id}`} />
        ))}
      </div>
    </>
  );
}
