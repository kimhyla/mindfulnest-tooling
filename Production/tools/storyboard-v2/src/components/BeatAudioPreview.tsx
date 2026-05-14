// BeatAudioPreview — renders a fresh-stream <audio> element for a beat.
// Per LD-184 PREVIEW_BEAT_AUDIO_FRESH_STREAM (S5.5e).
//
// The server endpoint /api/beat/audio/<beat_id> always streams from disk,
// never caches; modifying the dialogue text + clicking Preview MUST return
// the NEW TTS audio. We force the browser to re-fetch by appending a
// monotonic query string (no body — GET requests don't accept JSON), and we
// recreate the <audio> element on each "play fresh" click via a key remount.

import { useState } from 'preact/hooks';
import { activeScope } from '../state/scope';
import { READ_ENDPOINTS } from '../api/endpoints';

export interface BeatAudioPreviewProps {
  beatId: string;
  /** Optional cache-bust seed — Storyboard passes beat.text_last_updated_at
   *  here so any text save re-bumps the URL automatically. */
  cacheBust?: string;
  /** Optional testid suffix — defaults to beat_id. */
  testId?: string;
  /** Optional disabled flag — true if no audio file exists yet. */
  disabled?: boolean;
}

export function BeatAudioPreview({ beatId, cacheBust, testId, disabled }: BeatAudioPreviewProps) {
  const [reloadTick, setReloadTick] = useState(0);

  // Build absolute URL per Rule 32 (no relative paths).
  // Substitute {beat_id} in the template, then add cache-bust + scope params.
  const tpl = READ_ENDPOINTS.beat_audio;
  const baseUrl = tpl.replace('{beat_id}', encodeURIComponent(beatId));
  const url = new URL(baseUrl);
  url.searchParams.set('event_id', activeScope.value.event_id);
  if (cacheBust) url.searchParams.set('cache_bust', cacheBust);
  // The reloadTick forces a key change → DOM remount → browser re-fetches.
  url.searchParams.set('_t', String(reloadTick));

  return (
    <span
      class="mn-beat-audio-preview"
      data-testid={`beat-audio-preview-${testId ?? beatId}`}
    >
      {/* key forces remount on tick change so the audio source re-fetches. */}
      <audio
        key={`audio-${beatId}-${reloadTick}`}
        src={url.toString()}
        controls
        preload="metadata"
        data-testid={`beat-audio-element-${testId ?? beatId}`}
      />
      <button
        type="button"
        class="mn-btn mn-btn-small"
        data-testid={`beat-audio-reload-${testId ?? beatId}`}
        onClick={() => setReloadTick((n) => n + 1)}
        disabled={disabled === true}
        title="Re-fetch fresh audio (LD-184)"
      >
        ⟳
      </button>
    </span>
  );
}
