import { useEffect, useRef, useState } from 'react';

import type { LlmStreamState } from '../types-stream';
import { tryParseJson } from '../utils/json';
import { JsonTreeView } from './JsonTreeView';

export function LiveStreamCard({
  stream,
  label,
  lazy = false,
}: {
  stream: LlmStreamState;
  label: string;
  lazy?: boolean;
}) {
  const shellRef = useRef<HTMLDivElement>(null);
  const eager = !lazy || stream.status === 'streaming';
  const [bodyVisible, setBodyVisible] = useState(eager);

  useEffect(() => {
    if (eager) {
      setBodyVisible(true);
      return;
    }
    const node = shellRef.current;
    if (!node) {
      return;
    }
    const root = node.closest('.live-stream-decisions__list--scroll, .live-stream-grid');
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setBodyVisible(true);
          observer.disconnect();
        }
      },
      { root, rootMargin: '96px 0px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [eager, stream.purpose, stream.status]);

  const parsedJson = stream.text.trim() ? tryParseJson(stream.text) : undefined;

  return (
    <article className={`live-stream-card live-stream-card--${stream.status}`}>
      <header className="live-stream-card__header">
        <strong>{label}</strong>
        <StreamTokenBadges stream={stream} />
      </header>
      <div ref={shellRef} className="live-stream-card__body-shell">
        {bodyVisible ? (
          stream.status === 'streaming' && !stream.text.trim() ? (
            <div className="live-stream-card__loader" aria-label="Generando contenido">
              <span className="live-stream-card__loader-bar" />
              <span className="live-stream-card__loader-bar" />
              <span className="live-stream-card__loader-bar" />
            </div>
          ) : parsedJson !== undefined ? (
            <JsonTreeView value={parsedJson} className="live-stream-card__body custom-scroll" />
          ) : (
            <pre className="live-stream-card__body custom-scroll">{stream.text || '…'}</pre>
          )
        ) : (
          <div className="live-stream-card__placeholder">Desplázate para ver el contenido.</div>
        )}
      </div>
    </article>
  );
}

function StreamTokenBadges({ stream }: { stream: LlmStreamState }) {
  if (stream.status === 'streaming') {
    return (
      <span className="live-stream-card__metrics">
        <span className="stream-token-badge stream-token-badge--status">en curso</span>
      </span>
    );
  }

  if (stream.status !== 'completed') {
    return null;
  }

  if (stream.purpose === 'final_response') {
    return (
      <span className="live-stream-card__metrics">
        <TokenBadge label="tokens out" value={stream.output_tokens ?? 0} />
      </span>
    );
  }

  return (
    <span className="live-stream-card__metrics">
      <TokenBadge label="tokens in" value={stream.input_tokens ?? 0} />
      <TokenBadge label="tokens out" value={stream.output_tokens ?? 0} />
    </span>
  );
}

function TokenBadge({ label, value }: { label: string; value: number }) {
  return (
    <span className="stream-token-badge">
      <span className="stream-token-badge__label">{label}</span>
      <strong>{value.toLocaleString('es-ES')}</strong>
    </span>
  );
}
