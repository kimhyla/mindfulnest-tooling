# Firestore Security Rules + Atomic Write Patterns (Canonical)

**Status:** Canonical reference — this is the ruleset that Stage 3 must implement.
**Date:** April 17, 2026
**Source:** Rescued from `Research/FIREBASE_FIRESTORE_ARCHITECTURE_OPTIMIZATION_v1.md` §6, §10, §13.
**Related locked decisions:**
- `FIRESTORE_RULES_AND_TRANSACTIONS_CANONICAL`
- `THERAPIST_SUMMARY_CLOUD_FUNCTION_PATTERN`
- `FIRESTORE_FIELD_LEVEL_SANITIZATION_VIA_CLOUD_FUNCTION` (C4)
- `STAGE3_SECURITY_RULES_FIRST` (execution ordering)

---

## 1. Security Rules — Full Ruleset

The following `firestore.rules` is the CANONICAL starting point for MindfulNest Stage 3. It enforces the three non-negotiables locked under `STAGE3_SECURITY_RULES_FIRST`:

- Therapist can read only linked patients
- Parent can read/write only linked children
- Shared content (modules, storeItems, narrativeEvents, arcDefinitions) is read-only to any authenticated user

```firestore
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Therapist collection: therapists can read/write own doc only
    match /therapists/{therapistId} {
      allow read, write: if request.auth.uid == therapistId;
    }

    // Parent collection: parents can read/write own doc only
    match /parents/{parentId} {
      allow read, write: if request.auth.uid == parentId;
    }

    // Children: isolated by linkedParent or linkedTherapist
    match /children/{childId} {
      // Parent (caretaker) can read and write own child's document
      allow read, write: if request.auth.uid == resource.data.linkedParent;

      // Therapist can READ ONLY — no direct writes to child state
      allow read: if request.auth.uid == resource.data.linkedTherapist;

      // Subcollections: inherit parent-child linkage via get()
      match /{document=**} {
        allow read: if request.auth.uid == get(/databases/$(database)/documents/children/$(childId)).data.linkedParent;
        allow read: if request.auth.uid == get(/databases/$(database)/documents/children/$(childId)).data.linkedTherapist;
        allow write: if request.auth.uid == get(/databases/$(database)/documents/children/$(childId)).data.linkedParent;
      }
    }

    // Modules, storeItems, narrativeEvents, arcDefinitions: shared read-only content
    match /modules/{moduleId} {
      allow read: if request.auth != null;
    }

    match /storeItems/{itemId} {
      allow read: if request.auth != null;
    }

    match /narrativeEvents/{eventId} {
      allow read: if request.auth != null;
    }

    match /arcDefinitions/{arcId} {
      allow read: if request.auth != null;
    }

    // therapistInvites: parents can claim, therapists can create
    match /therapistInvites/{code} {
      allow read: if request.auth != null;
      allow create: if request.auth.uid == request.resource.data.therapistId;
      allow update: if request.auth.uid == request.resource.data.claimedByParent;
    }
  }
}
```

### Non-negotiable invariants (verified by `@firebase/rules-unit-testing` per `STAGE3_SECURITY_RULES_FIRST`)

1. **Therapist read isolation:** a therapist with `uid=T1` cannot read child `C2` where `C2.linkedTherapist != T1`. Tested both allowed (linked) and denied (not linked) paths.
2. **Parent read/write isolation:** a parent with `uid=P1` cannot read or write child `C2` where `C2.linkedParent != P1`.
3. **Child-write protected fields:** child-side app writes cannot mutate any of: `coins`, `runeStates`, `modulesCompleted`, `ownedItems`, or any other computed progression state. (See §3 — these updates MUST flow through Cloud Functions triggered by completionLog writes; the rules enforce that client writes cannot touch those keys directly.)

### Protected-field immutability pattern

The rules above grant `write: if parent-linked`, which on its own would let a parent client mutate protected fields. The canonical enforcement (see `PROTECTED_FIELD_IMMUTABILITY_PATTERN`, LD-125, April 17 2026) uses a value-based `fieldUnchanged()` helper rather than `affectedKeys()` so nested-map mutations are caught:

```
function fieldUnchanged(field) {
  return resource.data.get(field, null) == request.resource.data.get(field, null);
}

function anyProtectedFieldChanged() {
  return !fieldUnchanged('coins')
      || !fieldUnchanged('runeStates')
      || !fieldUnchanged('modulesCompleted')
      || !fieldUnchanged('ownedItems')
      || !fieldUnchanged('engagementStatus')
      || !fieldUnchanged('sessionsThisWeek')
      || !fieldUnchanged('domainSessionCounts');
}
```

