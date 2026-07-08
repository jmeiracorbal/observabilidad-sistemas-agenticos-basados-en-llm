import { useCallback, useEffect, useMemo, useState } from 'react';
import { Route, Routes, useNavigate, useParams } from 'react-router-dom';

import { getRunTimeline, listRuns } from './api';
import { config } from './config';
import { RunsSidebar } from './components/RunsSidebar';
import { ConversationPage } from './pages/ConversationPage';
import { MessageDetailPage } from './pages/MessageDetailPage';
import type { Run } from './types';
import { summarizeTurnTokens } from './utils/token-summary';

function MessageDetailRoute({
  onConversationChanged,
  onRunLoaded,
}: {
  onConversationChanged: (conversationId: string) => void;
  onRunLoaded: (runId: string) => void;
}) {
  const { runId } = useParams<{ runId: string }>();
  if (!runId) {
    return null;
  }
  return (
    <MessageDetailPage
      runId={runId}
      onConversationChanged={onConversationChanged}
      onRunLoaded={onRunLoaded}
    />
  );
}

function App() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>();
  const [runsLoading, setRunsLoading] = useState(false);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [liveRunId, setLiveRunId] = useState<string>();
  const [activeConversationId, setActiveConversationId] = useState<string>();
  const [invokeSessionKey, setInvokeSessionKey] = useState(0);
  const [invokeRunning, setInvokeRunning] = useState(false);
  const [previewTokenSummary, setPreviewTokenSummary] = useState<ReturnType<typeof summarizeTurnTokens> | null>(null);

  const refreshRuns = useCallback(async (signal?: AbortSignal) => {
    setRunsLoading(true);
    setRunsError(null);
    try {
      const data = await listRuns(signal);
      setRuns(data);
    } catch (error) {
      setRunsError(error instanceof Error ? error.message : 'No se pudo cargar el historial');
    } finally {
      setRunsLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refreshRuns(controller.signal);
    return () => controller.abort();
  }, [refreshRuns]);

  useEffect(() => {
    if (!liveRunId) {
      return;
    }
    const controller = new AbortController();
    const interval = window.setInterval(() => {
      void refreshRuns(controller.signal);
    }, 1200);
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [liveRunId, refreshRuns]);

  useEffect(() => {
    if (!selectedRunId) {
      setPreviewTokenSummary(null);
      return;
    }
    const controller = new AbortController();
    void getRunTimeline(selectedRunId, controller.signal)
      .then((data) => {
        setPreviewTokenSummary(data.token_summary ?? summarizeTurnTokens(data.timeline, data.run.input));
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setPreviewTokenSummary(null);
        }
      });
    return () => controller.abort();
  }, [selectedRunId]);

  const selectedTurnTokens = useMemo(() => previewTokenSummary, [previewTokenSummary]);

  const selectConversation = useCallback(
    (conversationId: string) => {
      setActiveConversationId(conversationId);
      navigate('/');
    },
    [navigate],
  );

  const selectRun = useCallback(
    (runId: string) => {
      setSelectedRunId(runId);
      navigate(`/messages/${runId}`);
    },
    [navigate],
  );

  const startNewConversation = useCallback(() => {
    setActiveConversationId(undefined);
    setSelectedRunId(undefined);
    setPreviewTokenSummary(null);
    setLiveRunId(undefined);
    setInvokeSessionKey((current) => current + 1);
    navigate('/');
  }, [navigate]);

  return (
    <div className="app-shell">
      <RunsSidebar
        runs={runs}
        activeConversationId={activeConversationId}
        loading={runsLoading}
        error={runsError}
        onSelectConversation={selectConversation}
      />

      <main className="main-content">
        <header className="topbar">
          <h1>{config.appTitle}</h1>
          <div className="topbar-actions">
            {invokeRunning && <span className="status-badge status-running">En curso</span>}
            <button
              className="new-conversation-button"
              type="button"
              disabled={invokeRunning}
              onClick={startNewConversation}
            >
              Nueva conversación
            </button>
          </div>
        </header>

        <div className="main-content__body">
        <Routes>
          <Route
            path="/"
            element={
              <ConversationPage
                runs={runs}
                runsLoading={runsLoading}
                activeConversationId={activeConversationId}
                invokeSessionKey={invokeSessionKey}
                turnTokenSummary={selectedTurnTokens}
                onConversationChanged={setActiveConversationId}
                onRunningChange={setInvokeRunning}
                onRunStarted={setLiveRunId}
                onRunCompleted={(runId) => {
                  setLiveRunId(undefined);
                  setSelectedRunId(runId);
                  void refreshRuns();
                }}
              />
            }
          />
          <Route
            path="/messages/:runId"
            element={
              <MessageDetailRoute
                onConversationChanged={setActiveConversationId}
                onRunLoaded={setSelectedRunId}
              />
            }
          />
        </Routes>
        </div>
      </main>
    </div>
  );
}

export default App;
