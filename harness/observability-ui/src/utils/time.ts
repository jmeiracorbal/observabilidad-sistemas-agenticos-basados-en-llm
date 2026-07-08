export function toDate(value?: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function durationMs(start?: string | null, end?: string | null): number | null {
  const startDate = toDate(start);
  const endDate = toDate(end);
  if (!startDate || !endDate) return null;
  return Math.max(0, endDate.getTime() - startDate.getTime());
}

export function formatTime(value?: string | null): string {
  const date = toDate(value);
  if (!date) return '—';
  return new Intl.DateTimeFormat('es', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date);
}

export function formatDateTime(value?: string | null): string {
  const date = toDate(value);
  if (!date) return '—';
  return new Intl.DateTimeFormat('es', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(date);
}

export function formatDuration(ms?: number | null): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(2)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes} min ${rest} s`;
}

export function compareTime(a?: string | null, b?: string | null): number {
  return (toDate(a)?.getTime() ?? 0) - (toDate(b)?.getTime() ?? 0);
}
