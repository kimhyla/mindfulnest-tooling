# Audio Stripping: Pragmatic Implementation Recommendation

**Executive Summary**

Implement **Layers 1 + 3 only**. Skip Layer 2. Consider Layer 4 later.

Why: Layers 1 and 3 form an airtight defense with minimal operational overhead. Layer 2 is overkill (if Layer 1 works, Layer 2 never triggers). Layer 4 is valuable for forensics but not operationally critical.

---

## The Recommendation Matrix

| Layer | Implement? | Why | Cost | Effort |
|-------|-----------|-----|------|--------|
| **L1: Download Strip** | **YES** | Primary defense. Silent failures possible. Catches problem earliest. | ~500ms/clip (bg thread) | 30min |
| **L2: Serve Validate** | **NO** | Redundant with L1. If L1 works, L2 never triggers. Adds latency to every serve request. | ~500ms/request | 10min |
| **L3: Build Audit** | **YES** | Last gate before storyboard finalized. Kim's decision point. Value-add: asks her to choose. | ~500ms × M clips | 20min |
| **L4: Export Audit** | **LATER** | Forensics only. Valuable for accountability but not operationally critical. | ~500ms × M clips | 15min |

**Total investment for MVP (L1+L3): ~50 minutes. One afternoon.**

---

## Why Skip Layer 2?

**The case for Layer 2:**
- "What if ffmpeg silently fails?"
- "What if Kim manually copies a clip?"
- "Defense-in-depth sounds good"

**The case against Layer 2:**
- If ffmpeg fails, Layer 1 detects it immediately (we run ffprobe AFTER strip). Clip is rejected, retry triggered. **Layer 1 is self-verifying.**
- If Kim manually copies a clip with audio, Layer 3 (build) catches it. **Layer 3 is the gate.**
- Layer 2 adds 500ms latency to EVERY clip request from the browser during storyboard authoring (playback/scrubbing). That's annoying. Many requests per beat.
- Layer 2 never actually *blocks* anything — it just logs warnings. If we're not blocking, Layer 3 is the real control point.
- Layer 2 is security theater: it doesn't prevent the problem, just detects it after the fact (and only logs).

**The verdict:** Layer 2 is defensive but inefficient. The other three layers (especially L1 and L3) already provide complete coverage without the latency penalty.

**When to reconsider:** Only if you discover Layer 1's ffmpeg strip is failing silently. Then Layer 2 becomes essential as an early warning.

---

## Why Layer 1 is Sufficient for "Didn't Fail Silently"

Layer 1 has internal verification:

```python
# Layer 1 flow:
1. ffmpeg -an -c copy (strip audio)          <-- 200ms
2. ffprobe the result                         <-- 300ms
3. If audio_count > 0: REJECT clip            <-- Blocker
4. If ffprobe fails: REJECT clip              <-- Blocker
5. If audio_count == 0: Mark as complete      <-- Safe
```

The ffprobe check in step 2 is non-negotiable. We don't just blindly trust ffmpeg's success code; we verify the output.

**Failure modes Layer 1 catches:**
- ffmpeg silent fail (audio not stripped) → ffprobe detects → reject
- ffmpeg file corruption (container broken) → ffprobe fails → reject
- Incorrect ffmpeg flags (unlikely) → ffprobe detects → reject
- Disk space exhaustion → ffmpeg fails → reject

**Layer 1 cannot miss audio in the output.** It literally validates the output before committing it to state.

---

## Why Layer 3 is Non-Negotiable

Layer 3 (build audit) is where Kim makes her final selection and we're about to render the storyboard HTML. It's the quality gate.

**Two scenarios:**

**Scenario A: Layer 1 worked (likely)**
- All clips in `animation_clips/` have zero audio
- Layer 3 runs, validates all N selected clips → all pass → Layer 3 is silent, build proceeds
- Cost: ~500ms × N (one-time per module)
- No friction for Kim

**Scenario B: Audio present at Layer 3 (rare)**
- Layer 1 failed (or Kim manually copied a clip)
- Layer 3 detects it
- Layer 3 asks Kim: "I found audio in [list]. Do you want to re-do animation or proceed?"
- Kim decides
- This is good UX: she's informed, she chooses

**Why it's valuable:**
- Catches edge cases (manual file copy, Layer 1 failure)
- Gives Kim control: she knows about the problem and chooses
- Happens once per module, non-recurring cost
- Better to ask her at build-time than to discover audio at listen-through

---

## Why Layer 4 Can Wait

Layer 4 (export audit) is forensics and accountability.

**Value:**
- Logs "at export time, all selected clips were validated"
- Provides audit trail for debugging
- Can trigger optional email notification to Kim

**Why it can wait:**
- If Layer 3 passed, all clips are already validated
- Export is the final step; unlikely new audio would appear between Layer 3 (build) and Layer 4 (export)
- Logging layer 4 results is nice-to-have, not must-have
- Can be added after L1+L3 are working and tested

**Implement Layer 4 when:**
- L1+L3 are stable and tested (1-2 weeks)
- You have bandwidth
- You want comprehensive audit trail for all modules

---

## Implementation Sequence

### Week 1: Layers 1 + 3 (MVP)

**Monday:**
1. Add `from Production.validators.audio_stripping import AudioStripLayer` to production_server.py
2. Integrate Layer 1 download strip in PollingThread._poll_one()
3. Add Layer 1 tests (create test clip with audio, verify strip)
4. Run `production_server.py --smoke-test`
5. Deploy to staging

**Tuesday:**
1. Integrate Layer 3 build audit in storyboard_producer.py (or equivalent)
2. Add Layer 3 tests (validate batch of clips with/without audio)
3. Run end-to-end test: download clips → build storyboard → verify audit
4. Deploy to staging

