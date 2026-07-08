import type { Status } from '../types';
import { STATUS_LABELS } from '../ui-copy';

export function StatusBadge({ status }: { status?: Status }) {
  const value = status ?? 'unknown';
  const label = STATUS_LABELS[value as keyof typeof STATUS_LABELS] ?? value;
  return <span className={`status-badge status-${value}`}>{label}</span>;
}
