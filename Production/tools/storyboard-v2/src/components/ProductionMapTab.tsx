// ProductionMapTab — 5th tab in v59. Per-module per-segment status matrix.
// Per LD-465 PRODUCTION_MAP_V1.
//
// Reads /api/production/map (60s TTL cache server-side). Renders play-order
// timeline: modules, milestones, and narratives interleaved per arc skeleton.

import { loadEvent, noteClientPinnedEvent } from '../api/client';
import { activeScope, scopeKey, makeScope } from '../state/scope';
import {
  mapData,
  mapError,
  mapLoading,
  mapSessionHasCache,
} from '../state/mapSessionStore';

export const MAP_CELL_NAVIGATE_EVENT = 'mn:map-cell-navigate';

interface SegmentStatus {
  status: 'ready' | 'missing' | string;
  count: number;
  latest?: string;
}

type RoleStateValue = 'absent' | 'empty' | 'in_progress' | 'complete' | 'final';
interface RoleStatus {
  state: RoleStateValue;
  completed_mp4?: string;
  bg_beat_count?: number;
}

interface MapModuleRow {
  kind: 'module';
  arc_number: number;
  play_order: number;
  m_number: number;
  creature_name: string;
  video_role: string;
  label?: string;
  event_dir?: string | null;
  after_event?: string | null;
  before_event?: string | null;
  segments: Record<string, SegmentStatus>;
  videos_by_role?: Record<string, RoleStatus>;
}

interface MapMilestoneRow {
  kind: 'milestone';
  arc_number: number;
  play_order: number;
  label?: string | null;
  suggested_milestone_id?: string | null;
  milestone_id?: string;
  created?: boolean;
  after_event?: string | null;
  before_event?: string | null;
  videos_by_role?: Record<string, RoleStatus>;
}

interface MapMilestoneExtra {
  milestone_id?: string;
  milestone_label?: string | null;
  dev_fixture?: boolean;
}

interface MapNarrativeRow {
  kind: 'narrative';
  arc_number: number;
  play_order: number;
  label?: string | null;
  after_event?: string | null;
  before_event?: string | null;
}

type TimelineRow = MapModuleRow | MapMilestoneRow | MapNarrativeRow;

interface MapResponse {
  ok: boolean;
  timeline?: TimelineRow[];
  modules?: MapModuleRow[];
  milestones?: MapMilestoneRow[];
  milestone_extras?: MapMilestoneExtra[];
  generated_at?: string;
}

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

function kindLabel(kind: string): string {
  if (kind === 'module') return 'Module';
  if (kind === 'milestone') return 'Milestone';
  if (kind === 'narrative') return 'Narrative';
  return kind;
}

function placementHint(row: TimelineRow): string {
  const after = row.after_event;
  const before = row.before_event;
  if (after && before) return `${after} → ${before}`;
  if (after) return `after ${after}`;
  if (before) return `before ${before}`;
  return '—';
}

function rowKey(row: TimelineRow): string {
  if (row.kind === 'module') return `arc${row.arc_number}-p${row.play_order}-m${row.m_number}`;
  if (row.kind === 'milestone') {
    const ms = row as MapMilestoneRow;
    return `arc${row.arc_number}-p${row.play_order}-${ms.suggested_milestone_id ?? ms.milestone_id ?? 'ms'}`;
  }
  return `arc${row.arc_number}-p${row.play_order}-nar`;
}

function rowTestId(row: TimelineRow): string {
  if (row.kind === 'module') return `map-row-m${row.m_number}`;
  if (row.kind === 'milestone') {
    const ms = row as MapMilestoneRow;
    return `map-milestone-row-${ms.suggested_milestone_id ?? ms.milestone_id ?? row.play_order}`;
  }
  return `map-narrative-row-${row.arc_number}-${row.play_order}`;
}

