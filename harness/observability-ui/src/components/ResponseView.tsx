import { useMemo } from 'react';

import { JsonView } from './JsonView';
import { LiveStreamCard } from './LiveStreamCard';
import type { TimelineItem } from '../types';
import {
  extractFinalResponseAutorepairFlows,
  extractFinalResponseStreams,
  extractRetryFlows,
  hasResponseData,
  responsePhaseLabel,
} from '../utils/response';

function retryStepLabel(stage: string): string {
  if (stage === 'retry_conflict_detected') {
    return 'Contrato incumplido';
  }
  if (stage === 'retry_decision') {
    return 'Decisión de reintentar';
  }
  return 'Reintento programado';
}

function autorepairStepLabel(stage: string): string {
  if (stage === 'autorepair_conflict_detected') {
    return 'Conflicto detectado';
  }
  if (stage === 'autorepair_decision') {
    return 'Decisión de autoreparar';
  }
  return 'Corrección aplicada';
}

function flowStepPayload(step: TimelineItem): Record<string, unknown> {
  const nested = (step.payload as { decision?: { payload?: Record<string, unknown> } } | undefined)?.decision?.payload;
  return step.content && Object.keys(step.content).length > 0 ? step.content : (nested ?? {});
}

const PURPOSE_LABELS: Record<string, string> = {
  final_response: 'Respuesta',
  final_response_retry: 'Reintento',
};

export function ResponseView({ timeline, runStatus }: { timeline: TimelineItem[]; runStatus?: string }) {
  const streams = useMemo(() => extractFinalResponseStreams(timeline), [timeline]);
  const retryFlows = useMemo(() => extractRetryFlows(timeline), [timeline]);
  const autorepairFlows = useMemo(() => extractFinalResponseAutorepairFlows(timeline), [timeline]);
  const empty = !hasResponseData(timeline);

  if (empty) {
    return (
      <section className="panel muted pad response-view">
        {runStatus === 'running'
          ? 'La respuesta final aparecerá aquí cuando el agente la genere.'
          : 'No hay pasos de respuesta final registrados para este mensaje.'}
      </section>
    );
  }

  return (
    <section className="response-view">
      <div className="live-stream-grid custom-scroll">
        {streams.map((stream, index) => (
          <LiveStreamCard
            key={`${stream.purpose}-${index}`}
            stream={stream}
            label={PURPOSE_LABELS[stream.purpose] ?? stream.purpose}
          />
        ))}
      </div>

      {retryFlows.length > 0 && (
        <div className="response-recovery-stack">
          {retryFlows.map((flow) => (
            <section key={`retry-${flow.phase}-${flow.conflict.id}`} className="response-recovery response-recovery--retry panel">
              <header className="response-recovery__header">
                <strong>Reintento</strong>
                <span className="response-recovery__phase">{responsePhaseLabel(flow.phase)}</span>
              </header>
              <div className="response-recovery__steps">
                {[flow.conflict, flow.decision, flow.applied].map((step) => (
                  <article key={step.id} className="response-recovery__step">
                    <header className="response-recovery__step-header">
                      <span>{retryStepLabel(step.title)}</span>
                      <span className="muted">{step.subtitle}</span>
                    </header>
                    <JsonView value={flowStepPayload(step)} />
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      {autorepairFlows.length > 0 && (
        <div className="response-recovery-stack">
          {autorepairFlows.map((flow) => (
            <section key={`autorepair-${flow.phase}-${flow.conflict.id}`} className="response-recovery response-recovery--autorepair panel">
              <header className="response-recovery__header">
                <strong>Autoreparación</strong>
                <span className="response-recovery__phase">{responsePhaseLabel(flow.phase)}</span>
              </header>
              <div className="response-recovery__steps">
                {[flow.conflict, flow.decision, flow.applied].map((step) => (
                  <article key={step.id} className="response-recovery__step">
                    <header className="response-recovery__step-header">
                      <span>{autorepairStepLabel(step.title)}</span>
                      <span className="muted">{step.subtitle}</span>
                    </header>
                    <JsonView value={flowStepPayload(step)} />
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </section>
  );
}
