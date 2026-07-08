import { useEffect, useMemo, useState } from 'react';

import { getRunTimeline } from '../api';
import type { RunTimelineResponse } from '../types';
import { summarizeTurnTokens } from '../utils/token-summary';
import { RunSummary } from './RunSummary';

export function RunSummaryCard({ runId, to }: { runId: string; to: string }) {
  const [timelineData, setTimelineData] = useState<RunTimelineResponse>();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    void getRunTimeline(runId, controller.signal)
      .then(setTimelineData)
      .catch((loadError) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : 'No se pudo cargar el mensaje');
      });
    return () => controller.abort();
  }, [runId]);

  useEffect(() => {
    if (!timelineData || timelineData.run.status !== 'running') {
      return;
    }

    const controller = new AbortController();
    const interval = window.setInterval(() => {
      void getRunTimeline(runId, controller.signal).then(setTimelineData).catch(() => undefined);
    }, 1200);

    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [runId, timelineData]);

  const tokenSummary = useMemo(() => {
    if (!timelineData) {
      return undefined;
    }
    return timelineData.token_summary ?? summarizeTurnTokens(timelineData.timeline, timelineData.run.input);
  }, [timelineData]);

  if (error) {
    return <div className="alert alert-error">{error}</div>;
  }

  if (!timelineData) {
    return <div className="panel muted pad">Cargando mensaje…</div>;
  }

  return (
    <RunSummary
      run={timelineData.run}
      timeline={timelineData.timeline}
      tokenSummary={tokenSummary}
      to={to}
    />
  );
}
