// ProductionMapTab — 5th tab in v59. Per-module per-segment status matrix.
// Per LD-465 PRODUCTION_MAP_V1.
//
// Reads /api/production/map (60s TTL cache server-side). Renders a matrix:
//   rows = modules (m_number, creature_name, video_role)
//   cols = phase_a, phase_b, intro_or_resolution, final_concat
//   cells = ✅/⏳/❌ + count + latest filename

import { useEffect, useState } from 'preact/hooks';
import { apiGet } from '../api/client';
import { activeScope, scopeKey, makeScope } from '../state/scope';
import { MUTATION_ENDPOINTS } from '../api/endpoints';

// Custom event the App listens for. ProductionMapTab dispatches this on
// cell click; App switches activeTab to 'storyboard'.
export const MAP_CELL_NAVIGATE_EVENT = 'mn:map-cell-navigate';

interface SegmentStatus {
  status: 'ready' | 'missing' | string;
  count: number;
  latest?: string;
}

interface MapRow {
  m_number: number;
  creature_name: string;
  video_role: string;
  event_dir: string;
  segments: Record<string, SegmentStatus>;
}

interface MapResponse {
  ok: boolean;
  modules?: MapRow[];
  generated_at?: string;
}

const SEGMENTS = [
  { key: 'phase_a', label: 'Phase A' },
  { key: 'phase_b', label: 'Phase B' },
  { key: 'intro_or_resolution', label: 'Storyboard' },
  { key: 'final_concat', label: 'Final concat' },
] as const;

function statusGlyph(s: SegmentStatus | undefined): string {
  if (!s) return '—';
  if (s.status === 'ready') return '✅';
  if (s.status === 'missing') return '❌';
  return '⏳';
}

export function ProductionMapTab() {
  const [data, setData] = useState<MapResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await apiGet<MapResponse>('production_map');
      if (cancelled) return;
      setLoading(false);
      if (res.ok && res.data) {
        setData(res.data);
        setErr(null);
      } else {
        setErr(res.error ?? 'unknown error');
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <section class="mn-tab-pane mn-production-map-pane" data-testid="pane-map">
      <header class="mn-pane-header">
        <h2>Production Map</h2>
        <span class="mn-scope-chip" data-testid="map-scope-chip">
          scope: {scopeKey(activeScope.value)}
        </span>
      </header>
      {loading ? (
        <p class="mn-loading" data-testid="map-loading">Loading production map…</p>
      ) : err ? (
        <div class="mn-empty" data-testid="map-error">
          <p class="mn-warn">Could not reach /api/production/map.</p>
          <p class="mn-dim">{err}</p>
        </div>
      ) : !data?.modules?.length ? (
        <p class="mn-empty" data-testid="map-empty">No modules.</p>
      ) : (
        <div class="mn-map-table-wrap">
          {/* PHASE 4 DELIBERATE BREAK — R4 UI note temporarily removed to
              prove CI gate enforces e2e coverage. This commit pushes alone
              should turn CI red on R4 test. The next commit restores. */}
          <table class="mn-map-table" data-testid="map-table">
            <thead>
              <tr>
                <th>M#</th>
                <th>Creature</th>
                <th>Role</th>
                {SEGMENTS.map((s) => <th key={s.key}>{s.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.modules.map((m) => (
                <tr key={m.m_number} data-testid={`map-row-m${m.m_number}`}>
                  <td>M{m.m_number}</td>
                  <td>{m.creature_name}</td>
                  <td>{m.video_role}</td>
                  {SEGMENTS.map((s) => {
                    const seg = m.segments[s.key];
                    const onCellClick = async () => {
                      // S4 — click cell to load that scope in storyboard.
                      // Per LD-465 PRODUCTION_MAP_V1.
                      if (!m.event_dir) return;
                      try {
                        const res = await fetch(MUTATION_ENDPOINTS.event_load, {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ event_id: m.event_dir }),
                        });
                        if (res.ok) {
                          const data = await res.json() as {
                            event_id: string;
                            event_generation: number;
                          };
                          activeScope.value = makeScope(
                            data.event_id, null, data.event_generation,
                          );
                        }
                      } catch (e) {
                        // eslint-disable-next-line no-console
                        console.warn('[map-cell] event_load failed:', e);
                      }
                      // Dispatch tab-switch event so App can flip to 'storyboard'.
                      window.dispatchEvent(new CustomEvent(MAP_CELL_NAVIGATE_EVENT, {
                        detail: { m_number: m.m_number, segment: s.key, event_dir: m.event_dir },
                      }));
                    };
                    return (
                      <td
                        key={s.key}
                        class="mn-map-cell mn-map-cell-clickable"
                        data-testid={`map-cell-m${m.m_number}-${s.key}`}
                        data-segment-status={seg?.status ?? 'unknown'}
                        title={`${seg?.latest ?? ''}${seg?.latest ? ' · ' : ''}click to load this scope`}
                        onClick={onCellClick}
                        role="button"
                        tabIndex={0}
                      >
                        <span class="mn-map-glyph">{statusGlyph(seg)}</span>
                        {seg ? (
                          <span class="mn-map-count">{seg.count}</span>
                        ) : null}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <footer class="mn-pane-footer">
        <p class="mn-dim">
          Generated {data?.generated_at ?? '—'} · 60s server-side cache.
        </p>
      </footer>
    </section>
  );
}
