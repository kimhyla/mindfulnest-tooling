// ProductionMapTab — 5th tab in v59. Per-module per-segment status matrix.
// Per LD-465 PRODUCTION_MAP_V1.
//
// Reads /api/production/map (60s TTL cache server-side). Renders a matrix:
//   rows = modules (m_number, creature_name, video_role)
//   cols = phase_a, phase_b, intro_or_resolution, final_concat
//   cells = ✅/⏳/❌ + count + latest filename

import { loadEvent, noteClientPinnedEvent } from '../api/client';
import { activeScope, scopeKey, makeScope } from '../state/scope';
import {
  mapData,
  mapError,
  mapLoading,
  mapSessionHasCache,
} from '../state/mapSessionStore';

// Custom event the App listens for. ProductionMapTab dispatches this on
// cell click; App switches activeTab to 'storyboard'.
export const MAP_CELL_NAVIGATE_EVENT = 'mn:map-cell-navigate';

interface SegmentStatus {
  status: 'ready' | 'missing' | string;
  count: number;
  latest?: string;
}

// C-12 ride-along: per-role state derived server-side from partition
// presence + display_order + completed mp4 + final concat. Picker-spec R3
// preserved (no prod_modules schema change). 5-state glyph mapping in
// statusGlyphForRole() below mirrors post-redeploy v2 §3.3 Part 2.
type RoleStateValue = 'absent' | 'empty' | 'in_progress' | 'complete' | 'final';
interface RoleStatus {
  state: RoleStateValue;
  completed_mp4?: string;
}

interface MapRow {
  m_number: number;
  creature_name: string;
  video_role: string;
  event_dir: string;
  segments: Record<string, SegmentStatus>;
  videos_by_role?: Record<string, RoleStatus>;
}

interface MapMilestoneRow {
  milestone_id: string;
  milestone_label?: string | null;
  skeleton_ref?: { arc_number?: number; event_id?: string; phase?: string };
  path?: string;
  scope_type?: string;
  videos_by_role?: Record<string, RoleStatus & { bg_beat_count?: number }>;
}

interface MapResponse {
  ok: boolean;
  modules?: MapRow[];
  milestones?: MapMilestoneRow[];
  generated_at?: string;
}

// 5-column layout per handoff §4 C-12: Intro, Phase A, Phase B, Resolution,
// Final concat. The single legacy "Storyboard" column is replaced by per-role
// columns (intro + resolution); Phase A / Phase B / Final concat unchanged.
// Each segment has a `kind`: 'role' uses videos_by_role + 5-state glyph;
// 'segment' uses the legacy ready/missing artifact glob status.
type SegmentDef =
  | { key: 'intro' | 'resolution'; kind: 'role'; label: string }
  | { key: 'phase_a' | 'phase_b' | 'final_concat'; kind: 'segment'; label: string };

const SEGMENTS: readonly SegmentDef[] = [
  { key: 'intro', kind: 'role', label: 'Intro' },
  { key: 'phase_a', kind: 'segment', label: 'Phase A' },
  { key: 'phase_b', kind: 'segment', label: 'Phase B' },
  { key: 'resolution', kind: 'role', label: 'Resolution' },
  { key: 'final_concat', kind: 'segment', label: 'Final' },
] as const;

function statusGlyph(s: SegmentStatus | undefined): string {
  if (!s) return '—';
  if (s.status === 'ready') return '✅';
  if (s.status === 'missing') return '❌';
  return '⏳';
}

// 5-state glyph for per-role columns. Mapping per post-redeploy v2 §3.3
// Part 2 + handoff §4 C-12:
//   absent      → '—'   em dash, n/a (partition not in state.videos)
//   empty       → '○'   white circle (partition present, display_order=[])
//   in_progress → '◐'   half circle (display_order populated, no mp4)
//   complete    → '●'   black circle (display_order + per-role mp4)
//   final       → '★'   star (complete + module-level final concat)
function statusGlyphForRole(r: RoleStatus | undefined): string {
  if (!r) return '—';
  switch (r.state) {
    case 'absent':      return '—';
    case 'empty':       return '○';
    case 'in_progress': return '◐';
    case 'complete':    return '●';
    case 'final':       return '★';
    default:            return '?';
  }
}

