// EventSelector — top-of-app dropdown for switching between events.
// Per LD-467 MULTI_EVENT_SELECTOR_V1.
//
// Reads /api/event/list, posts /api/event/load on change. Server's
// event_load_lock + monotonic event_generation guarantee atomic swap;
// async jobs pinned to old gen are rejected at terminal write per LD-460.

import { useEffect, useState } from 'preact/hooks';
import { activeScope, makeScope } from '../state/scope';
import { apiGet } from '../api/client';
import { MUTATION_ENDPOINTS } from '../api/endpoints';

interface EventListItem {
  event_id: string;
  path: string;
  storyboards: string[];
  active_storyboard: string;
  is_current: boolean;
}

interface EventListResponse {
  ok: boolean;
  events?: EventListItem[];
  current_event_id?: string;
  current_generation?: number;
}

export function EventSelector() {
  const [events, setEvents] = useState<EventListItem[]>([]);
  const [current, setCurrent] = useState<string>(activeScope.value.event_id);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await apiGet<EventListResponse>('event_list');
      if (cancelled) return;
      if (res.ok && res.data?.events) {
        setEvents(res.data.events);
        if (res.data.current_event_id) setCurrent(res.data.current_event_id);
      } else {
        setErr(res.error ?? 'failed to load events');
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const onChange = async (e: Event) => {
    const target = e.target as HTMLSelectElement;
    const newEventId = target.value;
    if (newEventId === current) return;
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch(MUTATION_ENDPOINTS.event_load, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: newEventId }),
      });
      if (!res.ok) {
        const txt = await res.text().catch(() => '');
        setErr(`HTTP ${res.status}: ${txt.slice(0, 100)}`);
        // Revert selection.
        target.value = current;
        return;
      }
      const data = (await res.json()) as { event_id: string; event_generation: number };
      setCurrent(data.event_id);
      activeScope.value = makeScope(data.event_id, null, data.event_generation);
      // S5.5b Bug 4 fix B: update URL with ?event=<id> BEFORE reload so
      // ScopeBoundary on next mount reads the correct event from the URL
      // (its first resolution source). Belt + suspenders with the new
      // /api/event/current endpoint (fix A).
      try {
        const url = new URL(window.location.href);
        url.searchParams.set('event', data.event_id);
        window.history.replaceState({}, '', url.toString());
      } catch {
        // window.history not available in headless contexts — fall through.
      }
      // Hard-reload so all v59 stores re-hydrate from the new event.
      window.location.reload();
    } catch (e) {
      setErr(String(e));
      target.value = current;
    } finally {
      setLoading(false);
    }
  };

  return (
    <div class="mn-event-selector" data-testid="event-selector">
      <label class="mn-event-selector-label" for="mn-event-select">Event:</label>
      <select
        id="mn-event-select"
        data-testid="event-select"
        class="mn-event-select"
        value={current}
        onChange={onChange}
        disabled={loading}
      >
        {events.length === 0 ? (
          <option value={current}>{current}</option>
        ) : (
          events.map((e) => (
            <option key={e.event_id} value={e.event_id}>
              {e.event_id}
              {e.is_current ? ' (current)' : ''}
            </option>
          ))
        )}
      </select>
      {loading ? <span class="mn-event-loading">switching…</span> : null}
      {err ? <span class="mn-event-error" data-testid="event-error">{err}</span> : null}
    </div>
  );
}
