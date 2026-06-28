/** Beat Gen — per-beat readiness for Send to Stitcher (mirrors backend gate). */

import {
  beatKlingStitchExportReady,
  o3JobBlocksStitchExport,
  stillBeatNeedsStitchApprove,
  type KlingStitchReadinessBeat,
} from './klingStitchReadiness';

export type BgBeatStitchFields = KlingStitchReadinessBeat & { beat_id: string };

export function shortBeatLabel(beatId: string): string {
  const m = beatId.match(/beat_(\d+)/);
  return m ? `beat ${m[1]}` : beatId;
}

/** True when this beat can be included in segment stitch export. */
export function beatStitchExportReady(b: BgBeatStitchFields): boolean {
  return beatKlingStitchExportReady(b);
}

/** Short UI label for what's blocking this beat, or null when ready. */
export function beatStitchExportBlockLabel(b: BgBeatStitchFields): string | null {
  if (beatStitchExportReady(b)) return null;
  if (b.magic_still_path && b.magic_still_path_exists === false) {
    return 'Magic still file missing';
  }
  if (stillBeatNeedsStitchApprove(b)) {
    return 'Approve still clip';
  }
  if (o3JobBlocksStitchExport(b)) {
    return 'Wait for Kling job to finish';
  }
  return 'Submit Kling or add magic on still';
}

export function allBeatsStitchExportReady(beats: BgBeatStitchFields[]): boolean {
  return beats.length > 0 && beats.every(beatStitchExportReady);
}

/** Tooltip for disabled Send to Stitcher — lists blocking beats by name. */
export function stitchExportBlockTooltip(
  beats: BgBeatStitchFields[],
  slotKey: string,
): string {
  if (allBeatsStitchExportReady(beats)) {
    return `Send all beats to Stitcher (${slotKey} slot) — Kling clips and magic-on-still beats`;
  }
  const blockers = beats
    .map((b) => ({ short: shortBeatLabel(b.beat_id), label: beatStitchExportBlockLabel(b) }))
    .filter((x): x is { short: string; label: string } => x.label != null);
  if (blockers.length === 0) {
    return 'Every beat needs a Kling delivery clip or a magic-on-still composite before sending to Stitcher';
  }
  const list = blockers.map((x) => `${x.short}: ${x.label}`).join(' · ');
  const stillBlockers = blockers.filter((x) => x.label === 'Approve still clip');
  const hints: string[] = [];
  if (stillBlockers.length) {
    hints.push(
      `Still-insert beats (${stillBlockers.map((x) => x.short).join(', ')}): open the beat, `
      + 'play the still clip in the option tile, then click **Approve still for stitch** under the video',
    );
  }
  if (blockers.some((x) => x.label === 'Wait for Kling job to finish')) {
    hints.push('Kling beats with an active job: wait for generation to finish before sending');
  }
  if (blockers.some((x) => x.label === 'Submit Kling or add magic on still')) {
    hints.push('Missing clips: generate O3 voice or build a still video first');
  }
  const hintText = hints.length ? ` ${hints.join('. ')}.` : '';
  return `Can't send yet — ${list}.${hintText}`;
}