**Wednesday:**
- Monitor: Are clips being stripped correctly? Are Layer 3 audits passing?
- Adjust as needed

**By end of week:** MVP (L1+L3) is live and tested.

### Week 2: Layer 4 (Forensics)

1. Integrate Layer 4 export audit in production_server.py._handle_export()
2. Connect Directus logging (log results for every export)
3. Test: Export selections, verify audit log in Directus
4. Deploy

### Backlog: Layer 2 (Optional)

Only implement if you discover Layer 1 is failing and want early warning. Otherwise, leave it out.

---

## Cost-Benefit Analysis

### Layer 1: Download Strip
- **Cost:** ~500ms per clip (background thread, doesn't block)
- **Benefit:** Prevents audio from entering animation_clips/ in the first place
- **Risk of skipping:** Audio clips reach Kim; might ship with lip-sync
- **Verdict:** MANDATORY

### Layer 3: Build Audit
- **Cost:** ~500ms × M selected clips (one-time, blocking but brief)
- **Benefit:** Last gate before storyboard HTML finalized; gives Kim control
- **Risk of skipping:** Audio reaches storyboard; Kim discovers it at listen-through
- **Verdict:** MANDATORY (UX is worth the brief latency)

### Layer 2: Serve Validate
- **Cost:** ~500ms per clip request (added to every playback request)
- **Benefit:** Would catch Layer 1 failures, but Layer 1 is self-verifying
- **Risk of skipping:** Layer 1 failure goes undetected at serve-time (but Layer 3 catches it)
- **Verdict:** SKIP (redundant; adds latency)

### Layer 4: Export Audit
- **Cost:** ~500ms × M selected clips (one-time, non-blocking)
- **Benefit:** Forensics, accountability, audit trail
- **Risk of skipping:** No log record of export validation
- **Verdict:** IMPLEMENT LATER (valuable but not critical)

---

## Threat Model

**Threat 1: Animation model returns clip with audio**
- Layer 1: Detects and strips ✓
- Layer 3: Detects if strip failed ✓
- Outcome: Safe

**Threat 2: ffmpeg silent failure (strip succeeds but audio remains)**
- Layer 1: ffprobe check detects ✓
- Outcome: Safe

**Threat 3: Kim manually copies clip with audio into animation_clips/**
- Layer 3: Detects at build time ✓
- Outcome: Safe (asks Kim)

**Threat 4: Directus/database corruption (clips registered as "audio-free" but aren't)**
- All layers run ffprobe on actual files; not dependent on DB state
- Outcome: Safe (ffprobe is the source of truth)

**Threat 5: ffprobe is buggy and misses audio**
- This would require ffprobe to be broken — extremely unlikely
- Fallback: Lip-sync caught at listen-through, re-do animation
- Outcome: Acceptable risk

---

## Cutover Plan

### Before Going Live

1. **Test all three layers (L1, L3, ±L4) against test clips with audio**
   - Create test clip with known audio: `ffmpeg -f lavfi -i testsrc=s=640x480:d=1 -f lavfi -i sine=f=1000:d=1 test_with_audio.mp4`
   - Verify L1 strips it: file should have zero audio after
   - Verify L3 detects it: should ask Kim
   - Verify L4 logs it: should record in Directus

2. **Test normal happy path**
   - Download clips from WaveSpeed
   - L1 strips them
   - L3 validates them
   - Build storyboard
   - Export selections
   - All should be silent and successful

3. **Load testing (optional)**
   - Download 33 clips (Arc 1 event, 3 options each)
   - Verify L1 strips in parallel without slowing down pollinig
   - Verify L3 batch-validates all 6-11 selected clips in <3 seconds

### Deployment

1. **Canary:** Run L1+L3 on staging environment for 1 module
2. **Rollout:** Enable for all modules
3. **Monitoring:** Log all Layer 1 and Layer 3 results to Directus; review daily for first week
4. **Fallback:** If issues arise, `SKIP_AUDIO_VALIDATION=true` disables all layers

---

## Frequently Asked Questions

**Q: What if ffmpeg is not installed?**
A: Layer 1 will fail on first strip attempt. Error will be logged. Clip will be rejected. Retry logic will kick in. Eventually: operator needs to install ffmpeg. Fail fast and clear.

**Q: What if ffmpeg is slow?**
A: ~500ms per clip is acceptable for background download processing. If you see slowdown: check system load, consider parallelizing ffmpeg calls.

**Q: What if Kim gets frustrated by Layer 3 blocks?**
A: Make the UX clear: show her exactly which clips have audio, why (brief explanation), and ask her to choose. Most of the time, Layer 3 is silent (all clips clean). When it does block, it's for a good reason.

**Q: Do we need both L1 and L3?**
A: Yes. L1 is the primary defense (prevent audio from entering the system). L3 is the last gate (ensure nothing slips through). Together they form airtight coverage.

**Q: Can we skip L1 and just rely on L3?**
A: No. If you skip L1, audio-containing clips reach `animation_clips/`. Then L3 catches them and asks Kim to retry animation. This is much slower (re-render from WaveSpeed = 20+ minutes per beat). Better to catch at L1 and retry immediately.

**Q: Should we implement all 4 layers?**
A: L1+L3 are essential. L2 is redundant. L4 is valuable for forensics but can be added later. Recommended: L1+L3 now, L4 in week 2, L2 never (unless you discover L1 is failing).

---

## Version History

| Version | Date | Status | Notes |
|---------|------|--------|-------|
| v1 | 2026-04-15 | Final | Recommends L1+L3, skip L2, defer L4 |