Apply `&& !anyProtectedFieldChanged()` to parent/child write allowances on `/children/{childId}`. `resource.data.get()` is null-safe on CREATE ops per the April 17 2026 emulator verification.

### CRUD surface summary

| Actor | `/therapists/{self}` | `/parents/{self}` | `/children/{linked}` | child subcollections | shared content |
|-------|----------------------|-------------------|----------------------|----------------------|----------------|
| Therapist | read+write | — | read only | read only | read |
| Parent | — | read+write | read+write (non-protected fields) | read+write | read |
| Child (device) | — | — | via parent session only | via parent session only | read |
| Unauthenticated | deny | deny | deny | deny | deny |

---

## 2. Atomic Writes — `runTransaction` Pattern

All writes that touch more than one document (or more than one field whose consistency matters) MUST use `runTransaction`. `serverTimestamp()` is the tiebreaker when offline writes collide with server-side Cloud Function updates.

### Canonical pattern — module completion

```javascript
import {
  doc, runTransaction, serverTimestamp, increment
} from 'firebase/firestore';

const childRef = doc(db, 'children', childId);
const barRef = doc(db, 'children', childId, 'bars', activeBarId);

await runTransaction(db, async (transaction) => {
  // Read inside the transaction (atomic snapshot)
  const childSnap = await transaction.get(childRef);
  const barSnap = await transaction.get(barRef);

  if (!childSnap.exists() || !barSnap.exists()) {
    throw new Error('Child or active bar missing');
  }

  const coinAward = 30; // Arc 1: arcFloor + moduleIndex*3

  // NOTE: protected fields (coins, modulesCompleted, runeStates) are
  // written by the Cloud Function triggered by completionLog create —
  // NOT by the client. Client-side runTransaction only writes the
  // completionLog entry + bar circle count. The server-side transaction
  // shown here is what the Cloud Function does.

  transaction.update(childRef, {
    coins: increment(coinAward),
    modulesCompleted: increment(1),
    runeStates: { [domain]: increment(1) },
    lastActivityAt: serverTimestamp()
  });

  transaction.update(barRef, {
    completedCircles: increment(1),
    updatedAt: serverTimestamp()
  });

  transaction.set(
    doc(db, 'children', childId, 'completionLog', autoId()),
    {
      moduleId,
      domain,
      barId: activeBarId,
      completedAt: serverTimestamp(),
      durationSeconds
    }
  );
});
```

### Why `runTransaction` + `serverTimestamp` is required

Offline-first architecture (Rule: CANONICAL_DATA_MODEL §5 offline persistence) means the child device can queue writes for hours or days before syncing. Without atomic transactions and server-side tiebreaking:

- Child completes module offline → local optimistic write `coins = 130`
- Parent/therapist mutates server-side `coins = 50` while child is offline
- Child reconnects → cached write overwrites the parent action → parent's action is lost

`serverTimestamp()` lets the Cloud Function reject stale client writes if the child's queued write is older than the most recent server-side update. `runTransaction` guarantees the bar-circle update and the completion-log write are atomic (both land or neither lands).

### Hard rule: protected progression fields are server-owned

Client code NEVER writes `coins`, `modulesCompleted`, `runeStates`, `ownedItems`, `engagementStatus`, `sessionsThisWeek`, or `domainSessionCounts` directly. The only client-side mutation is creating entries under `/children/{childId}/completionLog/`. The Cloud Function in §3 is the single writer for all protected progression fields. This prevents the client-trust anti-pattern that `STAGE3_SECURITY_RULES_FIRST` exists to block.

---

## 3. Pre-computed Therapist Summary — Cloud Function Pattern

**Locked decision:** `THERAPIST_SUMMARY_CLOUD_FUNCTION_PATTERN`
**Rationale:** at 40 patients per therapist, the naive "read completionLog per child" approach costs 400+ reads per dashboard load (10x more expensive). The Cloud Function below pre-computes summary fields on the child document so the therapist dashboard needs only one query per child (1 read each, 41 reads total for 40 patients + 1 therapist doc). Savings compound at scale (~90% at 100K children).

### Trigger

`onCreate` of any document under `children/{childId}/completionLog/{logId}`.

### Updates (all on `children/{childId}`)

