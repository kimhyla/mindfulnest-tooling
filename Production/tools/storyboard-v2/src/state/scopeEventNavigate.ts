// PROJECT_SELECTOR_DEDICATED_PORT_NAV_V1 — cross-event scope = port navigation,
// not event/load on dedicated ports. See TECH_SPEC_DEDICATED_PORT_EVENT_NAV_V1.md.
// EVENT_DEDICATED_SERVER_PROVISION_V1 — await launchd before navigation.

import { pathappPatch } from '../api/client';
import { pushToast } from '../components/ui/Toast';
import { activeScope, activeProjectType, activeTargetVideo } from './scope';
import { activeTab } from './refreshSignals';
import {
  buildDedicatedPortEventUrl,
  eventIdToDedicatedPortNumber,
  resolveEventSwitchMode,
} from './scopeAuthorityResolve';

export const PORT_NAV_TOAST_KEY = 'mn:port-nav-toast';

export interface ProvisionReadyResult {
  ok: boolean;
  skipped: boolean;
  ready: boolean;
  port?: number;
  error?: string;
}

/** Idempotent launchd provision — call from any live server before cross-port navigate. */
export async function ensureDedicatedEventServerReady(
  targetEventId: string,
): Promise<ProvisionReadyResult> {
  const port = eventIdToDedicatedPortNumber(targetEventId);
  if (port == null) {
    return { ok: true, skipped: true, ready: true };
  }
  pushToast({
    kind: 'info',
    message: `Starting ${targetEventId} dedicated server on port ${port}…`,
    source: 'dedicated-port-provision',
    ttlMs: 8000,
  });
  const result = await pathappPatch<{
    ok?: boolean;
    ready?: boolean;
    skipped?: boolean;
    port?: number;
    error_message?: string;
    error?: string;
  }>(activeScope.value, 'event_provision_server', { event_id: targetEventId });
  if (!result.ok || !result.data?.ok) {
    const msg = result.data?.error_message ?? result.data?.error ?? result.error ?? `HTTP ${result.status}`;
    return { ok: false, skipped: false, ready: false, port, error: msg };
  }
  const data = result.data;
  if (data.skipped) {
    return { ok: true, skipped: true, ready: true };
  }
  const ready = Boolean(data.ready);
  const out: ProvisionReadyResult = {
    ok: ready,
    skipped: false,
    ready,
    port: data.port ?? port,
  };
  if (!ready) {
    out.error = 'server not ready after provision';
  }
  return out;
}

/**
 * Provision (if needed) then navigate to Event_N dedicated port.
 * Returns true when navigation started.
 */
export async function provisionAndNavigateToDedicatedPortEvent(
  targetEventId: string,
): Promise<boolean> {
  if (typeof window === 'undefined') return false;
  const currentPort = parseInt(window.location.port || '0', 10);
  if (resolveEventSwitchMode(targetEventId, currentPort) !== 'navigate') {
    return false;
  }
  const prov = await ensureDedicatedEventServerReady(targetEventId);
  if (!prov.ok) {
    pushToast({
      kind: 'error',
      message: `Could not start ${targetEventId} server: ${(prov.error ?? '').slice(0, 120)}`,
      source: 'dedicated-port-provision-error',
    });
    return false;
  }
  return navigateToDedicatedPortEvent(targetEventId);
}

/** Show toast on destination tab after cross-port navigation. */
export function consumePortNavToast(
  push: (entry: { kind: 'info'; message: string; source: string }) => void,
): void {
  if (typeof window === 'undefined') return;
  try {
    const raw = sessionStorage.getItem(PORT_NAV_TOAST_KEY);
    if (!raw) return;
    sessionStorage.removeItem(PORT_NAV_TOAST_KEY);
    const parsed = JSON.parse(raw) as { message?: string; source?: string };
    if (parsed?.message) {
      push({
        kind: 'info',
        message: parsed.message,
        source: parsed.source ?? 'dedicated-port-nav',
      });
    }
  } catch {
    // ignore corrupt flash payload
  }
}

/**
 * Navigate to Event_N dedicated port when current port !== target port.
 * Returns true when navigation started (caller must not continue event/load).
 */
export function navigateToDedicatedPortEvent(targetEventId: string): boolean {
  if (typeof window === 'undefined') return false;
  const currentPort = parseInt(window.location.port || '0', 10);
  if (resolveEventSwitchMode(targetEventId, currentPort) !== 'navigate') {
    return false;
  }
  const targetPort = eventIdToDedicatedPortNumber(targetEventId);
  if (targetPort == null) return false;

  const tab = activeTab.value;
  const video = activeProjectType.value === 'event'
    ? activeTargetVideo.value
    : 'standalone';

  const url = buildDedicatedPortEventUrl({
    eventId: targetEventId,
    tab: tab !== 'bg' && tab !== 'cropper' ? tab : null,
    video: video || null,
  });
  if (!url) return false;

  try {
    sessionStorage.setItem(
      PORT_NAV_TOAST_KEY,
      JSON.stringify({
        kind: 'info',
        message: `Opened ${targetEventId} on port ${targetPort} (dedicated server).`,
        source: 'dedicated-port-nav',
      }),
    );
  } catch {
    // navigation still proceeds without flash toast
  }

  window.location.assign(url);
  return true;
}
