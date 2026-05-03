// ProductionMapTab — 5th tab in v59. Per-module per-segment status matrix.
// Per LD-465 PRODUCTION_MAP_V1.
//
// Reads /api/production/map (60s TTL cache server-side). Renders a matrix:
//   rows = modules (m_number, creature_name, video_role)
//   cols = phase_a, phase_b, intro_or_resolution, final_concat
//   cells = ✅/⏳/❌ + count + latest filename

import { useEffect, useState } from 'preact/hooks';
import { apiGet } from '../api/client';
import { activeScope, scopeKey } from '../state/scope';

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
                    return (
                      <td
                        key={s.key}
                        class="mn-map-cell"
                        data-testid={`map-cell-m${m.m_number}-${s.key}`}
                        data-segment-status={seg?.status ?? 'unknown'}
                        title={seg?.latest ?? ''}
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
