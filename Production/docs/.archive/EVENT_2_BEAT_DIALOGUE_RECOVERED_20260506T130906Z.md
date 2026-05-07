# Event_2 Beat Dialogue — Recovered (Pre-C-9b SKIP)

**UTC timestamp:** 20260506T130906Z  
**Session:** post-redeploy-authoring-workflow-2026-05-06  
**Branch:** claude/post-redeploy-bug-triage  
**Disposition:** C-9b normative SKIP per spec §7.4. RR-1 invariant
firing on Event_1 beats 1-11 (rendered Kling .mp4 files in event-pinned
clips_dir/) made KEEP-IDS salvage non-viable. Skip path empties both
partitions atomically; this transcript preserves dialogue + speaker
content for Kim's manual re-author of Event_2 from arc skeleton.

**Sources of dialogue truth (cross-checked at Kim's authoring time):**
- This transcript (text + canonical speaker per K8 resolution)
- Arc skeleton at `Arc Skeletons/Arc 1/` (Dropbox tree)
- Storyboard HTML L[] array in `Production/Event_*/intro/storyboard_v59_prod.html`
- BG sidecar at `Production/beat_generator_state.json` (BG-segment-keyed)

**Total beats captured:** 18  

| # | source_event | source_role | beat_id | speaker (raw) | speaker (canonical) | speaker (K8 resolved) | phase_1.status | rendered_files | text |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Event_1 | intro | beat_01 | Luna | Luna | Luna | polling | beat_01_option_A.mp4 | (Sounds of something heavy falling through the branches and landing on the forest floor). Luna's disembodied voice: [pause] [pause]. "I'm OK! I'm OK." |
| 2 | Event_1 | intro | beat_02 | Luna | Luna | Luna | completed | beat_02_option_2_regen_20260419T213621Z.mp4, beat_02_option_3.mp4 | WHAT is THAT.... Is that ... Is that IT...?  Did I find it?? |
| 3 | Event_1 | intro | beat_03 | Tessa | Tessa | Tessa | partial | beat_03_option_A.mp4, beat_03_option_2.mp4, beat_03_option_3.mp4 | Hello ... who are you? |
| 4 | Event_1 | intro | beat_04 | Tessa | Tessa | Tessa | completed | beat_04_option_A.mp4 | [curious]  I'm Luna.  I'm a scientist.  [pause].  Well, a student scientist.. [pause]  And if my calculations are right... [pause] THAT is the MindfulNest! |
| 5 | Event_1 | intro | beat_05 | Guide Bird | Chipper | Guide Bird | completed | beat_05_option_startend_20260417-133323.mp4, beat_05_option_2.mp4 | You're right ... How do you know about the MindfulNest? |
| 6 | Event_1 | intro | beat_06 | Luna | Luna | Luna | completed | beat_06_option_A.mp4, beat_06_option_2.mp4, beat_06_option_3.mp4, beat_06_option_4.mp4, beat_06_option_5.mp4, beat_06_option_A_looped.mp4 | Oh my gosh!  I can't believe it!  I study the MindfulNest at school.  The old books say it brought Light-Magic into the world.  But that was like a thousand years ago, so I'm not sure- WHOAH!! |
| 7 | Event_1 | intro | beat_07 | Luna | Luna | Luna | completed | beat_07_option_A.mp4, beat_07_option_2.mp4, beat_07_option_3.mp4, beat_07_option_4.mp4, beat_07_option_5.mp4 | IT'S AWAKE!!!  [pause] [pause] The Runestone [pause] How?! What did you DO?!? |
| 8 | Event_1 | intro | beat_08 | Tessa | Tessa | Tessa | completed | beat_08_option_A.mp4, beat_08_option_2.mp4, beat_08_option_3.mp4 | Well, I don't know!  I fell ... I got hurt.  This child is studying magic [pause] ... and ... cast a magic spell and [pause] .... fixed my shell.  Then ... the runestone just woke up. |
| 9 | Event_1 | intro | beat_09 | Luna | Luna | Luna | polling | beat_09_option_A.mp4 | (Looks directly at camera, shocked). You woke it up?? By YOURSELF?? |
| 10 | Event_1 | intro | beat_10 | Chipper | Chipper | Chipper | completed | beat_10_option_A.mp4 | Isn't it great? We're training in magic |
| 11 | Event_1 | intro | beat_11 | Luna | Luna | Luna | completed | beat_11_option_A.mp4, beat_11_option_2.mp4, beat_11_option_3.mp4, beat_11_option_4.mp4, beat_11_option_5.mp4 | Are you serious?? This is HUGE!! You WOKE UP A RUNESTONE WITH MAGIC!!! It's the biggest discovery in a hundred years!! The biggest discovery EVER! |
| 12 | Event_1 | intro | beat_12 | Tessa | Tessa | Tessa |  |  | "Guys... look at this writing next to the runestone.  It says... [pause] .... Um ...Feel... whats... real." |
| 13 | Event_1 | intro | beat_13 | Chipper | Chipper | Chipper |  |  | (looks at camera) Interesting .... that's what the Magic Hands Spell does, remember? You felt real magic between your hands. |
| 14 | Event_1 | intro | beat_14 | Luna | Luna | Luna |  |  | Oh this is the most EXCITING THING IN THE WORLD!!! I'll publish a paper about this! I'll give a speech at the College! |
| 15 | Event_1 | intro | beat_15 | Tessa | Tessa | Tessa |  |  | (diesmbodied voice) "What's THAT one say?  [pause] [pause] (reading aloud):  'Stay loose and light'. |
| 16 | Event_1 | intro | beat_16 | Luna | Luna | Luna |  |  | (worked up in a frenzy) What does it mean, what does it mean!? Oh I just HAVE to solve this mystery!!  (falls over) |
| 17 | Event_1 | intro | beat_17 | Chipper | Chipper | Chipper |  |  | OK, Kiddo.  (walking forward) Luna knows a lot about Everdale.  But she's so excited she can't think straight!  Let's try another Magic Spell.  Maybe we can help her calm down and focus. |
| 18 | Event_2 | intro | beat_04b |  |  |  |  |  | The MindfulNest! ... Well don't you know? It's in all the stories. The MindfulNest was the Heart of the Ancient Magical City. ... Everdale? |

## Notes

- Beats 1-11 in Event_1/intro have rendered Kling animations stored
  under `Production/Event_1/clips_dir/` — those files remain on disk
  even after C-9b empties the state partition. Filesystem is untouched.
- Beats 12-17 in Event_1/intro were the truly stranded Event-2 narrative
  beats from the 2026-05-01 leak (status=None; 0 options; 0 files).
  Pre-C-8.5 Event_2/intro had a single orphan stub `beat_04` (renamed
  to `beat_04b` for collision avoidance). All preserved here.
- Speaker columns: raw = on-disk top-level value; canonical =
  _canonicalize_speaker(raw) (e.g. 'Guide Bird' → 'Chipper'); K8 resolved
  = _resolve_beat_speaker which prefers top-level then falls back to
  phase_1.speaker mirror.
- Event_1 ships via the existing saved scene mp4 at
  `Production/Event_1/intro/scene_intro_*.mp4` per LD
  `EVENT_1_SHIPS_VIA_SAVED_VIDEO_V1` (Directus row 539). Re-author of
  Event_2 happens against arc skeleton + this transcript when Kim is ready.
