# Voice Interface Decision Matrix — Quick Reference

## One-Sentence Verdict
**Phone-based voice (Twilio + ElevenLabs) for MVP. Alexa post-MVP if smart home adoption >30%. Skip Google, Apple, pure smart home for now.**

---

## Platform Scorecard

| Criterion | Phone Voice | Alexa | Google Home | Apple Siri | Notes |
|-----------|---|---|---|---|---|
| **Time to MVP** | 6-8 weeks | 10-12 weeks | ❌ Dead | ❌ Delayed | Alexa adds cert cycle |
| **Dev complexity** | Medium | High | — | — | Alexa needs intent model |
| **Cost per call** | $0.12/min | $0.15/min | — | — | Phone is cheapest |
| **COPPA risk** | Low | Medium | — | — | Alexa always-listening is concern |
| **HIPAA risk** | Low | Medium | — | — | Phone is point-to-point |
| **Context injection** | Direct | Via AWS API | — | — | Phone wins; no translation layer |
| **Crisis escalation** | Native 988 | Clunky | — | — | Phone can transfer calls |
| **Parent friction** | Minimal | Medium | — | — | Alexa requires device + skill enable |
| **Smart home req?** | None | Echo device required | — | — | Phone: any phone works |
| **Certification** | None | 4-6 weeks | — | — | Phone wins; no external approval |
| **Therapist control** | Full | Limited | — | — | Phone is backend-driven |

---

## Cost Comparison (per 1000 parents, 2 calls/mo, 10 min each)

| Platform | Annual Cost | Per-Parent/Year | Per-Call | Includes |
|----------|---|---|---|---|
| **Phone Voice** | $21,140 | $21.14 | $1.05 | Twilio + Whisper + Claude + ElevenLabs |
| **Alexa** | $28,000 | $28 | $1.40 | Alexa cert + Lambda + ElevenLabs + operational overhead |
| **vs. Live Therapist** | $600,000+ | $600+ | $50-100 | On-call therapist salary / fees |

---

## Timeline

### MVP (Phone Voice)
```
NOW ─ Week 1-2: Twilio + backend integration
     ─ Week 3-5: Claude + context injection
     ─ Week 6-7: ElevenLabs + crisis escalation
     ─ Week 8:   Testing + launch
```
**Time to first call: 8 weeks**

### Post-MVP (Alexa, if justified)
```
Month 4:  Analyze smart home adoption in user base
Month 5:  Decision: Continue?
Month 5-6: Development (if yes)
Month 7-9: Alexa certification cycle
Month 10: Launch
```
**Alexa launch: 10 months from today**

---

## Decision Tree: Should We Build Alexa?

```
Q1: Do >30% of your parents own Echo devices?
  NO → Skip Alexa. Use phone voice only.
  YES → Continue to Q2

Q2: Can your ops team handle Alexa certification + ongoing compliance?
  NO → Skip. Phone voice is simpler.
  YES → Continue to Q3

Q3: Have you validated product-market fit with phone voice?
  NO → Do phone voice MVP first. Revisit post-launch.
  YES → Proceed to Alexa integration in Month 5+

OUTCOME:
  ✓ Add Alexa as secondary channel (many users will continue using phone)
  ✗ Skip Alexa; double down on phone experience
```

---

## Why NOT Those Platforms

| Platform | Status | Reason |
|----------|--------|--------|
| **Google Home** | ❌ SUNSET | Conversational Actions dead (June 2023); Google Assistant being replaced by Gemini; no third-party voice apps supported |
| **Apple Siri** | ⏳ DELAYED | Siri v2.0 delayed to Sept 2026; SiriKit doesn't support custom "coaching" intent; HomePod adoption low among parents of young kids |
| **Purely Smart-Home** | ❌ WRONG MODALITY | Always-listening devices are privacy risk in crisis context; parent already stressed, shouldn't have to remember to enable skill; phone is friction-free |

---

## Architecture One-Liner

