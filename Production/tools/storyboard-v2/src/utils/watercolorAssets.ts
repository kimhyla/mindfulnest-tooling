/**
 * Client mirror of Production/lib/watercolor_assets.py — single URL contract.
 * Never hardcode a fixed localhost port; always use SERVER_BASE + encoded paths.
 */
import { SERVER_BASE } from '../api/endpoints';

export interface WatercolorListItem {
  key: string;
  filename?: string;
  ext?: string;
  kind?: 'static' | 'animation' | string;
  thumb_url?: string;
  animation_url?: string | null;
  mtime?: number;
  size_bytes?: number;
  tier?: string;
  tags?: string[];
  abs_path?: string;
}

/** Static PNG/WebP preview (overlay + library thumbs). */
export function watercolorFileUrl(key: string): string {
  return `${SERVER_BASE}/api/phase/watercolor_file?key=${encodeURIComponent(key)}`;
}

/** Animated MP4/MOV overlay source. */
export function watercolorServeUrl(key: string): string {
  return `${SERVER_BASE}/api/phase_b/watercolor/${encodeURIComponent(key)}`;
}

/** Resolve list item or cue key to preview URL for overlay playback. */
export function watercolorOverlaySrc(
  key: string,
  item?: WatercolorListItem | null,
  opts?: { animation?: boolean },
): string {
  if (opts?.animation) {
    if (item?.animation_url) {
      return absolutizeWatercolorUrl(item.animation_url);
    }
    return watercolorServeUrl(key);
  }
  if (item?.thumb_url) {
    return absolutizeWatercolorUrl(item.thumb_url);
  }
  return watercolorFileUrl(key);
}

export function absolutizeWatercolorUrl(url: string): string {
  if (url.startsWith('http://') || url.startsWith('https://')) {
    try {
      const u = new URL(url);
      return `${SERVER_BASE}${u.pathname}${u.search}`;
    } catch {
      return url;
    }
  }
  if (url.startsWith('/')) {
    return `${SERVER_BASE}${url}`;
  }
  return url;
}
