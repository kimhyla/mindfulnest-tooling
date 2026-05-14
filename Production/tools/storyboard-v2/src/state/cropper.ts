// Cropper state — shared signal + openCropper() helper for opening CropperModal
// from any surface (BgTab, LibraryPanel, future surfaces).
//
// Lives here (not in app.tsx) to avoid circular imports: app.tsx renders BgTab
// and LibraryPanel, which both need to import openCropper. Having them import
// from app.tsx would create a cycle. This follows the activeScope pattern in
// ./scope.ts.
import { signal } from '@preact/signals';
import type { CropperModalState } from '../components/CropperModal';
import { initialCropperModalState } from '../components/CropperModal';

export const cropperState = signal<CropperModalState>({ ...initialCropperModalState });

export function openCropper(opts: {
  source: string;
  sourceLabel?: string;
  /** beat_id for server-side naming; null for library-origin crops. */
  targetBeatId: string | null;
}): void {
  cropperState.value = {
    open: true,
    source: opts.source,
    sourceLabel: opts.sourceLabel ?? null,
    targetBeatId: opts.targetBeatId,
  };
}
