import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';

export type ArtifactKind = 'input' | 'agent' | 'decision' | 'model' | 'tool' | 'memory' | 'error' | 'output';

export interface ArtifactNodeData extends Record<string, unknown> {
  kind: ArtifactKind;
  icon: string;
  title: string;
  subtitle: string;
  meta?: string;
  description?: string;
  status?: string;
}

export type ArtifactFlowNode = Node<ArtifactNodeData, 'artifact'>;

export function ArtifactNode({ data, selected }: NodeProps<ArtifactFlowNode>) {
  return (
    <div className={`artifact-node artifact-node--${data.kind} ${selected ? 'artifact-node--selected' : ''}`}>
      <Handle type="target" position={Position.Left} className="artifact-handle" />
      <div className="artifact-node__header">
        <span className="artifact-node__icon">{data.icon}</span>
        <div>
          <strong>{data.title}</strong>
          <small>{data.subtitle}</small>
        </div>
      </div>
      {data.description && <p>{data.description}</p>}
      <div className="artifact-node__footer">
        {data.meta && <span>{data.meta}</span>}
        {data.status && <em>{data.status}</em>}
      </div>
      <Handle type="source" position={Position.Right} className="artifact-handle" />
    </div>
  );
}