| Field | Type | Meaning |
|-------|------|---------|
| `sessionsThisWeek` | number | Count of completionLog entries where `completedAt >= weekStart(now)`. |
| `engagementStatus` | string | One of `active` (>=3 sessions this week), `moderate` (1–2), `inactive` (0, and >7 days since `lastActivityAt`). Helper `computeEngagementStatus()` derives this from `completedAt` + prior state. |
| `domainSessionCounts` | map<string, number> | Rolling total per domain (e.g., `{ breathing: 5, watching: 3, ... }`). Incremented on each completion. |
| `lastActivityAt` | timestamp | Mirror of the completionLog entry's `completedAt`. |

All writes are atomic via `db.runTransaction`. Idempotency: if the same completionLog entry fires the function twice (Cloud Functions at-least-once delivery), the function reads `lastProcessedLogId` on the child doc and skips if it matches the incoming `logId`.

### Reference implementation

```javascript
exports.updateChildSummary = functions.firestore
  .document('children/{childId}/completionLog/{logId}')
  .onCreate(async (snap, context) => {
    const { childId, logId } = context.params;
    const { completedAt, domain } = snap.data();

    const childRef = db.collection('children').doc(childId);

    await db.runTransaction(async (tx) => {
      const childDoc = await tx.get(childRef);
      if (!childDoc.exists) return;  // child deleted — drop update
      const data = childDoc.data();

      // Idempotency guard — at-least-once delivery protection
      if (data.lastProcessedLogId === logId) return;

      const newSessThisWeek = computeSessionsThisWeek(
        data.sessionsThisWeek || 0,
        data.lastActivityAt,
        completedAt
      );
      const newStatus = computeEngagementStatus(completedAt, data);
      const newDomainCounts = { ...(data.domainSessionCounts || {}) };
      newDomainCounts[domain] = (newDomainCounts[domain] || 0) + 1;

      tx.update(childRef, {
        sessionsThisWeek: newSessThisWeek,
        engagementStatus: newStatus,
        domainSessionCounts: newDomainCounts,
        lastActivityAt: completedAt,
        lastProcessedLogId: logId
      });
    });
  });
```

### Cost comparison

| Approach | Reads per dashboard load (40 patients) | Cost at 1K therapists × 1 load/day × 30 days |
|----------|---------------------------------------|----------------------------------------------|
| Naive (read completionLog per child) | 40 children × ~10 log reads = 400 reads | ~$24/month |
| Pre-computed summary (this pattern) | 1 therapist doc + 40 child docs = 41 reads | ~$2.40/month |

90% savings, scales linearly with active therapists.

### Field-level sanitization addendum (C4 — `FIRESTORE_FIELD_LEVEL_SANITIZATION_VIA_CLOUD_FUNCTION`)

Firestore rules cannot enforce field-level read restrictions — if a therapist can read the child document, they can read every field on it. Some fields (e.g., free-text parent notes, the parent's full account email, the child's raw completionLog entries) must be filtered out of therapist-facing reads.

**Pattern:** expose a dedicated Cloud Function (`getTherapistDashboardForChild(childId)`) that reads the child doc server-side, strips the therapist-forbidden fields, and returns only the sanitized projection. Therapist clients never read `/children/{childId}` directly — they call the Cloud Function. The security rules still prevent unauthorized therapist access to the underlying doc; the Cloud Function adds the projection layer that rules can't express.

This is documented here rather than a separate doc because it lives in the same Cloud Functions codebase as the summary pattern above. See LD `FIRESTORE_FIELD_LEVEL_SANITIZATION_VIA_CLOUD_FUNCTION` for the locked decision.

---

## 4. Implementation Ordering (Stage 3)

Per `STAGE3_SECURITY_RULES_FIRST` (LD registered 2026-04-17):

1. Write `firestore.rules` matching §1.
2. Write `@firebase/rules-unit-testing` suite covering the three non-negotiables + the protected-fields test matrix.
3. Run rules tests locally — both allowed and denied paths must pass.
4. Only then: implement data-model code (Cloud Function summaries §3, client transactions §2, dashboard reads).

This ordering prevents client-trust anti-patterns (client-side coin computation, client-writable progression state) from being baked into downstream code.

---

## Change Log

| Date | Change | Source |
|------|--------|--------|
| 2026-04-17 | Initial canonical extraction from research doc. | Rescue of orphaned content from `Research/FIREBASE_FIRESTORE_ARCHITECTURE_OPTIMIZATION_v1.md` §6, §10, §13. |
