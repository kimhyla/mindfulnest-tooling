/** Cache key builders for Producer Session Layer (PSL). */

export function bgSessionKey(eventId: string, videoRole: string): string {
  return `${eventId}|${videoRole}`;
}

export function mapSessionKey(eventId: string): string {
  return eventId;
}

export function storyboardSessionKey(
  eventId: string,
  projectType: string,
  milestoneId: string | null,
): string {
  return `${eventId}|${projectType}|${milestoneId ?? ''}`;
}

export function stitchJobSessionKey(
  eventId: string,
  projectType?: string,
  milestoneId?: string | null,
): string {
  if (projectType === 'milestone' && milestoneId) {
    return `milestone:${milestoneId}`;
  }
  return eventId;
}

export function stitchJobNameForScope(
  eventId: string,
  projectType?: string,
  milestoneId?: string | null,
): string {
  if (projectType === 'milestone' && milestoneId) {
    return `milestone_${milestoneId}_stitch`;
  }
  return `${eventId}_stitch`;
}
