# Storyboard Option B — Local Server + Dropbox Runtime Spec v1

**Status:** ACTIVE (2026-06-20)  
**Scope:** Authoring toolchain only (Beat Gen, Storyboard, Stitcher). Kid app unchanged.  
**Non-goal:** Cloud hosting (Option C), moving media off Dropbox.

---

## 1. Decision

**Option B:** Keep Dropbox as the **runtime filesystem** for `Production/Event_N/` media and state. Keep Python on Kim's Mac. Eliminate deploy drift via **one canonical deploy path** with **machine-verifiable proof** — no manual partial copies, no wrong-port smoke, no "restart alone is deploy."

---

## 2. Dual root (unchanged)

| Root | Role |
|------|------|
| `~/Projects/mindfulnest-tooling` | **Canonical code** — git, edit, pytest; **launchd runs `production_server.py` from here** |
| Dropbox `…/Claude Mindfulnest Project Files/Production/` | **Runtime data** — `Event_N/` media, state, storyboard HTML fanout; `--event-dir` points here |

**Rule:** Tooling-repo edits are **not live** until deploy completes with exit 0 (restart + storyboard fanout). Code no longer executes from `Dropbox/Production/tools/` — only data is read from Dropbox.

---

## 3. Canonical operator path (agents + Kim)

```bash
bash Production/scripts/deploy_option_b.sh --event Event_2
```

Steps inside (non-skippable):

1. Git-clean gate (committed HEAD = build-sha)
2. `npm run build` + stale-dist gate + regression guards
3. Rsync `Production/{tools,lib,scripts}` → Dropbox
4. Copy `dist/index.html` → `Event_*/storyboard_v59_prod.html` fanout
5. sha256 parity (`verify_tooling_dropbox_parity.py` exit 0)
6. Restart **only** the target event's dedicated port (`5110 + N`)
7. Live proof: build-sha on `http://localhost:{port}/` matches `git rev-parse --short HEAD`
8. API smoke: `/api/event/load`, O3 capabilities
9. Write `.last_deploy` sentinel

**Forbidden:** `cp` single file to Dropbox, manual rsync one subdir, "restart server" without mirror, `MN_ALLOW_DIRTY_DEPLOY=1` except SHORTCUT LD.

---

## 4. Dedicated event ports

| Event | URL |
|-------|-----|
| Event_1 | http://localhost:5111/?event=Event_1 |
| Event_2 | http://localhost:5112/?event=Event_2 |
| Event_N | http://localhost:{5110+N}/?event=Event_N |

Deploy and smoke **must** use the port for the deployed event — never hardcode 5111 when working Event_2.

---

## 5. Verification contract (`verify_deploy_option_b_live.sh`)

All must pass after deploy:

| Check | Evidence |
|-------|----------|
| Parity | `verify_tooling_dropbox_parity.py` exit 0 |
| Bundle sha | Dropbox `Event_N/storyboard_v59_prod.html` build-sha == git HEAD |
| Live sha | curl `http://localhost:{port}/` build-sha == git HEAD |
| UI marker | Served HTML contains `data-testid="app-build-sha"` with HEAD |
| Server HTTP | GET / → 200 |
| Event pin | POST `/api/event/load` → 200 |

---

## 6. What changes for Kim day-to-day

- **Same:** Files in Dropbox, bookmark per event, edit in Cursor on tooling repo.
- **Better:** After any agent code change, one deploy script → provable live sha.
- **Gone:** "Did the fix land?" — if deploy exit 0, yes; if not, no.

---

## 7. Files (implementation map)

| File | Purpose |
|------|---------|
| `Production/scripts/deploy_option_b.sh` | Single entry point |
| `Production/scripts/deploy_storyboard_v59.sh` | Full mirror + guards (called by option B) |
| `Production/scripts/verify_deploy_option_b_live.sh` | Post-deploy multipass proof |
| `Production/scripts/event_server_port.sh` | Port mapping |
| `Production/scripts/start_event_server.sh` | Dedicated server launch (Dropbox runtime) |
| `.cursor/rules/storyboard-option-b-workflow.mdc` | Agent always uses deploy_option_b |

---

## 8. Success criteria

Deploy is **done** only when:

1. `deploy_option_b.sh` exit 0
2. Proof block printed with HEAD sha, port, URL, marker match count
3. Browser-visible build-sha in storyboard header matches HEAD (hard refresh)
