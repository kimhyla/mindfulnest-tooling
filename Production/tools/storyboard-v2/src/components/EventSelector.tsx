// EventSelector — top-right tab-strip dropdown for cross-tab event scope.
// Per LD-467 MULTI_EVENT_SELECTOR_V1 + D1 tie-all-tabs (supersedes LD-687).
//
// Reads /api/event/list, posts /api/event/load on change. Updates activeScope
// and emits SCOPE_EVENT_CHANGED so all tabs re-fetch (no full page reload).

import { useEffect, useState } from 'preact/hooks';
import { activeScope, activeProjectType, makeScope, scopeKey } from '../state/scope';
import { apiGet, emitScopeEventChanged, loadEvent, noteClientPinnedEvent } from '../api/client';

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
    setCurrent(activeScope.value.event_id);
  }, [activeScope.value.event_id]);

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
      // Wave 3 (blocker #52 F-S2-004): use the loadEvent client helper instead
      // of a raw fetch — gets centralized error handling, scope-mismatch retry,
      // and consistent shape with the rest of the mutation channel.
      const result = await loadEvent(newEventId);
      if (!result.ok) {
        setErr(`HTTP ${result.status}: ${(result.error ?? '').slice(0, 100)}`);
        target.value = current;
        return;
      }
      const data = result.data;
      if (!data) {
        setErr('event_load returned no data');
        target.value = current;
        return;
      }
      setCurrent(data.event_id);
      activeScope.value = makeScope(data.event_id, null, data.event_generation);
      noteClientPinnedEvent(data.event_id);
      activeProjectType.value = 'event';
      try {
        const url = new URL(window.location.href);
        url.searchParams.delete('milestone');
        url.searchParams.set('event', data.event_id);
        window.history.replaceState({}, '', url.toString());
      } catch {
        // window.history not available in headless contexts — fall through.
      }
      emitScopeEventChanged({
        event_id: data.event_id,
        event_generation: data.event_generation,
        scope_key: scopeKey(activeScope.value),
        source: 'scope-event-selector',
      });
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
        class="mn-event-select"
        data-testid="event-select"
        aria-label="scope-event-selector"
        value={current}
        onChange={onChange}
        disabled={loading}
      >
        {events.length === 0 ? (
          <option value={current} data-testid={`scope-event-option-${current}`}>
            {current}
          </option>
        ) : (
          events.map((ev) => (
            <option
              key={ev.event_id}
              value={ev.event_id}
              data-testid={`scope-event-option-${ev.event_id}`}
            >
              {ev.event_id}
              {ev.is_current ? ' (current)' : ''}
            </option>
          ))
        )}
      </select>
      {loading ? <span class="mn-event-loading">switching…</span> : null}
      {err ? <span class="mn-event-error" data-testid="event-error">{err}</span> : null}
    </div>
  );
}
