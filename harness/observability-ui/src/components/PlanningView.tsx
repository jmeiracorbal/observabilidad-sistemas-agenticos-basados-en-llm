import { useMemo } from 'react';

import { JsonView } from './JsonView';
import { LiveStreamCard } from './LiveStreamCard';
import type { TimelineItem } from '../types';
import { extractPlannerStreams, extractPlanningOutcome, hasPlanningData } from '../utils/planning';

const PURPOSE_LABELS: Record<string, string> = {
  planner_assessment: 'análisis',
  planner_decision: 'decisión',
};

export function PlanningView({ timeline, runStatus }: { timeline: TimelineItem[]; runStatus?: string }) {
  const streams = useMemo(() => extractPlannerStreams(timeline), [timeline]);
  const outcome = useMemo(() => extractPlanningOutcome(timeline), [timeline]);
  const empty = !hasPlanningData(timeline);

  if (empty) {
    return (
      <section className="panel muted pad planning-view">
        {runStatus === 'running'
          ? 'La planificación aparecerá aquí cuando el agente la ejecute.'
          : 'No hay pasos de planificación registrados para este mensaje.'}
      </section>
    );
  }

  return (
    <section className="planning-view">
      <div className="live-stream-grid custom-scroll">
        {streams.map((stream) => (
          <LiveStreamCard
            key={stream.purpose}
            stream={stream}
            label={PURPOSE_LABELS[stream.purpose] ?? stream.purpose}
          />
        ))}
      </div>

      {outcome && (
        <div className="planning-outcome panel">
          <header className="planning-outcome__header">
            <strong>Resultado de planificación</strong>
            {outcome.selectedAction && <span className="planning-outcome__action">{outcome.selectedAction}</span>}
          </header>

          {outcome.plan && (
            <>
              <p className="inspector-section-label">Plan estructurado</p>
              <JsonView value={outcome.plan} />
            </>
          )}

          {outcome.hiddenReasoning.length > 0 && (
            <>
              <p className="inspector-section-label">Razonamiento interno</p>
              <div className="hidden-reasoning">
                {outcome.hiddenReasoning.map((step, index) => (
                  <div key={index} className="hidden-reasoning__step">
                    <strong>#{String((step as { step?: number }).step ?? index + 1).padStart(2, '0')}</strong>
                    <JsonView value={step} />
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
