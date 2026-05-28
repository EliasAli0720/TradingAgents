import { useEffect, useState } from 'react';
import { sseUrl } from '@/api/client';

export type RunEvent = { event: string; data: any };

const TERMINAL = new Set(['run_succeeded', 'run_failed', 'run_cancelled']);

export function useRunEvents(runId: string | undefined): {
  events: RunEvent[];
  terminated: boolean;
} {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [terminated, setTerminated] = useState(false);

  useEffect(() => {
    if (!runId) return;
    setEvents([]);
    setTerminated(false);
    const es = new EventSource(sseUrl(`/runs/${runId}/events`), { withCredentials: true });

    const handlers = [
      'run_queued',
      'run_dispatching',
      'run_started',
      'run_requeued',
      'agent_step',
      'run_progress',
      'run_cancelling',
      'run_succeeded',
      'run_failed',
      'run_cancelled',
    ];
    const onAny = (name: string) => (evt: MessageEvent) => {
      let data: any = evt.data;
      try { data = JSON.parse(evt.data); } catch { /* keep raw */ }
      setEvents((prev) => [...prev, { event: name, data }]);
      if (TERMINAL.has(name)) {
        setTerminated(true);
        es.close();
      }
    };
    handlers.forEach((n) => es.addEventListener(n, onAny(n)));

    es.onerror = () => {
      // EventSource auto-reconnects; mark terminated only on close.
    };

    return () => es.close();
  }, [runId]);

  return { events, terminated };
}
