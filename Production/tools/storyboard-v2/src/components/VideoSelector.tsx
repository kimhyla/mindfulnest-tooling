// VideoSelector — top-of-app dropdown for switching the active video role
// within the loaded event. Per S5.5b spec §4 + LD-478 IMAGE_OVERRIDES_NESTED_BY_ROLE_V1.
//
// Reads /api/video/list, persists changes via /api/video/set_active. The
// activeVideoRole signal updates immediately on selection so subsequent
// pathappPatch calls auto-inject the new scope_video_role per LD-474.
//
// Per LD-474 VIDEO_ROLE_PER_REQUEST_V1:
//   - state.active_video is a DISPLAY HINT only — server handlers MUST NOT
//     read it for partition selection.
//   - VideoSelector reads it on mount (via /api/event/current → ScopeBoundary
//     hydration, or directly via /api/video/list).
//   - On change, VideoSelector writes via POST /api/video/set_active so the
//     signal persists across page reloads.
//   - Every mutating fetch from any tab carries body.scope_video_role auto-
//     injected by pathappPatch from the activeVideoRole signal.

import { useEffect, useState } from 'preact/hooks';
import { activeScope, activeVideoRole } from '../state/scope';
import { READ_ENDPOINTS, MUTATION_ENDPOINTS } from '../api/endpoints';

interface VideoListItem {
  video_role: string;
  video_label: string | null;
  has_beats: boolean;
  beat_count: number;
}

interface VideoListResponse {
  ok: boolean;
  event_id?: string;
  active_video?: string | null;
  videos?: VideoListItem[];
}

// S5.5d (v3 architecture revision, 2026-05-03): canonical roles narrow to
// {intro, resolution, standalone} per VIDEO_ROLE_PER_REQUEST_V2 (supersedes
// LD-474). phase_a + phase_b are top-level + addressed via dedicated tabs.
// 'standalone' is milestone-only and hidden in event scope by VideoSelector
// callers (see app.tsx + TargetVideoSelector design).
const CANONICAL_ROLES = ['intro', 'resolution'] as const;

export function VideoSelector() {
  const [videos, setVideos] = useState<VideoListItem[]>([]);
  const [current, setCurrent] = useState<string>(activeVideoRole.value);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [creatingNew, setCreatingNew] = useState(false);

  // On mount: fetch /api/video/list and seed dropdown.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(READ_ENDPOINTS.video_list);
        if (cancelled) return;
        if (!res.ok) {
          setErr(`HTTP ${res.status}`);
          return;
        }
        const data = (await res.json()) as VideoListResponse;
        if (data.videos) setVideos(data.videos);
        if (data.active_video && typeof data.active_video === 'string') {
          setCurrent(data.active_video);
          activeVideoRole.value = data.active_video;
        }
      } catch (e) {
        if (!cancelled) setErr(String(e));
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const onChange = async (e: Event) => {
    const target = e.target as HTMLSelectElement;
    const newRole = target.value;
    if (newRole === current) return;
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch(MUTATION_ENDPOINTS.video_set_active, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scope_event_id: activeScope.value.event_id,
          video_role: newRole,
        }),
      });
      if (!res.ok) {
        const txt = await res.text().catch(() => '');
        setErr(`HTTP ${res.status}: ${txt.slice(0, 100)}`);
        target.value = current;
        return;
      }
      const data = (await res.json()) as { ok: boolean; active_video?: string };
      if (data.ok && data.active_video) {
        setCurrent(data.active_video);
        activeVideoRole.value = data.active_video;
        // Update URL with ?video=<role> for shareable links + cold-boot persistence.
        try {
          const url = new URL(window.location.href);
          url.searchParams.set('video', data.active_video);
          window.history.replaceState({}, '', url.toString());
        } catch {
          // window.history not available — no-op.
        }
      }
    } catch (e) {
      setErr(String(e));
      target.value = current;
    } finally {
      setLoading(false);
    }
  };

  const onAddNew = async () => {
    // Find first canonical role NOT yet present in videos (server creates an
    // empty partition). Skip 'standalone' for the typical case.
    const existing = new Set(videos.map((v) => v.video_role));
    const candidate = CANONICAL_ROLES.find((r) => !existing.has(r));
    if (!candidate) {
      setErr('All canonical video roles already exist for this event.');
      return;
    }
    setCreatingNew(true);
    setErr(null);
    try {
      const res = await fetch(MUTATION_ENDPOINTS.video_create, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scope_event_id: activeScope.value.event_id,
          video_role: candidate,
          video_label: null,
        }),
      });
      if (!res.ok) {
        const txt = await res.text().catch(() => '');
        setErr(`HTTP ${res.status}: ${txt.slice(0, 100)}`);
        return;
      }
      // Refresh the list.
      const listRes = await fetch(READ_ENDPOINTS.video_list);
      if (listRes.ok) {
        const data = (await listRes.json()) as VideoListResponse;
        if (data.videos) setVideos(data.videos);
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setCreatingNew(false);
    }
  };

  return (
    <div class="mn-video-selector" data-testid="video-selector">
      <label class="mn-video-selector-label" for="mn-video-select">Video:</label>
      <select
        id="mn-video-select"
        data-testid="video-select"
        class="mn-video-select"
        value={current}
        onChange={onChange}
        disabled={loading || videos.length === 0}
      >
        {videos.length === 0 ? (
          <option value="">— no partitions —</option>
        ) : (
          videos.map((v) => (
            <option key={v.video_role} value={v.video_role}>
              {v.video_role}{v.video_label ? ` — ${v.video_label}` : ''}{' '}
              {v.has_beats ? `(${v.beat_count})` : ''}
            </option>
          ))
        )}
      </select>
      <button
        type="button"
        class="mn-btn mn-btn-small"
        data-testid="video-add-new"
        onClick={onAddNew}
        disabled={creatingNew || videos.length >= CANONICAL_ROLES.length}
        title="Create the next canonical video partition (intro→resolution)"
      >
        {creatingNew ? '…' : '+ New video'}
      </button>
      {loading ? <span class="mn-dim">loading…</span> : null}
      {err ? <span class="mn-warn" data-testid="video-selector-err">{err}</span> : null}
    </div>
  );
}