export function ProductionMapTab() {
  const data = mapData.value as MapResponse | null;
  const err = mapError.value;
  const loading = mapLoading.value && !mapSessionHasCache();
  const timeline = data?.timeline ?? [];

  // Group timeline rows by arc for section headers.
  const arcGroups: { arc: number; rows: TimelineRow[] }[] = [];
  for (const row of timeline) {
    const last = arcGroups[arcGroups.length - 1];
    if (last && last.arc === row.arc_number) {
      last.rows.push(row);
    } else {
      arcGroups.push({ arc: row.arc_number, rows: [row] });
    }
  }

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
      ) : !timeline.length ? (
        <p class="mn-empty" data-testid="map-empty">No production slots.</p>
      ) : (
        <div class="mn-map-table-wrap">
          <p
            class="mn-map-tbd-note mn-dim"
            data-testid="production-map-tbd-note"
          >
            <strong>Play order</strong> from Arc Skeletons — modules, milestones, and
            narrative beats interleaved as they ship. Use <strong>+ New Event…</strong> or{' '}
            <strong>+ New Milestone…</strong> for the next expected slot.
          </p>
          {arcGroups.map(({ arc, rows }) => (
            <div key={`arc-${arc}`} class="mn-map-arc-section" data-testid={`map-arc-${arc}`}>
              <h3 class="mn-map-arc-heading">Arc {arc}</h3>
              <table class="mn-map-table" data-testid="map-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Kind</th>
                    <th>Label</th>
                    <th>ID</th>
                    <th>Placement</th>
                    {SEGMENTS.map((s) => <th key={s.key}>{s.label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const isModule = row.kind === 'module';
                    const isMilestone = row.kind === 'milestone';
                    const m = isModule ? (row as MapModuleRow) : null;
                    const ms = isMilestone ? (row as MapMilestoneRow) : null;
                    const idCell = isModule
                      ? `M${m!.m_number}${m!.event_dir ? ` · ${m!.event_dir}` : ''}`
                      : isMilestone
                        ? (ms!.suggested_milestone_id ?? ms!.milestone_id ?? '—')
                        : '—';

                    return (
                      <tr
                        key={rowKey(row)}
                        data-testid={rowTestId(row)}
                        class={
                          isMilestone ? 'mn-map-row-milestone'
                          : row.kind === 'narrative' ? 'mn-map-row-narrative'
                          : ''
                        }
                      >
                        <td>{row.play_order}</td>
                        <td>{kindLabel(row.kind)}</td>
                        <td>{row.label ?? (isModule ? m!.creature_name : '—')}</td>
                        <td>{idCell}</td>
                        <td class="mn-dim mn-map-placement" title="Between which Event folders">
                          {placementHint(row)}
                        </td>
                        {SEGMENTS.map((s) => {
                          if (!isModule) {
                            if (isMilestone && s.key === 'intro') {
                              const role = ms!.videos_by_role?.['standalone'];
                              return (
                                <td
                                  key={s.key}
                                  class="mn-map-cell mn-map-cell-role"
                                  data-testid={`${rowTestId(row)}-standalone`}
                                >
                                  <span class="mn-map-glyph">{statusGlyphForRole(role)}</span>
                                  {ms!.created ? null : (
                                    <span class="mn-map-count mn-dim" title="Not created on disk">new</span>
                                  )}
                                </td>
                              );
                            }
                            return <td key={s.key} class="mn-map-cell mn-dim">—</td>;
                          }

                          const isRole = s.kind === 'role';
                          const role = isRole ? m!.videos_by_role?.[s.key] : undefined;
                          const seg = !isRole ? m!.segments?.[s.key] : undefined;
                          const cellGlyph = isRole ? statusGlyphForRole(role) : statusGlyph(seg);
                          const cellState = isRole ? (role?.state ?? 'absent') : (seg?.status ?? 'unknown');
                          const titleHint = isRole
                            ? `${s.label}: ${role?.state ?? 'absent'}${role?.completed_mp4 ? ' · ' + role.completed_mp4 : ''} · click to load`
                            : `${seg?.latest ?? ''}${seg?.latest ? ' · ' : ''}click to load`;
                          const onCellClick = async () => {
                            if (!m!.event_dir) return;
                            try {
                              const result = await loadEvent(m!.event_dir!);
                              if (result.ok && result.data) {
                                const d = result.data;
                                noteClientPinnedEvent(d.event_id);
                                activeScope.value = makeScope(
                                  d.event_id, null, d.event_generation,
                                );
                              }
                            } catch (e) {
                              // eslint-disable-next-line no-console
                              console.warn('[map-cell] event_load failed:', e);
                            }
                            window.dispatchEvent(new CustomEvent(MAP_CELL_NAVIGATE_EVENT, {
                              detail: {
                                m_number: m!.m_number,
                                segment: s.key,
                                event_dir: m!.event_dir,
                              },
                            }));
                          };
                          return (
                            <td
                              key={s.key}
                              class={isRole ? 'mn-map-cell mn-map-cell-role mn-map-cell-clickable' : 'mn-map-cell mn-map-cell-clickable'}
                              data-testid={`map-cell-m${m!.m_number}-${s.key}`}
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
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))}
          {data?.milestone_extras && data.milestone_extras.length > 0 ? (
            <details class="mn-map-milestone-extras" data-testid="map-milestone-extras">
              <summary>
                Other on-disk milestone folders ({data.milestone_extras.length})
                <span class="mn-dim"> — legacy / dev fixtures, not in the plan</span>
              </summary>
              <table class="mn-map-table mn-map-milestones-table">
                <thead>
                  <tr>
                    <th>Folder</th>
                    <th>Label</th>
                    <th>Type</th>
                  </tr>
                </thead>
                <tbody>
                  {data.milestone_extras.map((ms) => (
                    <tr key={ms.milestone_id} data-testid={`map-milestone-extra-${ms.milestone_id}`}>
                      <td>{ms.milestone_id}</td>
                      <td>{ms.milestone_label ?? '—'}</td>
                      <td>{ms.dev_fixture ? 'dev fixture' : 'unplanned'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
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
