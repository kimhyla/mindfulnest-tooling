// ProjectSelector — top-of-app dropdown for switching between Events AND Milestones.
// Per LD PROJECT_SELECTOR_V1 (S5.5e). Extends LD-467 MULTI_EVENT_SELECTOR_V1
// with milestone listing + "+ New Milestone" via the shared Modal primitive.
//
// Replaces EventSelector (removed from tab bar). Reads /api/project/list (v3-added),
// navigates to dedicated port OR posts /api/event/load on change. Server's
// event_load_lock + monotonic event_generation guarantee atomic swap.
//
// URL parsing: milestone wins if both ?event= and ?milestone= are present
// per Cursor v8 Q8 (ScopeBoundary error-toasts the conflict; v59 client
// honors the chosen value).

import { useEffect, useState } from 'preact/hooks';
import {
  activeScope, makeScope, activeProjectType, activeMilestoneId, activeTargetVideo,
  activeVideoRole, persistActiveMilestoneId, syncMilestoneUrlParams,
} from '../state/scope';
import { apiGet, pathappPatch, loadEvent, noteClientPinnedEvent } from '../api/client';
import { provisionAndNavigateToDedicatedPortEvent } from '../state/scopeEventNavigate';
import { Modal } from './ui/Modal';
import { Select } from './ui/Select';
import { pushToast } from './ui/Toast';

interface EventListItem {
  event_id: string;
  path: string;
  storyboard?: string;
}

interface MilestoneListItem {
  milestone_id: string;
  milestone_label?: string | null;
  path?: string;
}

interface ProjectListResponse {
  ok: boolean;
  events?: EventListItem[];
  milestones?: MilestoneListItem[];
  scope_type?: 'event' | 'milestone';
  active_event_id?: string;
  active_milestone_id?: string | null;
}

// Sentinel values used inside the <select> to trigger non-load actions.
const NEW_MILESTONE_VALUE = '__new_milestone__';
const NEW_EVENT_VALUE = '__new_event__'; // S5.5c+e proper-fix +NewEvent: enabled

const MILESTONE_ID_REGEX = /^[a-z0-9][a-z0-9_-]{2,63}$/;
const RESERVED_PREFIXES = [
  'event_', 'module_', 'arc_', 'phase_', 'scene_', 'milestone_',
  'test_', 'system_', 'admin_', 'api_',
];

function validateMilestoneId(id: string): string | null {
  if (!id) return 'milestone_id required';
  if (!MILESTONE_ID_REGEX.test(id)) {
    return 'must match ^[a-z0-9][a-z0-9_-]{2,63}$ (lowercase, 3-64 chars, only [a-z0-9_-])';
  }
  for (const prefix of RESERVED_PREFIXES) {
    if (id.startsWith(prefix)) {
      return `cannot start with reserved prefix "${prefix}"`;
    }
  }
  return null;
}

// S5.5c+e proper-fix +NewEvent — event_id validation per spec §4.4
// (regex ^[A-Z][A-Za-z0-9_]{2,63}$, reserved prefixes Test_/_/Tmp_).
const EVENT_ID_REGEX = /^[A-Z][A-Za-z0-9_]{2,63}$/;
const EVENT_RESERVED_PREFIXES = ['Test_', '_', 'Tmp_'];

function validateEventId(id: string): string | null {
  if (!id) return 'event_id required';
  if (!EVENT_ID_REGEX.test(id)) {
    return 'must match ^[A-Z][A-Za-z0-9_]{2,63}$ (PascalCase, 3-64 chars)';
  }
  for (const prefix of EVENT_RESERVED_PREFIXES) {
    if (id.startsWith(prefix)) {
      return `cannot start with reserved prefix "${prefix}"`;
    }
  }
  return null;
}

interface NewEventModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (eventId: string) => void;
}