export function ProductionMapTab() {
  const data = mapData.value as MapResponse | null;
  const err = mapError.value;
  const loading = mapLoading.value && !mapSessionHasCache();

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
      ) : !data?.modules?.length && !data?.milestones?.length ? (
        <p class="mn-empty" data-testid="map-empty">No modules.</p>
      ) : (
        <div class="mn-map-table-wrap">
          {/* R4 fix: UI note explaining V1 scope policy for M7-M54 placeholders.
              See PRODUCTION_MAP_TBD_HONEST_V1 (S5.5c+e proper-fix §3) — TBD
              entries are V1 scope by design, not parser bugs.
              PHASE 4 RED PROOF: removed in commit 0e265ca; CI run 25301870632
              went red on R4 test (12/13 passing); restored here per Phase 4.4. */}
          <p
            class="mn-map-tbd-note mn-dim"
            data-testid="production-map-tbd-note"
          >
            <strong>Note:</strong> M7-M54 are V1 scope placeholders — author
            each by creating an Event. Once authored, run
            <code> populate_prod_modules_from_gameplay_scope.py</code> to
            update <code>creature_name</code> from the doc.
          </p>
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
              {data.modules?.map((m) => (
                <tr key={m.m_number} data-testid={`map-row-m${m.m_number}`}>
                  <td>M{m.m_number}</td>
                  <td>{m.creature_name}</td>
                  <td>{m.video_role}</td>
                  {SEGMENTS.map((s) => {
                    // Two cell flavors:
                    //   role    — videos_by_role[<role>].state → 5-state glyph
                    //   segment — segments[<key>].status → 3-state glyph (ready/missing/⏳)
                    const isRole = s.kind === 'role';
                    const role = isRole ? m.videos_by_role?.[s.key] : undefined;
                    const seg = !isRole ? m.segments[s.key] : undefined;
                    const cellGlyph = isRole ? statusGlyphForRole(role) : statusGlyph(seg);
                    const cellState = isRole ? (role?.state ?? 'absent') : (seg?.status ?? 'unknown');
                    const titleHint = isRole
                      ? `${s.label}: ${role?.state ?? 'absent'}${role?.completed_mp4 ? ' · ' + role.completed_mp4 : ''} · click to load this scope`
                      : `${seg?.latest ?? ''}${seg?.latest ? ' · ' : ''}click to load this scope`;
                    const onCellClick = async () => {
                      // S4 — click cell to load that scope in storyboard.
                      // Per LD-465 PRODUCTION_MAP_V1.
                      if (!m.event_dir) return;
                      // Wave 3 (blocker #53 F-S2-005): loadEvent client helper.
                      try {
                        const result = await loadEvent(m.event_dir);
                        if (result.ok && result.data) {
                          const data = result.data;
                          noteClientPinnedEvent(data.event_id);
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
                        class={isRole ? 'mn-map-cell mn-map-cell-role mn-map-cell-clickable' : 'mn-map-cell mn-map-cell-clickable'}
                        data-testid={`map-cell-m${m.m_number}-${s.key}`}
                        data-segment-status={cellState}
                        data-cell-kind={s.kind}
                        title={titleHint}
                        onClick={onCellClick}
                        role="button"
                        tabIndex={0}
                      >
                        <span class="mn-map-glyph">{cellGlyph}</span>
                        {!isRole && seg ? (
                          <span class="mn-map-count">{seg.count}</span>
                        ) : null}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          {data.milestones && data.milestones.length > 0 ? (
            <>
              <h3 class="mn-map-milestones-heading" data-testid="map-milestones-heading">Milestones</h3>
              <table class="mn-map-table mn-map-milestones-table" data-testid="map-milestones-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Label</th>
                    <th>Skeleton</th>
                    <th>Standalone</th>
                    <th>BG beats</th>
                  </tr>
                </thead>
                <tbody>
                  {data.milestones.map((ms) => {
                    const skel = ms.skeleton_ref ?? {};
                    const role = ms.videos_by_role?.['standalone'];
                    return (
                      <tr key={ms.milestone_id} data-testid={`map-milestone-row-${ms.milestone_id}`}>
                        <td>{ms.milestone_id}</td>
                        <td>{ms.milestone_label ?? '—'}</td>
                        <td>
                          arc {skel.arc_number ?? '?'} · event {skel.event_id ?? '?'} · {skel.phase ?? '?'}
                        </td>
                        <td data-testid={`map-milestone-${ms.milestone_id}-standalone`}>
                          <span class="mn-map-glyph">{statusGlyphForRole(role)}</span>
                        </td>
                        <td>{role?.bg_beat_count ?? 0}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          ) : null}
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
