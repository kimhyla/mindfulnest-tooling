/** Beat Gen — per-beat readiness for Send to Stitcher (mirrors backend gate). */

export interface BgBeatStitchFields {
  beat_id: string;
  magic_still_path?: string | null;
  magic_still_path_exists?: boolean;
  magic_video_path?: string | null;
  magic_video_path_exists?: boolean;
  kling_o3_status?: string | null;
  kling_o3_video_path?: string | null;
}

export function shortBeatLabel(beatId: string): string {
  const m = beatId.match(/beat_(\d+)/);
  return m ? `beat ${m[1]}` : beatId;
}

/** True when this beat can be included in segment stitch export. */
export function beatStitchExportReady(b: BgBeatStitchFields): boolean {
  if (b.magic_still_path && b.magic_still_path_exists !== false) return true;
  return b.kling_o3_status === 'approved' && Boolean(b.kling_o3_video_path);
}

/** Short UI label for what's blocking this beat, or null when ready. */
export function beatStitchExportBlockLabel(b: BgBeatStitchFields): string | null {
  if (beatStitchExportReady(b)) return null;
  if (b.magic_still_path && b.magic_still_path_exists === false) {
    return 'Magic still file missing';
  }
  if (b.kling_o3_video_path && b.kling_o3_status !== 'approved') {
    return 'Approve Kling clip';
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
    return 'Every beat needs an approved Kling clip or a magic-on-still composite before sending to Stitcher';
  }
  const list = blockers.map((x) => `${x.short}: ${x.label}`).join(' · ');
  return (
    `Can't send yet — ${list}. `
    + 'Magic-on-still beats count as ready once the composite renders (no Approve button). '
    + 'Kling beats need you to click Approve after reviewing the clip.'
  );
}