function NewEventModal({ open, onClose, onCreated }: NewEventModalProps) {
  const [eventId, setEventId] = useState('');
  const [eventLabel, setEventLabel] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const liveError = eventId.length > 0 ? validateEventId(eventId) : null;

  const onSubmit = async () => {
    const idError = validateEventId(eventId);
    if (idError) {
      setError(idError);
      return;
    }
    setSubmitting(true);
    setError(null);
    const result = await pathappPatch<{ ok: boolean; event_id?: string; event_dir?: string; error?: string }>(
      activeScope.value, 'event_create', {
        event_id: eventId,
        event_label: eventLabel || undefined,
      },
    );
    setSubmitting(false);
    if (result.ok && result.data?.ok) {
      pushToast({ kind: 'success', message: `Event "${eventId}" created`, source: 'event-create' });
      setEventId('');
      setEventLabel('');
      onCreated(eventId);
    } else {
      const msg = result.data?.error ?? result.error ?? `HTTP ${result.status}`;
      setError(msg);
    }
  };

  return (
    <Modal
      id="new-event"
      title="+ New Event"
      open={open}
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            class="mn-btn"
            data-testid="new-event-cancel"
            onClick={onClose}
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="button"
            class="mn-btn mn-btn-primary"
            data-testid="new-event-create"
            onClick={onSubmit}
            disabled={submitting || !eventId || liveError !== null}
          >
            {submitting ? 'Creating…' : 'Create'}
          </button>
        </>
      }
    >
      <p class="mn-dim">
        Events are top-level production scopes (e.g. "Event_3", "M5E1").
        They live at <code>Production/Event_&lt;id&gt;/</code>.
      </p>
      <label class="mn-select-label" for="new-event-id">Event ID:</label>
      <input
        id="new-event-id"
        class="mn-project-modal-input"
        type="text"
        placeholder="Event_3"
        value={eventId}
        onInput={(e) => setEventId((e.target as HTMLInputElement).value)}
        data-testid="new-event-id-input"
        autofocus
      />
      <p class="mn-project-modal-help">
        PascalCase, 3–64 chars, alphanumeric + <code>_</code>. First char
        uppercase. Cannot start with reserved prefixes
        (<code>Test_</code>, <code>_</code>, <code>Tmp_</code>).
      </p>
      {liveError ? (
        <p class="mn-project-modal-error" data-testid="new-event-id-error">
          {liveError}
        </p>
      ) : null}

      <label class="mn-select-label" for="new-event-label">Display label (optional):</label>
      <input
        id="new-event-label"
        class="mn-project-modal-input"
        type="text"
        placeholder="My Event"
        value={eventLabel}
        onInput={(e) => setEventLabel((e.target as HTMLInputElement).value)}
        data-testid="new-event-label-input"
      />

      {error ? (
        <p class="mn-project-modal-error" data-testid="new-event-error">
          {error}
        </p>
      ) : null}
    </Modal>
  );
}

interface NewMilestoneModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (milestoneId: string) => void;
}

function NewMilestoneModal({ open, onClose, onCreated }: NewMilestoneModalProps) {
  const [milestoneId, setMilestoneId] = useState('');
  const [milestoneLabel, setMilestoneLabel] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Live regex feedback as the user types.
  const liveError = milestoneId.length > 0 ? validateMilestoneId(milestoneId) : null;

  const onSubmit = async () => {
    const idError = validateMilestoneId(milestoneId);
    if (idError) {
      setError(idError);
      return;
    }
    setSubmitting(true);
    setError(null);
    const result = await pathappPatch<{ ok: boolean; milestone_id?: string; error?: string }>(
      activeScope.value, 'milestones_create', {
        milestone_id: milestoneId,
        milestone_label: milestoneLabel || undefined,
      },
    );
    setSubmitting(false);
    if (result.ok && result.data?.ok) {
      pushToast({ kind: 'success', message: `Milestone "${milestoneId}" created`, source: 'milestone-create' });
      setMilestoneId('');
      setMilestoneLabel('');
      onCreated(milestoneId);
    } else {
      const msg = result.data?.error ?? result.error ?? `HTTP ${result.status}`;
      setError(msg);
    }
  };

  return (
    <Modal
      id="new-milestone"
      title="+ New Milestone"
      open={open}
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            class="mn-btn"
            data-testid="new-milestone-cancel"
            onClick={onClose}
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="button"
            class="mn-btn mn-btn-primary"
            data-testid="new-milestone-create"
            onClick={onSubmit}
            disabled={submitting || !milestoneId || liveError !== null}
          >
            {submitting ? 'Creating…' : 'Create'}
          </button>
        </>
      }
    >
      <p class="mn-dim">
        Milestones are standalone single-video projects (e.g. trailers, app intro).
        They live at <code>Production/Milestones/&lt;id&gt;/</code>.
      </p>
      <label class="mn-select-label" for="new-milestone-id">Milestone ID:</label>
      <input
        id="new-milestone-id"
        class="mn-project-modal-input"
        type="text"
        placeholder="my_milestone_id"
        value={milestoneId}
        onInput={(e) => setMilestoneId((e.target as HTMLInputElement).value)}
        data-testid="new-milestone-id-input"
        autofocus
      />
      <p class="mn-project-modal-help">
        Lowercase, 3–64 chars, alphanumeric + <code>_</code> + <code>-</code>.
        First char must be alphanumeric. Cannot start with reserved prefixes
        (event_, module_, arc_, phase_, scene_, milestone_, test_, system_, admin_, api_).
      </p>
      {liveError ? (
        <p class="mn-project-modal-error" data-testid="new-milestone-id-error">
          {liveError}
        </p>
      ) : null}

      <label class="mn-select-label" for="new-milestone-label">Display label (optional):</label>
      <input
        id="new-milestone-label"
        class="mn-project-modal-input"
        type="text"
        placeholder="My Milestone"
        value={milestoneLabel}
        onInput={(e) => setMilestoneLabel((e.target as HTMLInputElement).value)}
        data-testid="new-milestone-label-input"
      />

      {error ? (
        <p class="mn-project-modal-error" data-testid="new-milestone-error">
          {error}
        </p>
      ) : null}
    </Modal>
  );
}

