import type { CSSProperties, ReactNode } from 'react';

import type { TimelineItem } from '../types';
import { formatDateTime, formatDuration } from '../utils/time';
import { formatTokenMetrics } from '../utils/tokens';

const kindIcon: Record<string, string> = {
  input: '⌁',
  output: '✓',
  span: '⬡',
  decision: '◇',
  model: '◈',
  tool: '⚙',
  memory: '◉',
  error: '⚠',
  event: '•',
};

const agentToneByActor: Record<string, string> = {
  MainAgent: 'main',
  PlannerAgent: 'planner',
  MathAgent: 'math',
  WriterAgent: 'writer',
  TimeAgent: 'time',
  ResearchAgent: 'research',
};

type TimelineRenderNode =
  | {
      type: 'item';
      item: TimelineItem;
    }
  | {
      type: 'group';
      spanId: string;
      actor: string;
      tone: string;
      startItem: TimelineItem;
      endItem?: TimelineItem;
      children: TimelineRenderNode[];
    };

export function TimelineView({
  items,
  selectedItemId,
  onSelect,
}: {
  items: TimelineItem[];
  selectedItemId?: string;
  onSelect: (item: TimelineItem) => void;
}) {
  const tree = buildTimelineTree(items);
  const agents = collectAgents(tree);

  return (
    <section className="panel timeline-panel">
      <div className="panel-heading">
        <h2>Actividad</h2>
        <span className="muted">{items.length} pasos</span>
      </div>
      {agents.length > 0 && (
        <div className="timeline-agent-legend" aria-label="Leyenda de spans por agente">
          {agents.map((agent) => (
            <span key={agent.actor} className={`timeline-agent-chip timeline-agent-chip--${agent.tone}`}>
              {agent.actor}
            </span>
          ))}
        </div>
      )}
      <div className="timeline-list">
        {tree.map((node) => renderNode(node, selectedItemId, onSelect))}
      </div>
    </section>
  );
}

function renderNode(
  node: TimelineRenderNode,
  selectedItemId: string | undefined,
  onSelect: (item: TimelineItem) => void,
): ReactNode {
  if (node.type === 'item') {
    return renderItem(node.item, selectedItemId, onSelect);
  }

  return (
    <section
      key={`group:${node.spanId}`}
      className={`timeline-span-group timeline-span-group--${node.tone}`}
      style={{ '--depth': node.startItem.depth } as CSSProperties}
    >
      <div className="timeline-span-group__rail" aria-hidden />
      {renderItem(node.startItem, selectedItemId, onSelect, 'timeline-item--group-boundary')}
      <div className="timeline-span-group__body">
        {node.children.map((child) => renderNode(child, selectedItemId, onSelect))}
      </div>
      {node.endItem && renderItem(node.endItem, selectedItemId, onSelect, 'timeline-item--group-boundary timeline-item--group-footer')}
    </section>
  );
}

function renderItem(
  item: TimelineItem,
  selectedItemId: string | undefined,
  onSelect: (item: TimelineItem) => void,
  extraClassName?: string,
): ReactNode {
  return (
    <button
      key={item.id}
      className={`timeline-item timeline-item--${item.kind} ${selectedItemId === item.id ? 'timeline-item--active' : ''} ${extraClassName ?? ''}`}
      onClick={() => onSelect(item)}
      style={{ '--depth': item.depth } as CSSProperties}
    >
      <span className="timeline-index">{String(item.sequence).padStart(2, '0')}</span>
      <span className="timeline-icon">{kindIcon[item.kind] ?? '•'}</span>
      <span className="timeline-content">
        <strong>{item.title}</strong>
        <small>{flowLabel(item)}</small>
        <small>{visibilityLabel(item)}{item.subtitle}{tokenLabel(item)}</small>
      </span>
      <span className="timeline-time">
        <strong>{formatDuration(item.duration_ms)}</strong>
        <small>{formatDateTime(item.started_at ?? item.created_at)}</small>
      </span>
    </button>
  );
}

function buildTimelineTree(items: TimelineItem[]): TimelineRenderNode[] {
  const { nodes } = parseTimelineNodes(items, 0);
  return nodes;
}

function parseTimelineNodes(
  items: TimelineItem[],
  startIndex: number,
  closingSpanId?: string,
): { nodes: TimelineRenderNode[]; nextIndex: number; closingItem?: TimelineItem } {
  const nodes: TimelineRenderNode[] = [];
  let index = startIndex;

  while (index < items.length) {
    const item = items[index];
    if (closingSpanId && isAgentSpanEnd(item, closingSpanId)) {
      return { nodes, nextIndex: index + 1, closingItem: item };
    }

    if (isAgentSpanStart(item)) {
      const nested = parseTimelineNodes(items, index + 1, item.span_id ?? undefined);
      nodes.push({
        type: 'group',
        spanId: item.span_id ?? item.id,
        actor: item.actor,
        tone: agentTone(item.actor),
        startItem: item,
        endItem: nested.closingItem,
        children: nested.nodes,
      });
      index = nested.nextIndex;
      continue;
    }

    nodes.push({ type: 'item', item });
    index += 1;
  }

  return { nodes, nextIndex: index };
}

function isAgentSpanStart(item: TimelineItem): boolean {
  return item.kind === 'span' && item.event_type === 'span_started' && spanType(item) === 'agent';
}

function isAgentSpanEnd(item: TimelineItem, spanId: string): boolean {
  return item.kind === 'span' && item.event_type === 'span_ended' && item.span_id === spanId && spanType(item) === 'agent';
}

function spanType(item: TimelineItem): string | undefined {
  const payload = item.payload as { span?: { type?: string } } | undefined;
  return payload?.span?.type;
}

function agentTone(actor: string): string {
  return agentToneByActor[actor] ?? 'other';
}

function collectAgents(tree: TimelineRenderNode[]): Array<{ actor: string; tone: string }> {
  const seen = new Map<string, string>();

  function visit(node: TimelineRenderNode) {
    if (node.type === 'group') {
      if (!seen.has(node.actor)) {
        seen.set(node.actor, node.tone);
      }
      node.children.forEach(visit);
    }
  }

  tree.forEach(visit);
  return Array.from(seen, ([actor, tone]) => ({ actor, tone }));
}

function flowLabel(item: TimelineItem): string {
  if (item.source_actor === item.target_actor) {
    return `${item.actor} · ${item.relation}`;
  }
  return `${item.source_actor} ─ ${item.relation} → ${item.target_actor}`;
}

function tokenLabel(item: TimelineItem): string {
  if (item.kind !== 'model') return '';
  return formatTokenMetrics(item.metrics?.input_tokens, item.metrics?.output_tokens);
}

function visibilityLabel(item: TimelineItem): string {
  return item.visibility === 'hidden' ? 'oculto · ' : '';
}
