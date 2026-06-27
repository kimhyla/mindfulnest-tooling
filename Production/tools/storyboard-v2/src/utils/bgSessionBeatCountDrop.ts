/** Beat count drop warning — operator-visible signal when session reload shrinks list. */

export function shouldWarnBeatCountDrop(prevCount: number, nextCount: number): boolean {
  return prevCount > 0 && nextCount > 0 && nextCount < prevCount;
}

export function beatCountDropMessage(prevCount: number, nextCount: number): string {
  return `Beat count dropped (${prevCount} → ${nextCount}). Hard refresh again; if this persists, note the URL.`;
}
