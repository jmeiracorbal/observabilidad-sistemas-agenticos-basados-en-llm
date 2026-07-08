import { useState, type CSSProperties } from 'react';

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function JsonPrimitive({ value }: { value: unknown }) {
  if (value === null) {
    return <span className="json-tree__null">null</span>;
  }
  if (typeof value === 'boolean') {
    return <span className="json-tree__boolean">{String(value)}</span>;
  }
  if (typeof value === 'number') {
    return <span className="json-tree__number">{value}</span>;
  }
  if (typeof value === 'string') {
    return <span className="json-tree__string">{value === '' ? '""' : `"${value}"`}</span>;
  }
  return <span className="json-tree__unknown">{String(value)}</span>;
}

function JsonNode({
  name,
  value,
  depth,
}: {
  name?: string;
  value: unknown;
  depth: number;
}) {
  const [open, setOpen] = useState(depth < 1);
  const indent = { paddingLeft: `${depth * 14}px` } as CSSProperties;

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return (
        <div className="json-tree__row" style={indent}>
          {name !== undefined && <span className="json-tree__key">{name}: </span>}
          <span className="json-tree__bracket">[]</span>
        </div>
      );
    }

    return (
      <div className="json-tree__block">
        <button
          type="button"
          className="json-tree__row json-tree__row--toggle"
          style={indent}
          onClick={() => setOpen((current) => !current)}
        >
          <span className="json-tree__caret" aria-hidden>{open ? '▾' : '▸'}</span>
          {name !== undefined && <span className="json-tree__key">{name}</span>}
          <span className="json-tree__meta">[{value.length}]</span>
        </button>
        {open && value.map((entry, index) => (
          <JsonNode key={index} name={String(index)} value={entry} depth={depth + 1} />
        ))}
      </div>
    );
  }

  if (isRecord(value)) {
    const entries = Object.entries(value);
    if (entries.length === 0) {
      return (
        <div className="json-tree__row" style={indent}>
          {name !== undefined && <span className="json-tree__key">{name}: </span>}
          <span className="json-tree__bracket">{'{}'}</span>
        </div>
      );
    }

    return (
      <div className="json-tree__block">
        <button
          type="button"
          className="json-tree__row json-tree__row--toggle"
          style={indent}
          onClick={() => setOpen((current) => !current)}
        >
          <span className="json-tree__caret" aria-hidden>{open ? '▾' : '▸'}</span>
          {name !== undefined && <span className="json-tree__key">{name}</span>}
          <span className="json-tree__meta">{'{'}{entries.length}{'}'}</span>
        </button>
        {open && entries.map(([key, entry]) => (
          <JsonNode key={key} name={key} value={entry} depth={depth + 1} />
        ))}
      </div>
    );
  }

  return (
    <div className="json-tree__row" style={indent}>
      {name !== undefined && <span className="json-tree__key">{name}: </span>}
      <JsonPrimitive value={value} />
    </div>
  );
}

export function JsonTreeView({ value, className }: { value: unknown; className?: string }) {
  return (
    <div className={`json-tree ${className ?? ''}`}>
      <JsonNode value={value} depth={0} />
    </div>
  );
}
