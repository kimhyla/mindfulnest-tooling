// BUILD_SHA_DRIFT_V1 — zero-dep HTML parse helpers for Node unit tests.

export function parseBuildShaFromHtml(html: string): string | null {
  const m = html.match(/<meta\s+name=["']build-sha["']\s+content=["']([^"']+)["']/i);
  return m?.[1]?.trim() ?? null;
}

export function readBuildShaMetaContent(doc: { querySelector: (sel: string) => { getAttribute: (n: string) => string | null } | null }): string {
  return doc.querySelector('meta[name="build-sha"]')?.getAttribute('content')?.trim() ?? '';
}

export function buildShaDriftDetected(bundled: string, live: string): boolean {
  if (!bundled || !live || bundled === '?' || live === '?') return false;
  return bundled !== live;
}
