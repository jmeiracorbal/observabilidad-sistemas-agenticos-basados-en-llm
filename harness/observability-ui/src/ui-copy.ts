import type { Status } from './types';

export const STATUS_LABELS: Record<Status | 'unknown', string> = {
  completed: 'Completado',
  failed: 'Error',
  running: 'En curso',
  unknown: 'Desconocido',
};
