#!/usr/bin/env node
"use strict";
/**
 * Firebase Firestore rules actor-matrix test (Phase 2.7).
 *
 * Tests child / parent / therapist / unauthenticated actors across
 * get, list/query, and collectionGroup shapes — both positive (assertSucceeds)
 * and negative (assertFails) cases.
 *
 * Usage:
 *   FIREBASE_RULES_PATH=firestore.rules node Production/scripts/test_firestore_rules.js
 *
 * Required devDependencies (install once):
 *   npm install --save-dev @firebase/rules-unit-testing firebase
 *
 * Required env vars:
 *   FIREBASE_RULES_PATH  — path to firestore.rules (default: firestore.rules)
 *   FIREBASE_PROJECT_ID  — emulator project id (default: demo-mindfulnest-ci)
 *
 * Exit 0 on full PASS, exit 1 on any failure.
 */

const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");

const {
  initializeTestEnvironment,
  assertSucceeds,
  assertFails,
} = require("@firebase/rules-unit-testing");

const {
  doc,
  setDoc,
  getDoc,
  collection,
  query,
  where,
  getDocs,
  collectionGroup,
} = require("firebase/firestore");

const PROJECT_ID =
  process.env.FIREBASE_PROJECT_ID || "demo-mindfulnest-ci";

const RULES_PATH =
  process.env.FIREBASE_RULES_PATH ||
  path.resolve(process.cwd(), "firestore.rules");

function mustReadRules(filePath) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Rules file not found: ${filePath}`);
  }
  return fs.readFileSync(filePath, "utf8");
}

async function seedData(testEnv) {
  await testEnv.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore();

    // Family f1 — child c1, parent p1, therapist t1
    await setDoc(doc(db, "families/f1"), {
      familyId: "f1",
      parentId: "p1",
      childIds: ["c1"],
      therapistIds: ["t1"],
    });
    await setDoc(doc(db, "families/f1/sessions/s1"), {
      familyId: "f1",
      ownerParentId: "p1",
      childIds: ["c1"],
      therapistIds: ["t1"],
      coinTally: 12,
      createdAt: 1,
    });
    await setDoc(doc(db, "families/f1/therapist_notes/n1"), {
      familyId: "f1",
      therapistId: "t1",
      visibility: "therapist",
      note: "f1 therapist note",
    });

    // Family f2 — separate tenant (cross-family isolation tests)
    await setDoc(doc(db, "families/f2"), {
      familyId: "f2",
      parentId: "p2",
      childIds: ["c2"],
      therapistIds: ["t2"],
    });
    await setDoc(doc(db, "families/f2/sessions/s2"), {
      familyId: "f2",
      ownerParentId: "p2",
      childIds: ["c2"],
      therapistIds: ["t2"],
      coinTally: 3,
      createdAt: 2,
    });
    await setDoc(doc(db, "families/f2/therapist_notes/n2"), {
      familyId: "f2",
      therapistId: "t2",
      visibility: "therapist",
      note: "f2 therapist note",
    });
  });
}

async function run() {
  const rules = mustReadRules(RULES_PATH);

  const testEnv = await initializeTestEnvironment({
    projectId: PROJECT_ID,
    firestore: { rules },
  });

  try {
    await seedData(testEnv);

    // Actor contexts
    const unauthDb = testEnv.unauthenticatedContext().firestore();
    const childDb = testEnv
      .authenticatedContext("c1", { role: "child", familyId: "f1" })
      .firestore();
    const parentDb = testEnv
      .authenticatedContext("p1", { role: "parent", familyId: "f1" })
      .firestore();
    const therapistDb = testEnv
      .authenticatedContext("t1", { role: "therapist", familyIds: ["f1"] })
      .firestore();

    // ── Unauthenticated: all reads denied ──────────────────────────────────
    await assertFails(getDoc(doc(unauthDb, "families/f1/sessions/s1")));
    await assertFails(
      getDocs(query(collection(unauthDb, "families/f1/sessions")))
    );
    console.log("PASS unauthenticated: all reads denied");

    // ── Parent: own family allowed, cross-family denied ────────────────────
    await assertSucceeds(getDoc(doc(parentDb, "families/f1/sessions/s1")));
    await assertSucceeds(
      getDocs(query(collection(parentDb, "families/f1/sessions")))
    );
    await assertFails(getDoc(doc(parentDb, "families/f2/sessions/s2")));
    await assertFails(
      getDocs(query(collection(parentDb, "families/f2/sessions")))
    );
    console.log("PASS parent: own-family sessions allowed, cross-family denied");

    // ── Child: own family sessions allowed, cross-family + therapist notes denied
    await assertSucceeds(getDoc(doc(childDb, "families/f1/sessions/s1")));
    await assertFails(getDoc(doc(childDb, "families/f2/sessions/s2")));
    await assertFails(getDoc(doc(childDb, "families/f1/therapist_notes/n1")));
    console.log(
      "PASS child: own sessions allowed, cross-family + therapist notes denied"
    );

    // ── Therapist: assigned family notes allowed, unassigned denied ─────────
    await assertSucceeds(
      getDoc(doc(therapistDb, "families/f1/therapist_notes/n1"))
    );
    await assertSucceeds(
      getDocs(
        query(collection(therapistDb, "families/f1/therapist_notes"))
      )
    );
    await assertFails(
      getDoc(doc(therapistDb, "families/f2/therapist_notes/n2"))
    );
    console.log(
      "PASS therapist: assigned-family notes allowed, unassigned denied"
    );

    // ── collectionGroup: therapist can query own assignments, child denied ──
    const therapistNotesCg = query(
      collectionGroup(therapistDb, "therapist_notes"),
      where("therapistId", "==", "t1")
    );
    await assertSucceeds(getDocs(therapistNotesCg));

    const childCg = query(
      collectionGroup(childDb, "therapist_notes"),
      where("familyId", "==", "f1")
    );
    await assertFails(getDocs(childCg));
    console.log("PASS collectionGroup: therapist allowed, child denied");

    // ── Vacuity guard: positive reads actually return data ──────────────────
    const parentSession = await getDoc(
      doc(parentDb, "families/f1/sessions/s1")
    );
    assert.equal(
      parentSession.exists(),
      true,
      "Parent session doc should exist (non-vacuous positive)"
    );

    console.log(
      "\nPASS: Firestore actor matrix clean " +
        "(child/parent/therapist/unauth × get/list/collectionGroup + positive/negative)."
    );
  } finally {
    await testEnv.cleanup();
  }
}

run().catch((err) => {
  console.error("FAIL: Firestore actor matrix failed.");
  console.error(err?.stack || String(err));
  process.exit(1);
});