export function ProjectSelector() {
  const [events, setEvents] = useState<EventListItem[]>([]);
  const [milestones, setMilestones] = useState<MilestoneListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showNewMilestone, setShowNewMilestone] = useState(false);
  const [showNewEvent, setShowNewEvent] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  // Fetch project list.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await apiGet<ProjectListResponse>('project_list');
      if (cancelled) return;
      setLoading(false);
      if (res.ok && res.data) {
        setEvents(res.data.events ?? []);
        setMilestones(res.data.milestones ?? []);
        setErr(null);
      } else {
        setErr(res.error ?? 'failed to load project list');
      }
    })();
    return () => { cancelled = true; };
  }, [refreshTick]);

  // URL precedence on first mount: milestone wins if both present (Cursor v8 Q8).
  // ScopeBoundary already routes initial scope; this hook just notifies via toast
  // on conflict so Kim sees what happened.
  useEffect(() => {
    try {
      const url = new URL(window.location.href);
      const eventParam = url.searchParams.get('event');
      const milestoneParam = url.searchParams.get('milestone');
      if (eventParam && milestoneParam) {
        pushToast({
          kind: 'info',
          message: `URL had both ?event=${eventParam} and ?milestone=${milestoneParam}. Milestone wins.`,
          source: 'project-selector-url-conflict',
        });
      }
    } catch {
      // window.location not available; ignore.
    }
  }, []);

  // Compute current selected value.
  // Format: 'event:<id>' or 'milestone:<id>'.
  const currentValue = (() => {
    if (activeProjectType.value === 'milestone' && activeMilestoneId.value) {
      return `milestone:${activeMilestoneId.value}`;
    }
    return `event:${activeScope.value.event_id}`;
  })();

  const onChange = async (next: string) => {
    if (next === NEW_MILESTONE_VALUE) {
      setShowNewMilestone(true);
      return;
    }
    if (next === NEW_EVENT_VALUE) {
      // S5.5c+e proper-fix +NewEvent: enabled — opens modal, posts to
      // /api/event/create, auto-loads on success (mirrors milestone flow).
      setShowNewEvent(true);
      return;
    }
    if (next === currentValue) return;

    if (next.startsWith('event:')) {
      const newEventId = next.slice('event:'.length);
      // PROJECT_SELECTOR_DEDICATED_PORT_NAV_V1 + EVENT_DEDICATED_SERVER_PROVISION_V1
      if (await provisionAndNavigateToDedicatedPortEvent(newEventId)) {
        return;
      }
      const result = await loadEvent(newEventId);
      if (!result.ok) {
        pushToast({
          kind: 'error',
          message: `Event load failed: HTTP ${result.status}: ${(result.error ?? '').slice(0, 80)}`,
          source: 'project-selector-event-load-error',
        });
        return;
      }
      const data = result.data;
      if (!data) {
        pushToast({
          kind: 'error',
          message: 'event_load returned no data',
          source: 'project-selector-event-load-error',
        });
        return;
      }
      activeScope.value = makeScope(data.event_id, null, data.event_generation);
      noteClientPinnedEvent(data.event_id);
      activeProjectType.value = 'event';
      activeMilestoneId.value = null;
      persistActiveMilestoneId(null);
      activeTargetVideo.value = 'intro';
      activeVideoRole.value = 'intro';
      if (typeof document !== 'undefined') {
        document.body.setAttribute('data-active-project-type', 'event');
      }
      try {
        const url = new URL(window.location.href);
        url.searchParams.delete('milestone');
        url.searchParams.set('event', data.event_id);
        url.searchParams.set('video', 'intro');
        window.history.replaceState({}, '', url.toString());
      } catch {
        // headless context — fine.
      }
      setRefreshTick((n) => n + 1);
    } else if (next.startsWith('milestone:')) {
      const milestoneId = next.slice('milestone:'.length);
      const result = await pathappPatch<{ ok: boolean; milestone_id?: string }>(
        activeScope.value, 'milestone_load', { milestone_id: milestoneId },
      );
      if (result.ok && result.data?.ok) {
        activeProjectType.value = 'milestone';
        activeMilestoneId.value = milestoneId;
        activeTargetVideo.value = 'standalone';
        persistActiveMilestoneId(milestoneId);
        syncMilestoneUrlParams(milestoneId);
        try {
          const url = new URL(window.location.href);
          url.searchParams.delete('event');
          url.searchParams.set('milestone', milestoneId);
          url.searchParams.set('video', 'standalone');
          window.history.replaceState({}, '', url.toString());
        } catch {
          // headless context — fine.
        }
        setRefreshTick((n) => n + 1);
      } else {
        pushToast({
          kind: 'error',
          message: `Milestone load failed: ${result.error ?? `HTTP ${result.status}`}`,
          source: 'project-selector-milestone-load-error',
        });
      }
    }
  };

  return (
    <div class="mn-project-selector" data-testid="project-selector">
      <Select
        id="project"
        label="Project:"
        value={currentValue}
        onChange={onChange}
        disabled={loading}
        groups={[
          {
            label: 'Events',
            options: [
              ...events.map((e) => ({
                value: `event:${e.event_id}`,
                label: e.event_id,
              })),
              { value: NEW_EVENT_VALUE, label: '+ New Event…' },
            ],
          },
          {
            label: 'Milestones',
            options: [
              ...milestones.map((m) => ({
                value: `milestone:${m.milestone_id}`,
                label: m.milestone_label
                  ? `${m.milestone_id} — ${m.milestone_label}`
                  : m.milestone_id,
              })),
              { value: NEW_MILESTONE_VALUE, label: '+ New Milestone…' },
            ],
          },
        ]}
      />
      {err ? (
        <span class="mn-project-selector-error" data-testid="project-selector-error">{err}</span>
      ) : null}
      <NewMilestoneModal
        open={showNewMilestone}
        onClose={() => setShowNewMilestone(false)}
        onCreated={async (id) => {
          // R1.2 fix: auto-load the newly-created milestone so the UI scope
          // updates immediately (paired with R1 dep-array fix in BgTab +
          // StoryboardTab so downstream views refetch). Per spec §5 Phase 3.1.
          setShowNewMilestone(false);
          setRefreshTick((n) => n + 1);
          const loadResult = await pathappPatch<{ ok: boolean; milestone_id?: string }>(
            activeScope.value, 'milestone_load', { milestone_id: id },
          );
          if (loadResult.ok && loadResult.data?.ok) {
            activeProjectType.value = 'milestone';
            activeMilestoneId.value = id;
            activeTargetVideo.value = 'standalone';
            persistActiveMilestoneId(id);
          } else {
            pushToast({
              kind: 'error',
              message: `Auto-load failed for "${id}": ${loadResult.error ?? 'unknown'}`,
              source: 'milestone-auto-load-error',
            });
          }
        }}
      />
      <NewEventModal
        open={showNewEvent}
        onClose={() => setShowNewEvent(false)}
        onCreated={async (id) => {
          // +NewEvent fix: after creating the event server-side, auto-load
          // it (mirrors R1.2 milestone pattern).
          setShowNewEvent(false);
          setRefreshTick((n) => n + 1);
          if (await provisionAndNavigateToDedicatedPortEvent(id)) {
            return;
          }
          const loadRes = await loadEvent(id);
          if (loadRes.ok && loadRes.data) {
            const data = loadRes.data;
            activeScope.value = makeScope(data.event_id, null, data.event_generation);
            noteClientPinnedEvent(data.event_id);
            activeProjectType.value = 'event';
            activeMilestoneId.value = null;
            persistActiveMilestoneId(null);
          } else {
            pushToast({
              kind: 'error',
              message: `Auto-load failed for "${id}": HTTP ${loadRes.status}`,
              source: 'event-auto-load-error',
            });
          }
        }}
      />
    </div>
  );
}
