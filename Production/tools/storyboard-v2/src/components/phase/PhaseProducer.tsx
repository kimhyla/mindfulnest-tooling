// PhaseProducer — shared base component for Phase A + Phase B producers.
// Per LD-462 PHASE_A_PRODUCER_V1 + LD-463 PHASE_B_PRODUCER_V1.
//
// S3 SCOPE: skeleton mounting that exercises the new server endpoints
// (/api/phase/watercolor_list, /api/phase/base_clips_list, /api/phase/
// suggest_script). Full UX features (audio player + WaveSurfer timeline +
// drag-drop + Send for Lipsync + lipsync video player + Export to Stitcher)
// land in Session 4 polish — flagged inline.

import { useEffect, useState } from 'preact/hooks';
import { apiGet, pathappPatch } from '../../api/client';
import { activeScope } from '../../state/scope';

interface WatercolorItem {
  key: string;
  filename: string;
  ext: string;
  kind: 'static' | 'animation' | string;
  thumb_url: string;
  mtime: number;
  size_bytes: number;
}
interface WatercolorListResponse {
  ok: boolean;
  items?: WatercolorItem[];
  count?: number;
}

interface BaseClipItem {
  id: string;
  filename: string;
  ext: string;
  character: string | null;
  duration_s: number | null;
}
interface BaseClipsResponse {
  ok: boolean;
  items?: BaseClipItem[];
  count?: number;
}

export interface PhaseProducerProps {
  phase: 'a' | 'b';
}

export function PhaseProducer({ phase }: PhaseProducerProps) {
  const [collapsed, setCollapsed] = useState(true);
  const [watercolors, setWatercolors] = useState<WatercolorItem[]>([]);
  const [baseClips, setBaseClips] = useState<BaseClipItem[]>([]);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestion, setSuggestion] = useState<string | null>(null);

  useEffect(() => {
    if (collapsed) return;
    let cancelled = false;
    (async () => {
      const [wc, bc] = await Promise.all([
        apiGet<WatercolorListResponse>('phase_watercolor_list'),
        apiGet<BaseClipsResponse>('phase_base_clips_list'),
      ]);
      if (cancelled) return;
      if (wc.ok && wc.data?.items) setWatercolors(wc.data.items);
      if (bc.ok && bc.data?.items) setBaseClips(bc.data.items);
    })();
    return () => { cancelled = true; };
  }, [collapsed]);

  const phaseLabel = phase === 'a' ? 'Phase A (Chipper)' : 'Phase B (Cedric)';

  const onSuggest = async () => {
    setSuggesting(true);
    setSuggestion(null);
    const res = await pathappPatch(activeScope.value, 'phase_suggest_script', {
      phase,
    });
    setSuggesting(false);
    if (res.ok && res.data) {
      const data = res.data as { script?: string };
      setSuggestion(data.script ?? '(no script returned)');
    } else {
      setSuggestion(`error: HTTP ${res.status} ${res.error ?? ''}`);
    }
  };

  const onAnimateThis = (key: string) => {
    // Per LD-464 — open path_picker.html in NEW tab (not embedded).
    const url = new URL('http://localhost:5111/magic');
    url.searchParams.set('source', key);
    url.searchParams.set('return_endpoint', '/api/watercolor/animate');
    window.open(url.toString(), '_blank');
  };

  return (
    <details
      class={`mn-phase-producer mn-phase-${phase}`}
      data-testid={`phase-producer-${phase}`}
      open={!collapsed}
      onToggle={(e: Event) => {
        const t = e.target as HTMLDetailsElement;
        setCollapsed(!t.open);
      }}
    >
      <summary class="mn-phase-summary">
        {phaseLabel}
        <span class="mn-dim mn-phase-stub-tag">(S3 scaffold — full producer UX in S4)</span>
      </summary>
      <div class="mn-phase-body">
        <div class="mn-phase-row">
          <button
            type="button"
            class="mn-btn"
            data-testid={`phase-${phase}-suggest-btn`}
            onClick={onSuggest}
            disabled={suggesting}
          >
            {suggesting ? 'Suggesting…' : 'Suggest Script'}
          </button>
          <span class="mn-dim">
            {phase === 'a' ? 'reads Phase B + module context' : 'reads arc skeleton + therapeutic'}
          </span>
        </div>
        {suggestion ? (
          <pre class="mn-phase-suggestion" data-testid={`phase-${phase}-suggestion`}>{suggestion}</pre>
        ) : null}

        <div class="mn-phase-row">
          <strong>Base clips ({baseClips.length}):</strong>
          {baseClips.map((bc) => (
            <span class="mn-phase-base-clip" key={bc.id}>
              {bc.character ?? '?'}: {bc.id} ({bc.duration_s ?? '?'}s)
            </span>
          ))}
        </div>

        <div class="mn-phase-watercolor-list" data-testid={`phase-${phase}-watercolors`}>
          <strong>Watercolors ({watercolors.length}):</strong>
          <div class="mn-phase-watercolor-grid">
            {watercolors.map((wc) => (
              <div class="mn-phase-watercolor-tile" key={wc.key}>
                <img
                  src={wc.thumb_url}
                  alt={wc.filename}
                  class="mn-phase-watercolor-thumb"
                  loading="lazy"
                />
                <span class="mn-phase-watercolor-name">{wc.key}</span>
                <button
                  type="button"
                  class="mn-btn mn-btn-small"
                  data-testid={`phase-${phase}-animate-${wc.key}`}
                  onClick={() => onAnimateThis(wc.key)}
                >
                  Animate this
                </button>
              </div>
            ))}
          </div>
        </div>

        <p class="mn-readonly-banner">
          S3 scaffold: dropdown sources are live ({watercolors.length} watercolors,{' '}
          {baseClips.length} base clips). Full producer UX (audio player +
          timeline + Send for Lipsync + Export to Stitcher) lands in S4.
        </p>
      </div>
    </details>
  );
}
