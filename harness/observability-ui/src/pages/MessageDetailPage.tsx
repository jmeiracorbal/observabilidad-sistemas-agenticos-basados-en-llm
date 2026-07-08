import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { getRunTimeline } from '../api';
import { ArtifactGraph } from '../components/ArtifactGraph';
import { EventInspector } from '../components/EventInspector';
import { PlanningView } from '../components/PlanningView';
import { ResponseView } from '../components/ResponseView';
import { RunSummary } from '../components/RunSummary';
import { TimelineView } from '../components/TimelineView';
import type { RunTimelineResponse, TimelineItem } from '../types';
import { summarizeTurnTokens } from '../utils/token-summary';

export function MessageDetailPage({
  runId,
  onConversationChanged,
  onRunLoaded,
}: {
  runId: string;
  onConversationChanged: (conversationId: string) => void;
  onRunLoaded: (runId: string) => void;
}) {
  const [runTimeline, setRunTimeline] = useState<RunTimelineResponse>();
  const [selectedItem, setSelectedItem] = useState<TimelineItem | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<'timeline' | 'graph' | 'planning' | 'response'>('timeline');

  useEffect(() => {
    const controller = new AbortController();
    setDetailsLoading(true);
    setDetailsError(null);
    setSelectedItem(null);
    void getRunTimeline(runId, controller.signal)
      .then((data) => {
        setRunTimeline(data);
        onConversationChanged(data.run.conversation_id);
        onRunLoaded(data.run.id);
      })
      .catch((error) => {
        if (controller.signal.aborted) {
          return;
        }
        setDetailsError(error instanceof Error ? error.message : 'No se pudo cargar el detalle');
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setDetailsLoading(false);
        }
      });
    return () => controller.abort();
  }, [runId, onConversationChanged, onRunLoaded]);

  useEffect(() => {
    if (!runTimeline || runTimeline.run.status !== 'running') {
      return;
    }
    const controller = new AbortController();
    const interval = window.setInterval(() => {
      void getRunTimeline(runId, controller.signal).then(setRunTimeline).catch(() => undefined);
    }, 1200);
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [runId, runTimeline]);

  const timeline = useMemo(() => runTimeline?.timeline ?? [], [runTimeline]);
  const turnTokenSummary = useMemo(() => {
    if (!runTimeline) {
      return null;
    }
    return runTimeline.token_summary ?? summarizeTurnTokens(runTimeline.timeline, runTimeline.run.input);
  }, [runTimeline]);

  return (
    <>
      {detailsError && <div className="alert alert-error">{detailsError}</div>}
      {detailsLoading && !runTimeline && <div className="panel muted pad">Cargando detalle…</div>}

      {!runTimeline && (
        <nav className="detail-nav">
          <Link className="detail-nav__back" to="/">
            ← Conversación
          </Link>
        </nav>
      )}

      {runTimeline && (
        <>
          <RunSummary
            run={runTimeline.run}
            timeline={runTimeline.timeline}
            tokenSummary={turnTokenSummary ?? undefined}
          />

          <nav className="detail-nav">
            <Link className="detail-nav__back" to="/">
              ← Conversación
            </Link>
            <div className="tabs">
              <button
                className={activeView === 'timeline' ? 'tab tab--active' : 'tab'}
                type="button"
                onClick={() => setActiveView('timeline')}
              >
                Actividad
              </button>
              <button
                className={activeView === 'graph' ? 'tab tab--active' : 'tab'}
                type="button"
                onClick={() => setActiveView('graph')}
              >
                Diagrama
              </button>
              <button
                className={activeView === 'planning' ? 'tab tab--active' : 'tab'}
                type="button"
                onClick={() => setActiveView('planning')}
              >
                Planificación
              </button>
              <button
                className={activeView === 'response' ? 'tab tab--active' : 'tab'}
                type="button"
                onClick={() => setActiveView('response')}
              >
                Respuesta
              </button>
            </div>
          </nav>

          {activeView === 'timeline' && (
            <div className="workspace-grid">
              <TimelineView items={timeline} selectedItemId={selectedItem?.id} onSelect={setSelectedItem} />
              <EventInspector item={selectedItem} />
            </div>
          )}

          {activeView === 'graph' && <ArtifactGraph run={runTimeline.run} timeline={runTimeline.timeline} />}

          {activeView === 'planning' && (
            <PlanningView timeline={runTimeline.timeline} runStatus={runTimeline.run.status} />
          )}

          {activeView === 'response' && (
            <ResponseView timeline={runTimeline.timeline} runStatus={runTimeline.run.status} />
          )}
        </>
      )}
    </>
  );
}
