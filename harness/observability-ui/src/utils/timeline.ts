import type { TimelineItem } from '../types';

export function summarizeTimeline(timeline: TimelineItem[]) {
  return timeline.reduce(
    (summary, item) => {
      if (item.event_type === 'span_started') summary.spans += 1;
      if (item.kind === 'decision') summary.decisions += 1;
      if (item.kind === 'model') summary.models += 1;
      if (item.kind === 'tool') summary.tools += 1;
      if (item.kind === 'memory') summary.memories += 1;
      if (item.kind === 'error') summary.errors += 1;
      return summary;
    },
    { spans: 0, decisions: 0, models: 0, tools: 0, memories: 0, errors: 0 },
  );
}
