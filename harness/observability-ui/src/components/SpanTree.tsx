import type { CSSProperties } from 'react';

import type { SpanNode } from '../types';
import { formatDuration, durationMs } from '../utils/time';
import { StatusBadge } from './StatusBadge';

export function SpanTree({ tree }: { tree: SpanNode[] }) {
  return (
    <section className="panel span-tree-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Jerarquía</p>
          <h2>Árbol de spans</h2>
        </div>
      </div>
      <div className="span-tree">
        {tree.map((node) => <SpanTreeNode key={node.span.id} node={node} depth={0} />)}
      </div>
    </section>
  );
}

function SpanTreeNode({ node, depth }: { node: SpanNode; depth: number }) {
  const childEvents = (node.decision_events ?? []).length + node.model_calls.length + node.tool_calls.length + node.memory_events.length + node.errors.length;

  return (
    <div className="span-tree-node" style={{ '--depth': depth } as CSSProperties}>
      <div className="span-tree-node__card">
        <div>
          <strong>{node.span.name}</strong>
          <small>{node.span.type} · {formatDuration(durationMs(node.span.started_at, node.span.ended_at))}</small>
        </div>
        <div className="span-tree-node__meta">
          <StatusBadge status={node.span.status} />
          <span>{childEvents} eventos</span>
        </div>
      </div>
      {node.children.map((child) => <SpanTreeNode key={child.span.id} node={child} depth={depth + 1} />)}
    </div>
  );
}