```
Parent (in app or calling phone number)
  → Twilio voice call
  → MindfulNest backend (OAuth: parent authenticated)
  → Child profile + therapist notes injected
  → Claude 3.5 Sonnet (inference)
  → ElevenLabs TTS (warm voice)
  → OpenAI Whisper (parent's next response)
  → [Loop] → Until parent says bye or danger detected → 988 transfer
```

**Total latency:** 15-30 seconds per round-trip (acceptable for therapy).
**Cost:** ~$1.05 per 10-minute call.
**COPPA/HIPAA:** Compliant (explicit consent, encrypted storage, auto-deletion).

---

## Top 3 Technical Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **15-30s latency feels slow in crisis** | Parent perceives coach as slow, disengages | Prefetch child profile in app; use Twilio STT for icebreaker (faster); stream Claude response token-by-token |
| **LLM instruction degradation past turn 30** | Coach starts ignoring safety constraints | Cap crisis call at 10 turns max; escalate to 988/therapist if extended support needed; restart fresh session per call |
| **STT fails in noisy environment** (parent in chaotic house) | Can't transcribe parent's speech | Whisper is robust to noise; offer text fallback ("Having trouble hearing? Type instead"); ask for confirmation if confidence <0.7 |

---

## Go/No-Go Checklist for Launch

- [ ] Twilio + ConversationRelay working end-to-end
- [ ] Claude integration tested with 50+ crisis scenarios
- [ ] ElevenLabs voice consistent across calls (test 20+ responses)
- [ ] Whisper + Twilio STT both integrated; can switch mid-call
- [ ] COPPA consent flow: verbal + checkbox on first call
- [ ] 988 escalation tested with live call transfer
- [ ] Therapist escalation tested (on-call transfer)
- [ ] Structured de-escalation (breathing, grounding) tested
- [ ] Encryption at rest verified (AES-256)
- [ ] Auto-deletion scheduled (90-day expiry)
- [ ] HIPAA compliance audit complete
- [ ] Parent privacy notice published + approved
- [ ] Therapist UX: Can therapist view/download transcripts?
- [ ] Crisis logging: Does therapist see escalation flags?
- [ ] Fallback: What if backend is down? (Graceful decline)

---

## Success Metrics (Post-Launch)

| Metric | Target | Reason |
|--------|--------|--------|
| **Adoption** | >5% of active parents use per month | Indicates relevance; establishes demand for Alexa later |
| **Call success rate** | >90% (call completes without error) | Reliability in crisis; <3% error rate is key |
| **Parent satisfaction** | >4/5 stars (post-call survey) | If satisfied, will recommend; sticky feature |
| **Escalation rate** | 2-5% (to 988 or therapist) | Indicates good risk assessment; not over-escalating |
| **Repeats per parent** | 1.5-2x per month (average) | Usage pattern; sustains economics |
| **Cost per call** | <$1.50 | Margin covers infrastructure + operations |

---

## Next Steps

1. **Align on MVP scope:** Confirm phone voice is priority (this doc recommends it)
2. **Finalize LLM choice:** Claude 3.5 Sonnet or GPT-4 mini? (Both work; Sonnet is better quality)
3. **Design system prompt:** Draft "Dr. [TherapistName]'s AI Coach" persona
4. **Build COPPA consent flow:** Determine exact wording + delivery (voice or checkbox?)
5. **Set up Twilio account + API keys** (if not already done)
6. **Sketch therapist UX:** How does therapist review transcripts? Set escalation rules?
7. **Start development:** Week 1 = Twilio + backend

---

## Key Contact Points

- **Twilio support:** [support.twilio.com](https://support.twilio.com)
- **ElevenLabs API docs:** [elevenlabs.io/api](https://elevenlabs.io/api)
- **OpenAI Whisper API:** [platform.openai.com/docs/guides/speech-to-text](https://platform.openai.com/docs/guides/speech-to-text)
- **COPPA guidance:** [ftc.gov/business-guidance/resources/complying-coppa](https://www.ftc.gov/business-guidance/resources/complying-coppa)
- **Alexa (if future):** [developer.amazon.com/en-US/alexa](https://developer.amazon.com/en-US/alexa)

