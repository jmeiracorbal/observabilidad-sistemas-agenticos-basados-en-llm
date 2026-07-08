import { useMemo } from 'react';

import { JsonView } from './JsonView';
import { LiveStreamCard } from './LiveStreamCard';
import type { TimelineItem } from '../types';
import {
  autorepairPhaseLabel,
  extractPlannerStreams,
  extractPlanningAutorepairFlows,
  extractPlanningOutcome,
  hasPlanningData,
} from '../utils/planning';

function autorepairStepLabel(stage: string): string {
  if (stage === 'autorepair_conflict_detected') {
    return 'Conflicto detectado';
  }
  if (stage === 'autorepair_decision') {
    return 'Decisión de autoreparar';
  }
  return 'Corrección aplicada';
}

const PURPOSE_LABELS: Record<string, string> = {
  planner_assessment: 'análisis',
  planner_decision: 'decisión',
};

export function PlanningView({ timeline, runStatus }: { timeline: TimelineItem[]; runStatus?: string }) {
  const streams = useMemo(() => extractPlannerStreams(timeline), [timeline]);
  const autorepairFlows = useMemo(() => extractPlanningAutorepairFlows(timeline), [timeline]);
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

      {autorepairFlows.length > 0 && (
        <div className="planning-autorepair-stack">
          {autorepairFlows.map((flow) => (
            <section key={`${flow.phase}-${flow.conflict.id}`} className="planning-autorepair panel">
              <header className="planning-autorepair__header">
                <strong>Autoreparación</strong>
                <span className="planning-autorepair__phase">{autorepairPhaseLabel(flow.phase)}</span>
              </header>
              <div className="planning-autorepair__steps">
                {[flow.conflict, flow.decision, flow.applied].map((step) => {
                  const stage = step.title;
                  const nested = (step.payload as { decision?: { payload?: Record<string, unknown> } } | undefined)
                    ?.decision?.payload;
                  const payload =
                    step.content && Object.keys(step.content).length > 0 ? step.content : (nested ?? {});
                  return (
                    <article key={step.id} className="planning-autorepair__step">
                      <header className="planning-autorepair__step-header">
                        <span>{autorepairStepLabel(stage)}</span>
                        <span className="muted">{step.subtitle}</span>
                      </header>
                      <JsonView value={payload} />
                    </article>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      )}

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
