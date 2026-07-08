import { Link } from 'react-router-dom';

import type { Run, TimelineItem, TurnTokenSummary } from '../types';
import { durationMs, formatDuration, formatTime } from '../utils/time';
import { shouldShowRunSummaryStats } from '../utils/planning';
import { summarizeTimeline } from '../utils/timeline';
import { summarizeTurnTokens } from '../utils/token-summary';

export function RunSummary({
  run,
  timeline,
  tokenSummary,
  to,
}: {
  run: Run;
  timeline: TimelineItem[];
  tokenSummary?: TurnTokenSummary;
  to?: string;
}) {
  const summary = summarizeTimeline(timeline);
  const tokens = tokenSummary ?? summarizeTurnTokens(timeline, run.input);
  const duration = durationMs(run.started_at, run.ended_at);
  const internalTotal = tokens.internal_input_tokens + tokens.internal_output_tokens;
  const status = run.status ?? 'unknown';
  const showStats = shouldShowRunSummaryStats(status, timeline);

  const content = (
    <section className={`panel run-summary run-summary--${status}${to ? ' run-summary--link' : ''}`}>
      <header className="run-summary__header">
        <div className="run-summary__title-row">
          <h2 className="run-summary__prompt">
            <span>{showStats ? run.input : 'Planificación en curso…'}</span>
          </h2>
          <p className="run-summary__meta muted">
            <span>
              <span className="run-summary__meta-label">inicio</span> {formatTime(run.started_at)}
            </span>
            <span aria-hidden>·</span>
            <span>
              <span className="run-summary__meta-label">fin</span> {formatTime(run.ended_at)}
            </span>
            <span aria-hidden>·</span>
            <span>{formatDuration(duration)}</span>
          </p>
        </div>
      </header>

      {showStats ? (
        <footer className="run-summary__stats" aria-label="Métricas del turno">
          <Metric label="Mensaje" value={tokens.user_input_tokens} />
          <Metric label="Respuesta" value={tokens.final_output_tokens} />
          <Metric label="Pipeline" value={internalTotal} />
          <Metric label="Tramos" value={summary.spans} />
          <Metric label="Decisiones" value={summary.decisions} />
          <Metric label="Modelo" value={summary.models} />
          <Metric label="Herramientas" value={summary.tools} />
          <Metric label="Memoria" value={summary.memories} />
          <Metric label="Errores" value={summary.errors} tone={summary.errors > 0 ? 'danger' : undefined} />
        </footer>
      ) : (
        <footer className="run-summary__stats run-summary__stats--pending" aria-label="Planificación en curso">
          <span className="run-summary__pending">Las métricas aparecerán cuando termine la planificación.</span>
        </footer>
      )}
    </section>
  );

  if (!to) {
    return content;
  }

  return (
    <Link className="run-summary-link" to={to}>
      {content}
    </Link>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: 'danger';
}) {
  return (
    <span className={`run-summary__stat ${tone === 'danger' ? 'run-summary__stat--danger' : ''}`}>
      <span className="run-summary__stat-label">{label}</span>
      <strong>{value.toLocaleString('es-ES')}</strong>
    </span>
  );
}
