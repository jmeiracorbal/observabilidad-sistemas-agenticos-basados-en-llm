import { JsonView } from './JsonView';
import type { TimelineItem } from '../types';
import { formatDateTime, formatDuration } from '../utils/time';

const KIND_LABELS: Record<string, string> = {
  input: 'entrada',
  output: 'salida',
  span: 'tramo',
  decision: 'decisión',
  model: 'modelo',
  tool: 'herramienta',
  memory: 'memoria',
  error: 'error',
  event: 'evento',
};

const ROLE_LABELS: Record<string, string> = {
  call: 'llamada',
  response: 'respuesta',
  execution: 'ejecución',
  annotation: 'anotación',
  evento: 'evento',
};

export function EventInspector({ item }: { item?: TimelineItem | null }) {
  if (!item) {
    return (
      <aside className="inspector panel">
        <h2>Detalle</h2>
        <p className="muted">Selecciona un paso de la lista para ver su información.</p>
      </aside>
    );
  }

  const role = item.event_role ?? 'evento';

  return (
    <aside className="inspector panel">
      <h2>{item.title}</h2>
      <div className="inspector-meta">
        <div><span>Tipo</span><strong>{KIND_LABELS[item.kind] ?? item.kind}</strong></div>
        <div><span>Actor</span><strong>{item.actor}</strong></div>
        <div><span>Flujo</span><strong>{item.source_actor} → {item.target_actor}</strong></div>
        <div><span>Relación</span><strong>{item.relation}</strong></div>
        <div><span>Rol</span><strong>{ROLE_LABELS[role] ?? role}</strong></div>
        <div><span>Visibilidad</span><strong>{item.visibility === 'hidden' ? 'oculto' : 'público'}</strong></div>
        <div><span>Tramo</span><code>{item.span_id ? `${item.span_id.slice(0, 8)}…` : '—'}</code></div>
        <div><span>Inicio</span><strong>{formatDateTime(item.started_at ?? item.created_at)}</strong></div>
        <div><span>Fin</span><strong>{formatDateTime(item.ended_at)}</strong></div>
        <div><span>Duración</span><strong>{formatDuration(item.duration_ms)}</strong></div>
      </div>
      {item.description && <p className="muted">{item.description}</p>}
      {item.metrics && Object.keys(item.metrics).length > 0 && (
        <>
          <p className="inspector-section-label">Métricas</p>
          <JsonView value={item.metrics} />
        </>
      )}
      {Array.isArray(item.content?.hidden_reasoning) && item.content.hidden_reasoning.length > 0 && (
        <>
          <p className="inspector-section-label">Razonamiento interno</p>
          <div className="hidden-reasoning">
            {item.content.hidden_reasoning.map((step, index) => (
              <div key={index} className="hidden-reasoning__step">
                <strong>#{String((step as { step?: number }).step ?? index + 1).padStart(2, '0')}</strong>
                <JsonView value={step} />
              </div>
            ))}
          </div>
        </>
      )}
      {item.content && Object.keys(item.content).length > 0 && (
        <>
          <p className="inspector-section-label">Contenido</p>
          <JsonView value={item.content} />
        </>
      )}
      <p className="inspector-section-label">Registro completo</p>
      <JsonView value={item.payload} />
    </aside>
  );
}
