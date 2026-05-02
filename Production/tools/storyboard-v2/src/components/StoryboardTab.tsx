// StoryboardTab — main beat editing surface. Session 1 placeholder; renders
// the scope label and a few placeholder beat cards. Real L[] hydration lands
// in Session 1.5+ once /api/v2/event-state has its scope guard.

import { useEffect, useState } from 'preact/hooks';
import { activeScope, scopeKey } from '../state/scope';
import { apiGet } from '../api/client';

interface EventState {
  beats?: Array<{ id?: string; beat_id?: string; speaker?: string; text?: string }>;
  L?: Array<{ id?: string; beat_id?: string; speaker?: string; text?: string }>;
}

export function StoryboardTab() {
  const [state, setState] = useState<EventState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await apiGet<EventState>('v2_event_state', {
        event_id: activeScope.value.event_id,
      });
      if (cancelled) return;
      setLoading(false);
      if (res.ok && res.data) {
        setState(res.data);
        setError(null);
      } else {
        setError(res.error ?? 'unknown error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const beats = state?.L ?? state?.beats ?? [];

  return (
    <section class="mn-tab-pane mn-storyboard-pane" data-testid="pane-storyboard">
      <header class="mn-pane-header">
        <h2>Storyboard</h2>
        <span class="mn-scope-chip" data-testid="storyboard-scope-chip">
          scope: {scopeKey(activeScope.value)}
        </span>
      </header>
      {loading ? (
        <p class="mn-loading" data-testid="storyboard-loading">
          Loading event state&hellip;
        </p>
      ) : error ? (
        <div class="mn-empty" data-testid="storyboard-error">
          <p class="mn-warn">Could not reach /api/v2/event-state.</p>
          <p class="mn-dim">{error}</p>
          <p class="mn-dim">
            (Session 1 is read-only preview. Session 1.5 lands the scope-guarded
            handler. Production server may not have the v59 endpoint yet.)
          </p>
        </div>
      ) : beats.length === 0 ? (
        <div class="mn-empty" data-testid="storyboard-empty">
          <p>No beats in this event yet.</p>
          <p class="mn-dim">L[] / beats array is empty.</p>
        </div>
      ) : (
        <ol class="mn-beat-list">
          {beats.map((b, i) => (
            <li
              key={b.id ?? b.beat_id ?? i}
              class="mn-beat-card"
              data-testid={`beat-card-${i}`}
              data-beat-id={b.beat_id ?? b.id ?? `beat_${i}`}
            >
              <div class="mn-beat-meta">
                <span class="mn-beat-index">#{i + 1}</span>
                <span class="mn-beat-speaker">{b.speaker ?? 'speaker'}</span>
              </div>
              <p class="mn-beat-text">{b.text ?? '—'}</p>
            </li>
          ))}
        </ol>
      )}
      <footer class="mn-pane-footer">
        <p class="mn-dim mn-readonly-banner" data-testid="storyboard-readonly">
          Read-only preview &mdash; mutation channel pathappPatch() ships in Session 1.5.
        </p>
      </footer>
    </section>
  );
}
