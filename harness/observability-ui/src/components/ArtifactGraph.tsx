import { Background, Controls, MarkerType, MiniMap, ReactFlow, type Edge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { ArtifactNode, type ArtifactFlowNode, type ArtifactKind, type ArtifactNodeData } from './ArtifactNode';
import type { Run, TimelineItem } from '../types';
import { formatDuration } from '../utils/time';
import { formatTokenMetrics } from '../utils/tokens';

const nodeTypes = {
  artifact: ArtifactNode,
};

const artifactKinds: ArtifactKind[] = ['input', 'agent', 'decision', 'model', 'tool', 'memory', 'error', 'output'];

const legendLabels: Record<ArtifactKind, string> = {
  input: 'entrada',
  agent: 'agente',
  decision: 'decisión',
  model: 'modelo',
  tool: 'tool',
  memory: 'memoria',
  error: 'error',
  output: 'salida',
};

type PendingArtifactNode = ArtifactFlowNode & {
  level: number;
  sequence: number;
};

export function ArtifactGraph({ run, timeline }: { run: Run; timeline: TimelineItem[] }) {
  const { nodes, edges } = buildGraph(timeline);

  return (
    <section className="panel graph-panel">
      <div className="panel-heading">
        <h2>Diagrama del turno</h2>
        <span className="muted">{nodes.length} nodos · {edges.length} enlaces</span>
      </div>

      <div className="artifact-legend">
        {artifactKinds.map((kind) => (
          <span key={kind} className={`legend-chip legend-chip--${kind}`}>{legendLabels[kind]}</span>
        ))}
      </div>

      <div className="flow-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.18 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
        >
          <MiniMap pannable zoomable nodeClassName={(node) => `minimap-node minimap-node--${node.data.kind}`} />
          <Controls />
          <Background />
        </ReactFlow>
      </div>
    </section>
  );
}

function buildGraph(timeline: TimelineItem[]): { nodes: ArtifactFlowNode[]; edges: Edge[] } {
  const ordered = [...timeline].sort((a, b) => a.sequence - b.sequence);
  const nodes: PendingArtifactNode[] = ordered.map((item) => ({
    id: item.id,
    type: 'artifact',
    position: { x: 0, y: 0 },
    level: levelFor(item),
    sequence: item.sequence,
    data: nodeData(item),
  }));

  const edges: Edge[] = [];
  for (let index = 1; index < ordered.length; index += 1) {
    const previous = ordered[index - 1];
    const current = ordered[index];
    edges.push({
      id: `edge:${previous.id}:${current.id}`,
      source: previous.id,
      target: current.id,
      label: edgeLabel(current),
      markerEnd: { type: MarkerType.ArrowClosed },
      className: current.status === 'running' ? 'artifact-edge artifact-edge--animated' : 'artifact-edge',
      animated: current.status === 'running',
      labelBgPadding: [8, 4],
      labelBgBorderRadius: 8,
      labelBgStyle: { fill: '#0f172a', fillOpacity: 0.92 },
      labelStyle: { fill: '#cbd5e1', fontSize: 11, fontWeight: 700 },
    });
  }

  return { nodes: layout(nodes), edges };
}

function nodeData(item: TimelineItem): ArtifactNodeData {
  const response = typeof item.content?.response === 'string' ? item.content.response : undefined;
  const output = typeof item.content?.output === 'string' ? item.content.output : undefined;
  const description = response || output || item.description || eventDescription(item);
  const tokens = item.kind === 'model' ? formatTokenMetrics(item.metrics?.input_tokens, item.metrics?.output_tokens) : '';
  const visibility = item.visibility === 'hidden' ? 'hidden · ' : '';
  const kind = artifactKind(item);
  const memoryMeta = kind === 'memory' ? ' · plugin externo · determinista' : '';
  return {
    kind,
    icon: iconFor(item),
    title: `${item.sequence}. ${item.title}`,
    subtitle: memorySubtitle(item, kind),
    description: truncate(String(description), 160),
    meta: `${visibility}${item.event_role ?? 'evento'} · ${item.relation}${memoryMeta}${tokens} · ${formatDuration(item.duration_ms)}`,
    status: item.status,
  };
}

function memorySubtitle(item: TimelineItem, kind: ArtifactKind): string {
  if (kind !== 'memory') {
    return `${item.actor} · ${item.event_type}`;
  }
  if (item.source_actor !== item.target_actor) {
    return `${item.source_actor} → ${item.target_actor} · ${item.event_type}`;
  }
  return `${item.actor} · plugin mnemo · ${item.event_type}`;
}

function edgeLabel(item: TimelineItem): string {
  if (item.kind === 'memory' || item.actor_type === 'memory' || item.target_actor_type === 'memory') {
    return `${item.sequence}. ${item.source_actor} → ${item.target_actor} · ${item.relation}`;
  }
  if (item.source_actor === item.target_actor) {
    return `${item.sequence}. ${item.actor} · ${item.relation}`;
  }
  return `${item.sequence}. ${item.source_actor} → ${item.target_actor}`;
}

function eventDescription(item: TimelineItem): string {
  if (item.source_actor === item.target_actor) {
    return `Evento generado sobre ${item.actor}: ${item.relation}`;
  }
  return `${item.source_actor} ${item.relation} ${item.target_actor}`;
}

function artifactKind(item: TimelineItem): ArtifactKind {
  if (item.kind === 'decision') {
    const stage = (item.payload as { decision?: { stage?: string } } | undefined)?.decision?.stage;
    if (stage === 'memory_observation' || stage === 'memory_persistence') {
      return 'memory';
    }
  }
  if (item.kind === 'span') {
    const spanType = (item.payload as { span?: { type?: string } } | undefined)?.span?.type;
    if (spanType === 'model') return 'model';
    if (spanType === 'tool') return 'tool';
    if (spanType === 'memory') return 'memory';
    return 'agent';
  }
  if (item.kind === 'event') return 'decision';
  return item.kind;
}

function iconFor(item: TimelineItem): string {
  if (item.kind === 'input') return '⌁';
  if (item.kind === 'output') return '✓';
  if (item.kind === 'span') {
    const spanType = (item.payload as { span?: { type?: string } } | undefined)?.span?.type;
    if (spanType === 'model') return '◈';
    if (spanType === 'tool') return '⚙';
    if (spanType === 'memory') return '◉';
    return '⬡';
  }
  if (item.kind === 'decision') {
    const stage = (item.payload as { decision?: { stage?: string } } | undefined)?.decision?.stage;
    if (stage === 'memory_observation' || stage === 'memory_persistence') {
      return '◉';
    }
    return '◇';
  }
  if (item.kind === 'model') return '◈';
  if (item.kind === 'tool') return '⚙';
  if (item.kind === 'memory') return '◉';
  if (item.kind === 'error') return '⚠';
  if (item.kind === 'event') return '•';
  return '•';
}

function levelFor(item: TimelineItem): number {
  if (item.kind === 'input') return 0;
  if (item.kind === 'output') return 6;
  if (item.kind === 'error') return 5;
  if (item.actor_type === 'llm') return 3;
  if (item.actor_type === 'subagent') return 2;
  if (item.actor_type === 'tool') return 4;
  if (item.actor_type === 'memory' || item.target_actor_type === 'memory') return 5;
  if (item.kind === 'memory') return 5;
  if (item.actor === 'MainAgent') return 1;
  return 1 + Math.min(item.depth, 3);
}

function layout(nodes: PendingArtifactNode[]): ArtifactFlowNode[] {
  return nodes.map(({ level, sequence, ...flowNode }) => ({
    ...flowNode,
    position: {
      x: level * 340,
      y: (sequence - 1) * 155,
    },
  }));
}

function truncate(value: string, maxLength: number): string {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}…` : value;
}
