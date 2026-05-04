#!/usr/bin/env python3
"""
V1 Scope Condensation — Directus governance writer.
Session: 2026-04-20
Task ID: v1-scope-condensation-sweep-20260420
Preflight ID: 134

Writes:
  - 15 new LDs to prod_locked_decisions (idempotent on decision_key)
  - 6 AMENDs to existing LDs (LD-128 + 5 others)
  - 18 new blockers to prod_blockers (idempotent on title)
  - Activity log rows + final summary

Module count: ~48 (8 arcs × 6 modules) per Kim 2026-04-20 9:15am decision
(was ~38 in Agent 1 draft; Kim reversed per-arc cut to hit 52-session target).

Run:
  python3 v1_scope_condensation_locks_20260420.py --dry-run
  python3 v1_scope_condensation_locks_20260420.py
"""
import argparse, json, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = "https://directus-production-3460.up.railway.app"
EMAIL = "kimhyla11@gmail.com"
PASSWORD = "directus11$"
TASK_ID = "v1-scope-condensation-sweep-20260420"
SESSION_DATE = "2026-04-20"
PREFLIGHT_ID = 134


def _req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} on {method} {path}: {body_err}") from e


def auth():
    return _req("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})["data"]["access_token"]


def fields(token, coll):
    return {f["field"] for f in _req("GET", f"/fields/{coll}", token=token).get("data", [])}


def find_by(token, coll, field, value, select="id,decision_key"):
    q = urllib.parse.urlencode({f"filter[{field}][_eq]": value, "fields": select, "limit": 3})
    return _req("GET", f"/items/{coll}?{q}", token=token).get("data", [])


# ============================================================================
# NEW LDs (15)
# ============================================================================

NEW_LDS = [
    {
        "decision_key": "V1_SCOPE_CONDENSED_20260420",
        "decision_name": "V1 scope condensed — 8 arcs, ~48 modules (6/arc), 5 creatures + Oliver at M3",
        "severity": "HIGH", "task_category": "app_architecture", "enforcement_type": "governed_file",
        "decision_text": (
            "V1 ship scope locked 2026-04-20:\n\n"
            "- ARCS: 8 (was 9). Arc 8 Hopegrove cut (Benson cut).\n"
            "- MODULES: ~48 (8 arcs × 6 modules). Module count per arc PRESERVED — no uniform cut.\n"
            "  Rationale: 26-week program × 2 modules/week = 52 sessions. ~48 unique + ~4-8 Spell Book replays fills the target.\n"
            "  Optional surgical per-arc cuts remain available for specific redundant events Kim identifies, but default is 6/arc.\n"
            "- CREATURES: 5 (Tessa, Luna, Ember, Bork, Bramble). Benson CUT.\n"
            "- M3 SLOT: filled by Oliver (narrative milestone elevated to full module, Wisdom/Courage fused domain).\n"
            "- STONES: 6 in MindfulNest structure preserved (5 creature-domain + 1 Wisdom keystone). Wisdom Stone absorbs Courage domain; becomes Willow's/Oliver's shared domain. 'Wisdom Stone cannot be mirrored' rule DELETED — Wisdom Stone mirror is now in the MindfulNest like the others.\n"
            "- WISHING GARDEN: merged as Sweetrose Garden in Arc 3 Foxhollow (see Arc 3 skeleton cascade tag).\n"
            "- DRAGON SYSTEM: ceremony MP4 + Patrol Album flight videos KEPT. Avatar toggle CUT (see ARC_5_DRAGONSHELL_STAYS_V1).\n"
            "- TALK TO PIP: CUT.\n\n"
            "Complements LD-282 CATALOG_DELIVERY_ARC_AT_A_TIME_V1 (same mechanism, 8 arcs). Supersedes any prior 'cut 2 per arc' uniform heuristic. Any arc/module added back to V1 requires unlock LD."
        ),
    },
    {
        "decision_key": "ZONE_COUNT_5_V1",
        "decision_name": "V1 ships 5 fidget zones; Tessa's area = My House decoration space",
        "severity": "MEDIUM", "task_category": "app_architecture", "enforcement_type": "governed_file",
        "decision_text": (
            "V1 ships FIVE fidget zones: Luna Star Window, Benson Bubble Hop (zone name preserved even though creature cut — mechanic assigned to Ember or rebranded pending Kim), Ember Glow Charge, Bork Sound Painting, Bramble Dig & Find. "
            "Tessa's area is My House decoration space (collection/placement surface), NOT a fidget zone. "
            "Deliberate architectural asymmetry. Adding a sixth fidget zone requires an unlock LD.\n\n"
            "OPEN: Bubble Hop zone name review now that Benson is cut — may rename or reassign to Oliver/another creature. See blocker."
        ),
    },
    {
        "decision_key": "PATH_A_TAP_PRIMITIVE_ALL_FIDGETS_V1",
        "decision_name": "Path A tap primitive + content variation + layered rewards unified across all fidget zones",
        "severity": "HIGH", "task_category": "app_architecture", "enforcement_type": "governed_file",
        "decision_text": (
            "All V1 fidget zones use PATH A — unified tap gesture primitive. Differentiation via content variation "
            "(star-to-constellate, bubble-pop, charge, sound-paint, dig-find) and layered rewards. No multi-step "
            "mini-games. No fail states. No tutorials on fidget layer — primitive is self-evident on first tap. "
            "Exception: Bubble Hop uses Matter.js for pop physics (scoped inside zone component only). All other "
            "zones use LD-128 stack (Reanimated + Skia + Lottie). Kids' app retention research confirms tap primitive "
            "+ variable reward + collection loop is sufficient mechanic depth for ages 7-11 (Sago Mini, Toca Life, "
            "Neko Atsume, Mightier all validate). PATH_A_BUILD_PLAN_v1.md is the build reference."
        ),
    },
    {
        "decision_key": "V1_CREATURE_SET_5_OLIVER_AT_M3",
        "decision_name": "V1 = 5 creatures (Benson cut) + Oliver at M3; 6 stones preserved via Wisdom+Courage fusion",
        "severity": "HIGH", "task_category": "app_architecture", "enforcement_type": "governed_file",
        "decision_text": (
            "Benson is CUT from V1. V1 creatures: Tessa, Luna, Ember, Bork, Bramble (5 total). "
            "Arc 1 M3 slot filled by OLIVER — his existing narrative milestone event elevated to full module with "
            "Phase A + Phase B teaching Physiological Sigh. Oliver already has voice profile + stills library per Kim. "
            "RUNESTONE STRUCTURE: 6 stones in MindfulNest preserved (5 domain + 1 Wisdom keystone) — "
            "Wisdom Stone absorbs Courage domain, becomes Willow's/Oliver's shared domain. Courage as distinct domain "
            "deleted; Physiological Sigh technique lives under Wisdom/Willow domain. 'Wisdom Stone cannot be mirrored' "
            "rule DELETED — Wisdom Stone mirror is now in the MindfulNest like the others. Avoids Heartwood visual redesign. "
            "M-numbers per LD-35 remain FIXED (M3 originally Benson, now filled by Oliver). Arc 8 Hopegrove cut. "
            "Wishing Garden merged as Sweetrose Garden in Arc 3 Foxhollow."
        ),
    },
    {
        "decision_key": "WISHING_GARDEN_AS_SWEETROSE_V1",
        "decision_name": "Wishing Garden merged into Arc 3 Foxhollow as Sweetrose Garden (not standalone Arc 8 space)",
        "severity": "MEDIUM", "task_category": "app_architecture", "enforcement_type": "governed_file",
        "decision_text": (
            "Wishing Garden as a standalone Arc 8 Hopegrove mechanic is CUT (Arc 8 cut with Benson). "
            "The Wishing Garden CONCEPT is preserved by merging into Arc 3 Foxhollow's existing Sweetrose Garden — "
            "the luminous living flowers that grow there become the canonical 'wishing garden' surface. "
            "Lightweight delayed-animation on seed placement: KEPT (simple mechanic). "
            "Cedric affirmation lines: DEFERRED (revisit post-launch). Decoration-space function preserved. "
            "See Arc 3 skeleton cascade tag at MILESTONE: ARRIVAL AT FOXHOLLOW."
        ),
    },
    {
        "decision_key": "ARC_5_DRAGONSHELL_STAYS_V1",
        "decision_name": "Arc 5 Dragonshell stays in Arc 5; Dragon avatar toggle CUT; ceremony + patrol album KEPT",
        "severity": "HIGH", "task_category": "app_architecture", "enforcement_type": "governed_file",
        "decision_text": (
            "Dragonshell transformation ceremony stays in Arc 5 (NOT absorbed into Arc 3 — Arc 3 has electric-shockwave "
            "destruction discovery which is load-bearing). Arc 5 ceremony MP4 preserved. Dragon Patrol Album + per-homeland "
            "flight videos preserved (production-cheap, narratively beloved). "
            "CUT: dragon avatar toggle. No `currentForm` state populated at runtime. No dual cosmetic wardrobe. No fire-magic "
            "Magic Tap variant. Child avatar is single-form in V1. "
            "Firestore schema fields (`currentForm`, `dragonUnlocked`, `equippedCosmetics.dragon`, `unlockedFlightVideos`) "
            "RESERVED UNPOPULATED — kept in schema to avoid migration pain if V1.x reintroduces toggle."
        ),
    },
    {
        "decision_key": "MAGIC_TAP_MAP_V1",
        "decision_name": "Map Magic Tap = wand particles + creature reactions + ~5-10% coin / ~0.5% rare item",
        "severity": "MEDIUM", "task_category": "app_architecture", "enforcement_type": "governed_file",
        "decision_text": (
            "Magic Tap on map fires wand particle effect + creature reaction animation on every tap. "
            "Reward probability: ~5-10% coin drop, ~0.5% rare collection item. Tunable via Firestore config doc. "
            "Reward rolls server-side via Cloud Function (LD-164). Sole Magic Tap variant in V1 — dragon fire-magic "
            "variant cut per ARC_5_DRAGONSHELL_STAYS_V1. Contributes to variable-reward retention layer per "
            "RETENTION_LAYER_V1. Neko Atsume pattern."
        ),
    },
    {
        "decision_key": "RETENTION_LAYER_V1",
        "decision_name": "V1 retention = backpack + variable reward + map-visit streak + Today card + weekly drops + Parent Weekly Plan",
        "severity": "HIGH", "task_category": "app_architecture", "enforcement_type": "governed_file",
        "decision_text": (
            "V1 retention has 6 low-coercion mechanisms:\n"
            "(1) Collection — backpack is THE gallery (see BACKPACK_IS_COLLECTION_GALLERY_V1).\n"
            "(2) Variable reward — Magic Tap probabilistic drops + fidget-play proportional coins.\n"
            "(3) Streak — fires on MAP VISIT, not module completion (anti-pattern protection per V1_ANTI_PATTERNS_LOCKED).\n"
            "(4) Today card — on app open, Chipper surfaces one curated suggestion from content pool.\n"
            "(5) Weekly content drops post-launch (new items, new dialogue, seasonal elements).\n"
            "(6) Parent Weekly Plan — 26-week calendar with 2 modules/week target + 5-min daily together-practice.\n\n"
            "No push notifications in V1. Retention threads AROUND therapeutic content, never gamifies it. "
            "Research backing: Duolingo 3.6x retention from 7-day streak; Neko Atsume variable-reward; Toca Life "
            "weekly drops; Mightier collection-layer-over-therapy validated clinically."
        ),
    },
    {
        "decision_key": "BACKPACK_IS_COLLECTION_GALLERY_V1",
        "decision_name": "Backpack = unified collection gallery; no separate creatures-met UI",
        "severity": "MEDIUM", "task_category": "app_architecture", "enforcement_type": "governed_file",
        "decision_text": (
            "Backpack screen serves as THE V1 collection gallery: runestones earned, fidget-zone collectibles, "
            "Magic Tap rare items, creature-met tokens (as items, not a screen), decoration unlocks for My House / "
            "Carriage / Sweetrose Garden. NO separate 'creatures met' UI. NO separate 'items earned' screen. "
            "NO collectibles sidebar. Complements LD-316 backpack reveal animation (open blocker). "
            "Rationale: single collection surface = lower production cost + lower child cognitive load + prevents "
            "reward-surface dilution across multiple screens."
        ),
    },
    {
        "decision_key": "FIDGET_PLAY_REWARD_V1",
        "decision_name": "Fidget play = coins proportional to interaction + occasional rare items",
        "severity": "LOW", "task_category": "app_architecture", "enforcement_type": "governed_file",
        "decision_text": (
            "Fidget zones produce coins proportional to interaction (tuning ~1 coin per 5 taps, TBD via beta) "
            "plus occasional rare items (rate ~2-5% of play sessions, comparable to Magic Tap rare rate). "
            "No fail states. No score displays (anti-pattern protection per V1_ANTI_PATTERNS_LOCKED). "
            "Coins fund decoration unlocks in My House / Carriage / Sweetrose Garden + Mountain Store purchases."
        ),
    },
    {
        "decision_key": "DECORATION_SURFACES_V1",
        "decision_name": "3 decoration surfaces V1: My House + Carriage + Sweetrose Garden (Arc 3)",
        "severity": "LOW", "task_category": "app_architecture", "enforcement_type": "governed_file",
        "decision_text": (
            "V1 decoration surfaces:\n"
            "(1) MY HOUSE — Tessa's pond cottage area, Day 1, decoration slots TBD.\n"
            "(2) CARRIAGE — unlocked at Arc 4 Willow rescue completion, 2-3 slots.\n"
            "(3) SWEETROSE GARDEN — merged into Arc 3 Foxhollow (absorbs former Wishing Garden concept). Lightweight "
            "delayed-animation on seed placement. Cedric affirmation lines deferred post-launch.\n\n"
            "All three surfaces share the backpack collection per BACKPACK_IS_COLLECTION_GALLERY_V1 — items earned "
            "can be placed in any surface, moved freely between surfaces."
        ),
    },
    {
        "decision_key": "V1_TECH_STACK_CONFIRMED_20260420",
        "decision_name": "V1 stack — LD-128 confirmed sufficient + Matter.js for Bubble Hop only",
        "severity": "MEDIUM", "task_category": "app_architecture", "enforcement_type": "governed_file",
        "decision_text": (
            "2026-04-20 scope-condensation session re-validated LD-128 ANIMATION_STACK_V1_PATH_D_v2: "
            "Reanimated + Skia + Lottie + gesture-handler + expo-haptics + expo-audio is sufficient for all V1 "
            "interactive surfaces under the condensed scope. Only addition: Matter.js SCOPED TO Bubble Hop zone "
            "component for bubble physics (pure JS, no native module, ~80KB). Not added to general stack. "
            "No new global animation lock needed.\n\n"
            "Reference implementations to study pre-build: enzomanuelmangano/demos Particle Button + Expo's "
            "Matter.js + Skia tutorial. See PATH_A_BUILD_PLAN_v1.md."
        ),
    },
    {
        "decision_key": "V1_ANTI_PATTERNS_LOCKED_20260420",
        "decision_name": "V1 anti-patterns — no fail states, no module streaks, no pet decay, no aggressive monetization",
        "severity": "HIGH", "task_category": "app_architecture", "enforcement_type": "governed_file",
        "decision_text": (
            "Locked V1 anti-patterns (require explicit unlock LD to introduce):\n"
            "(1) No fail states anywhere — fidget zones, modules, Magic Tap all succeed-only.\n"
            "(2) No tutorials on fidget layer — tap primitives self-evident.\n"
            "(3) No pet-care decay — creatures do not get sad/hungry/anxious if child doesn't visit.\n"
            "(4) No points/scores on therapy content — Phase A/B produce no numeric scores, no star ratings, no completion %.\n"
            "(5) No multi-step fidget mini-games — Path A primitive per PATH_A_TAP_PRIMITIVE_ALL_FIDGETS_V1 is one-step.\n"
            "(6) No aggressive monetization — no paywalls on therapeutic content, no ads, no limited-time FOMO.\n"
            "(7) No streak on modules — streak is map-visit-only per RETENTION_LAYER_V1.\n"
            "(8) No voice substitution — Cedric is Cedric, Chipper is Chipper; runtime TTS substitution already forbidden by LD-281.\n"
            "(9) No session replay of kid-facing screens (COPPA landmine per Services Landscape Agent 4 scan).\n"
            "(10) No ads/attribution SDKs in child app (AppsFlyer, Adjust, Branch, Kidoz, SuperAwesome AwesomeAds, AdMob).\n"
            "(11) No dragon avatar toggle (per ARC_5_DRAGONSHELL_STAYS_V1 — ceremony + patrol album kept, toggle cut).\n"
            "(12) No Talk-to-Pip chat screen (cut per V1_SCOPE_CONDENSED_20260420).\n\n"
            "These prevent re-litigation per session and protect clinical integrity from game-mechanic creep."
        ),
    },
    {
        "decision_key": "PRE_LAUNCH_SERVICES_V1",
        "decision_name": "Pre-launch services — Sentry, App Check, Crashlytics, Billing Alerts, EAS, App Distribution, BrowserStack, iPad 9",
        "severity": "HIGH", "task_category": "infrastructure", "enforcement_type": "governed_file",
        "decision_text": (
            "V1 pre-launch services confirmed via Services Landscape scan 2026-04-20:\n\n"
            "SHIP BLOCKERS (must integrate before V1):\n"
            "- Sentry (React Native + Expo) — crash/error reporting, free tier\n"
            "- Firebase App Check with `enforceAppCheck: true` on all Cloud Functions — abuse protection, free\n"
            "- Firebase Crashlytics — native crash reporting, free\n"
            "- Firebase Billing Alerts — cost-runaway protection, free\n\n"
            "STRONGLY RECOMMENDED (pre-launch beta):\n"
            "- EAS Starter ($19/mo) — build pipeline when free tier's 15 iOS builds/mo gets tight\n"
            "- Firebase App Distribution — free internal rings pre-TestFlight\n"
            "- BrowserStack App Live ($29/mo) — belt-and-suspenders iPad 9 access\n"
            "- Physical refurbished iPad 9 ($180-230 one-time) — LD-287 device-floor testing\n\n"
            "COPPA landmines avoided: LogRocket/FullStory/Sentry Session Replay skipped on child surfaces; "
            "Mixpanel/Amplitude skipped on child app (Firebase Analytics COPPA-mode default); "
            "AppsFlyer/Adjust/Branch attribution SDKs skipped entirely."
        ),
    },
    {
        "decision_key": "ASSET_SOURCES_LOCKED_V1",
        "decision_name": "V1 asset sources — Itch.io watercolor, Spitfire LABS, Sonniss GDC, FLUX.2, Wan-Alpha, Hailuo",
        "severity": "LOW", "task_category": "production", "enforcement_type": "governed_file",
        "decision_text": (
            "V1 asset sources locked 2026-04-20:\n\n"
            "FIDGET ZONE BACKDROPS: Itch.io watercolor packs (~$50 total for 5 zones, specific packs TBD per blocker).\n"
            "FIDGET UI ANIMATIONS: LottieFiles free + marketplace (Constellations, Spark, Treasure Chest, water ripple, digging).\n"
            "FIDGET PARTICLES: Kenney CC0 Particle Pack + OpenGameArt CC0 Watercolor Textures + Skia SKSL shaders ported from ShaderToy.\n"
            "FIDGET AUDIO: Sonniss GDC bundle (free annual), Zapsplat Premium ($7.50/mo for 1-2 month sprint sub), ElevenLabs SFX (existing sub), Spitfire LABS Hand Bells (free VSTs) for Bork pentatonic tones.\n"
            "AMBIENT MUSIC: Suno Pro ($10/mo existing sub) for zone ambient beds. Artlist ($21/mo for 1-2 months) optional for perpetual-license extras.\n\n"
            "CHARACTER ANIMATION: existing FLUX Kontext Pro → Kling v3.0 Pro pipeline maintained. Upgrade to FLUX.2 Pro/Max when available (10-ref support vs Kontext's 4). Evaluate Hailuo 2.3 Fast on WaveSpeed (55% cheaper than Kling, same WaveSpeed account). Evaluate Wan-Alpha on fal.ai if transparent-alpha character loops become needed ($0.04/sec RGBA video — CVPR 2026). Character LoRA training via fal.ai FLUX LoRA Fast Training for 7 creatures (~$50-100 one-time).\n\n"
            "CHARACTER VOICES: ElevenLabs eleven_v3 (existing sub). No runtime TTS per LD-281.\n\n"
            "All royalty-free for commercial use under respective licenses — verify per-asset license before ship. Does NOT replace custom-produced character voices."
        ),
    },
]

# ============================================================================
# AMENDs to existing LDs (6)
# ============================================================================

AMENDS = [
    {
        "decision_key": "ANIMATION_STACK_V1_PATH_D_v2",
        "append_note": (
            "\n\n--- AMENDMENT 2026-04-20 (V1 Scope Condensation) ---\n"
            "Re-validated during V1 scope-condensation session. Stack confirmed SUFFICIENT for all Path A fidget "
            "zones. Matter.js added ONLY inside Benson Bubble Hop component scope per V1_TECH_STACK_CONFIRMED_20260420. "
            "No other stack additions. No new global animation lock needed."
        ),
    },
    {
        "decision_key": "MODULE_FLOW_7_SCREENS",
        "append_note": (
            "\n\n--- AMENDMENT 2026-04-20 (V1 Scope Condensation) ---\n"
            "7-screen module flow unchanged. V1 scope reduction to 8 arcs × ~6 modules = ~48 modules does not change "
            "per-module flow structure. Dragon avatar toggle is CUT from V1 per ARC_5_DRAGONSHELL_STAYS_V1 — ceremony "
            "+ patrol album kept. Talk to Pip screen CUT. Wishing Garden merged into Arc 3 Sweetrose Garden per "
            "WISHING_GARDEN_AS_SWEETROSE_V1."
        ),
    },
    {
        "decision_key": "CATALOG_DELIVERY_ARC_AT_A_TIME_V1",
        "append_note": (
            "\n\n--- AMENDMENT 2026-04-20 (V1 Scope Condensation) ---\n"
            "V1 arc count is 8 (Arc 8 Hopegrove / Benson cut per V1_CREATURE_SET_5_OLIVER_AT_M3). "
            "Arc-at-a-time delivery mechanism unchanged — same mechanism applies to 8 arcs instead of 9. "
            "Post-launch arcs may re-expand the catalog; V1 ship = 8 arcs."
        ),
    },
    {
        "decision_key": "MODULE_EXIT_AND_PROGRESSION_V1",
        "append_note": (
            "\n\n--- AMENDMENT 2026-04-20 (V1 Scope Condensation) ---\n"
            "Exit/progression mechanism unchanged. Reward section routes to backpack per "
            "BACKPACK_IS_COLLECTION_GALLERY_V1 (no separate creatures-met UI). Backpack reveal animation "
            "remains open blocker (pre-existing LD-316 Layer 1 open items + new V1 blockers)."
        ),
    },
    {
        "decision_key": "IPAD_9_MEMORY_BENCHMARK_REQUIRED_V1",
        "append_note": (
            "\n\n--- AMENDMENT 2026-04-20 (V1 Scope Condensation) ---\n"
            "Still active. Kim to procure physical refurbished iPad 9 (~$180-230) per PRE_LAUNCH_SERVICES_V1. "
            "Benchmark sign-off requires physical-device run on the LD-287 lowest-supported target."
        ),
    },
    {
        "decision_key": "m_numbers_fixed_to_creatures",
        "append_note": (
            "\n\n--- AMENDMENT 2026-04-20 (V1 Scope Condensation) ---\n"
            "M-number mapping UNCHANGED — permanently fixed per original lock. V1 scope does NOT ship M3 as Benson; "
            "M3 slot filled by OLIVER per V1_CREATURE_SET_5_OLIVER_AT_M3 (Oliver's narrative milestone elevated to "
            "full module teaching Physiological Sigh under Wisdom/Willow fused domain). If Benson returns post-launch, "
            "M3=Benson is preserved as the original mapping. SCOPE change, not mapping change."
        ),
    },
]


# ============================================================================
# NEW blockers (18)
# ============================================================================

NEW_BLOCKERS = [
    {"title": "Kim beta-tests Bubble Hop with 5-10 kids after Phase 1 (Path A validation gate)",
     "severity": "medium", "description": "[V1-SC-01] Validation gate for Path A tap primitive. Bubble Hop is first-built zone with Matter.js; highest-risk for 'does the primitive actually work with kids.' Retention metric: ≥50% next-day return."},
    {"title": "Rebrand Bubble Hop zone (Benson cut — reassign mechanic or rename)",
     "severity": "low", "description": "[V1-SC-02] Bubble Hop zone name references Benson. With Benson cut, zone needs rebrand OR reassign to another creature. Mechanic (tap bubbles to pop) still valid."},
    {"title": "Redesign MindfulNest runestone structure: merge Wisdom+Courage into single Wisdom Stone domain",
     "severity": "high", "description": "[V1-SC-03] Architectural; downstream doc cascade: Bible, NDU, CDM, Technique Inventory, Arc Production Bible, skill governance files. Wisdom Stone absorbs Courage. 'Wisdom Stone cannot be mirrored' rule DELETED. Use cross-document-update skill."},
    {"title": "Draft 26-week Parent Weekly Plan template (2 modules/week + 5-min daily together-practice)",
     "severity": "medium", "description": "[V1-SC-04] Parent buy-in retention mechanism per RETENTION_LAYER_V1. Kim-authored content."},
    {"title": "Cascade Benson-cut across Arc Production Bible, arc skeletons (remaining), NDU, Bible, Technique Inventory",
     "severity": "high", "description": "[V1-SC-05] Doc cascade. Arc skeletons 1-3 already have cascade tags [V1 CASCADE TAG 2026-04-20]. Remaining: Bible v13_12, NDU v2_9, CDM v1_14, Technique Inventory v1_16 via subagent."},
    {"title": "Cascade Dragon avatar toggle cut across app architecture + gameplay specs",
     "severity": "medium", "description": "[V1-SC-06] Remove currentForm references from gameplay + architecture docs. Schema fields stay reserved (unpopulated) to avoid V1.x migration pain."},
    {"title": "Procure physical refurbished iPad 9 (~$180-230) for device-floor testing",
     "severity": "medium", "description": "[V1-SC-07] Unblocks LD-287 IPAD_9_MEMORY_BENCHMARK_REQUIRED_V1 sign-off."},
    {"title": "Select specific Itch.io watercolor backdrop packs for 5 fidget zones + verify commercial licenses",
     "severity": "low", "description": "[V1-SC-08] Unblocks ASSET_SOURCES_LOCKED_V1 production pipeline. Target ~$50 total."},
    {"title": "Build Reward section UI (stock-RN post-module onEnd)",
     "severity": "high", "description": "[V1-SC-09] Open from LD-316 Layer 1. Coin-burst animation + decoration drop into backpack."},
    {"title": "Build backpack-reveal animation for new items",
     "severity": "medium", "description": "[V1-SC-10] Open from LD-316 Layer 1. Sole collection-surface animation per BACKPACK_IS_COLLECTION_GALLERY_V1."},
    {"title": "Wire Magic Tap probabilistic reward drop (5-10% coin, 0.5% rare item)",
     "severity": "medium", "description": "[V1-SC-11] Implementation blocker for MAGIC_TAP_MAP_V1. Cloud Function-mediated rolls per LD-164."},
    {"title": "Wire fidget-play proportional coin accrual + rare-item probability per zone",
     "severity": "medium", "description": "[V1-SC-12] Implementation blocker for FIDGET_PLAY_REWARD_V1."},
    {"title": "Wire map-visit streak counter (NOT module completion streak)",
     "severity": "medium", "description": "[V1-SC-13] Implementation blocker for RETENTION_LAYER_V1 mechanism 3."},
    {"title": "Build Today card Chipper-suggestion surface on app open",
     "severity": "medium", "description": "[V1-SC-14] Implementation blocker for RETENTION_LAYER_V1 mechanism 4. Content pool + date-hash selector."},
    {"title": "Scaffold content pipeline for post-launch weekly drops (Directus admin UI for scheduling)",
     "severity": "low", "description": "[V1-SC-15] RETENTION_LAYER_V1 mechanism 5. Scaffolding before launch even if drops themselves post-launch."},
    {"title": "Adopt Sentry + Firebase App Check (enforceAppCheck=true) + Crashlytics + Billing Alerts",
     "severity": "high", "description": "[V1-SC-16] SHIP-BLOCKER services from PRE_LAUNCH_SERVICES_V1."},
    {"title": "Adopt EAS Starter ($19/mo) + Firebase App Distribution + BrowserStack App Live ($29/mo)",
     "severity": "medium", "description": "[V1-SC-17] Pre-launch recommended services from PRE_LAUNCH_SERVICES_V1."},
    {"title": "Design Oliver's M3 module (Physiological Sigh teaching; Wisdom/Willow domain)",
     "severity": "high", "description": "[V1-SC-18] Oliver's narrative event elevated to full module replacing Benson's M3 slot per V1_CREATURE_SET_5_OLIVER_AT_M3. Oliver has existing voice profile + stills library. Phase A demo + Phase B meditation script needed. Kim-authored clinical content."},
]


# ============================================================================
# Writers
# ============================================================================

def write_ld(token, ld, dry):
    key = ld["decision_key"]
    existing = find_by(token, "prod_locked_decisions", "decision_key", key)
    if existing:
        return f"SKIP-EXISTS id={existing[0]['id']}"
    body = dict(ld)
    body["source_document"] = "V1_SCOPE_CONDENSATION_SESSION_20260420"
    body["date_locked"] = SESSION_DATE
    body["status"] = "active"
    body["is_current"] = True
    if dry:
        return "DRY-RUN CREATE"
    resp = _req("POST", "/items/prod_locked_decisions", token=token, body=body)
    return f"CREATED id={resp['data']['id']}"


def amend_ld(token, amend, dry):
    key = amend["decision_key"]
    rows = find_by(token, "prod_locked_decisions", "decision_key", key, select="id,decision_key,decision_text")
    if not rows:
        return f"MISS ({key} not found)"
    row = rows[0]
    cur = row.get("decision_text") or ""
    if amend["append_note"].strip()[:60] in cur:
        return f"SKIP-APPLIED id={row['id']}"
    new_text = cur + amend["append_note"]
    if dry:
        return f"DRY-RUN PATCH id={row['id']}"
    _req("PATCH", f"/items/prod_locked_decisions/{row['id']}", token=token,
         body={"decision_text": new_text})
    return f"PATCHED id={row['id']}"


def write_blocker(token, blk, dry):
    existing = find_by(token, "prod_blockers", "title", blk["title"], select="id,title")
    if existing:
        return f"SKIP-EXISTS id={existing[0]['id']}"
    body = {
        "title": blk["title"],
        "severity": blk["severity"],
        "description": blk["description"],
        "is_resolved": False,
        "module_id": None,
    }
    if dry:
        return "DRY-RUN CREATE"
    resp = _req("POST", "/items/prod_blockers", token=token, body=body)
    return f"CREATED id={resp['data']['id']}"


def write_activity(token, action, details, dry):
    if dry:
        return "DRY-RUN"
    _req("POST", "/items/prod_activity_log", token=token,
         body={"action": action, "module_id": None, "details": details})
    return "LOGGED"


# ============================================================================
# Main
# ============================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = ap.parse_args()

    print(f"[{datetime.now(timezone.utc).isoformat()}] V1 SCOPE CONDENSATION WRITER (dry_run={args.dry_run})")
    token = auth()
    print("AUTH OK")

    # Schema introspection
    print("\n--- Schema introspection ---")
    for coll in ["prod_locked_decisions", "prod_blockers", "prod_activity_log"]:
        f = fields(token, coll)
        print(f"  {coll}: {len(f)} fields")

    # LDs
    print(f"\n--- Writing {len(NEW_LDS)} new LDs ---")
    ld_results = []
    for ld in NEW_LDS:
        status = write_ld(token, ld, args.dry_run)
        print(f"  [{ld['decision_key']:50s}] {status}")
        ld_results.append((ld["decision_key"], status))

    # AMENDs
    print(f"\n--- Amending {len(AMENDS)} existing LDs ---")
    amend_results = []
    for amend in AMENDS:
        status = amend_ld(token, amend, args.dry_run)
        print(f"  [{amend['decision_key']:45s}] {status}")
        amend_results.append((amend["decision_key"], status))

    # Blockers
    print(f"\n--- Writing {len(NEW_BLOCKERS)} new blockers ---")
    blk_results = []
    for blk in NEW_BLOCKERS:
        status = write_blocker(token, blk, args.dry_run)
        print(f"  [{blk['title'][:60]:60s}] {status}")
        blk_results.append((blk["title"], status))

    # Activity log (one summary row)
    if not args.dry_run:
        write_activity(token, "v1_scope_condensation_sweep_complete",
                       {"task_id": TASK_ID, "preflight_id": PREFLIGHT_ID,
                        "lds_created": sum(1 for _, s in ld_results if "CREATED" in s),
                        "lds_skipped": sum(1 for _, s in ld_results if "SKIP" in s),
                        "lds_amended": sum(1 for _, s in amend_results if "PATCHED" in s),
                        "blockers_created": sum(1 for _, s in blk_results if "CREATED" in s),
                        "blockers_skipped": sum(1 for _, s in blk_results if "SKIP" in s)},
                       args.dry_run)

    # Summary
    print("\n=== SUMMARY ===")
    print(f"  LDs  — CREATED: {sum(1 for _, s in ld_results if 'CREATED' in s)}, "
          f"SKIP-EXISTS: {sum(1 for _, s in ld_results if 'SKIP-EXISTS' in s)}, "
          f"DRY: {sum(1 for _, s in ld_results if 'DRY' in s)}")
    print(f"  AMENDs — PATCHED: {sum(1 for _, s in amend_results if 'PATCHED' in s)}, "
          f"MISS: {sum(1 for _, s in amend_results if 'MISS' in s)}, "
          f"SKIP-APPLIED: {sum(1 for _, s in amend_results if 'SKIP-APPLIED' in s)}, "
          f"DRY: {sum(1 for _, s in amend_results if 'DRY' in s)}")
    print(f"  BLOCKERS — CREATED: {sum(1 for _, s in blk_results if 'CREATED' in s)}, "
          f"SKIP-EXISTS: {sum(1 for _, s in blk_results if 'SKIP-EXISTS' in s)}, "
          f"DRY: {sum(1 for _, s in blk_results if 'DRY' in s)}")
    print(f"  Mode: {'DRY-RUN (no writes)' if args.dry_run else 'LIVE (writes committed)'}")
    print(f"  Preflight: {PREFLIGHT_ID}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
