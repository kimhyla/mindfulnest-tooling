# Windows Validation Procedure — LD-421 + LD-422

**Created:** 2026-04-26 (Mac/Darwin session)
**Scope:** Validate cross-platform behavior of the LD-421 asset findability build
and the LD-422 visible-magic skill wiring on the Windows work PC.
**Status:** PENDING — to be executed in a Windows-side Claude Code (Git Bash) session.

---

## Why this exists

The LD-421 build (asset findability overhaul) and the LD-422 follow-up (visible-magic
wiring) were performed and smoke-tested on the Mac home computer (Darwin). All path
resolution code follows the canonical LD-367 cross-platform pattern, but no Windows-side
test has been run. This procedure proves the wiring works end-to-end on Windows so
Kim's work PC can produce, register, and find magic assets identically to her Mac.

The hard cross-platform requirements that this procedure verifies:

- **LD-327** APP_REPO_SESSION_DIRECTUS_CRED_LOADING_V1 — credentials resolve via
  cross-platform helpers, never hardcoded paths.
- **LD-367** DIRECTUS_ADMIN_CLIENT_CROSS_PLATFORM_PATH_V1 — `Production/lib/directus_admin_client.py`
  + `Production/tools/lib/directus.py` handle path normalization.
- **MINDFULNEST_PROJECT_ROOT** env var with `platform.system()` branches in:
  - `Production/tools/registered_write.py` (lines 25-34)
  - `Production/tools/find_asset.py` (lines 32-40)
  - `Production/tools/magic_compositor.py` (lines 49-57)
  - `Production/scripts/docx_confirmation_hook.py` (lines 45-53 — canonical reference)

---

## Pre-conditions on the Windows machine

1. Project folder synced via Dropbox to:
   `C:\Users\ECDS Clinical\Dropbox\Claude Mindfulnest Project Files`
2. Python 3.10+ installed and on PATH (verify: `python3 --version` in Git Bash).
3. Required packages: `Pillow`, `numpy`, `scipy`, `imageio[ffmpeg]`, `pyyaml`. Install if missing:
   ```bash
   python3 -m pip install Pillow numpy scipy 'imageio[ffmpeg]' pyyaml
   ```
4. Directus credentials accessible via the same mechanism as Mac:
   - Either `doppler run -- python3 ...` if Doppler is configured on Windows, OR
   - `Production/API_KEYS_MASTER.md` is readable on the Windows-side path.
5. Git Bash (or another shell) where `python3` works.

---

## Validation steps

Run each step from the Git Bash terminal in the project root:
`cd "/c/Users/ECDS Clinical/Dropbox/Claude Mindfulnest Project Files"`

### Step 1 — PROJECT_ROOT auto-resolution check

Verify the cross-platform fallback resolves to the Windows path WITHOUT setting
the env var (auto-fallback test):

```bash
unset MINDFULNEST_PROJECT_ROOT
python3 -c "from Production.tools import registered_write as rw; print('PROJECT_ROOT:', rw._PROJECT_ROOT)"
```

**Expected output:**
```
PROJECT_ROOT: C:\Users\ECDS Clinical\Dropbox\Claude Mindfulnest Project Files
```

If the output shows the Mac path or an error, the platform-branch logic is broken
on Windows. STOP and escalate.

### Step 2 — Repeat for find_asset.py and magic_compositor.py

```bash
python3 -c "from Production.tools import find_asset; print('find_asset:', find_asset._PROJECT_ROOT)"
python3 -c "from Production.tools import magic_compositor; print('magic_compositor:', magic_compositor._PROJECT_ROOT)"
```

Both should print the Windows path.

### Step 3 — Env override check

Verify the env var takes precedence over the platform default:

```bash
MINDFULNEST_PROJECT_ROOT="/tmp/test" python3 -c "from importlib import reload; from Production.tools import registered_write; reload(registered_write); print(registered_write._PROJECT_ROOT)"
```

**Expected:** `/tmp/test` (env var overrides platform default).

### Step 4 — Directus credential resolution

Confirm the Directus client can authenticate from the Windows path:

```bash
python3 -c "
from Production.tools.lib import credentials, directus
creds = credentials.load_credentials()
client = directus.DirectusClient(creds['directus_url'], creds['directus_email'], creds['directus_password'])
result = client._request('GET', '/items/prod_modules?limit=1')
print('OK — got', len(result.get('data', [])), 'modules')
"
```

**Expected:** `OK — got 1 modules` (or similar). If 401/403, credentials aren't
loading from the Windows-side path correctly. Check `Production/API_KEYS_MASTER.md`
exists and is readable, or re-run with `doppler run -- python3 ...`.

### Step 5 — End-to-end smoke test (visible-magic wiring)

This is the same smoke test that PASSED on Darwin 2026-04-26. It writes a
synthetic background, renders a tiny preview + video via MagicCompositor with full
registration metadata, verifies both rows appear in `prod_assets` via search, and
cleans up. Run the inline test:

```bash
python3 << 'PYEOF'
import os, sys, time, platform
from pathlib import Path

env = os.environ.get('MINDFULNEST_PROJECT_ROOT')
if env:
    PROJECT_ROOT = env
elif platform.system() == 'Windows':
    PROJECT_ROOT = r"C:\Users\ECDS Clinical\Dropbox\Claude Mindfulnest Project Files"
else:
    PROJECT_ROOT = "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
sys.path.insert(0, PROJECT_ROOT)

print(f"Platform: {platform.system()}")
print(f"PROJECT_ROOT: {PROJECT_ROOT}")
assert platform.system() == 'Windows', f"Run this on Windows; saw {platform.system()}"

sandbox = Path(PROJECT_ROOT) / "Production" / "_sandbox"
sandbox.mkdir(parents=True, exist_ok=True)
ts = int(time.time())
bg_path = sandbox / f"win_smoke_bg_{ts}.png"

from PIL import Image
import numpy as np
arr = np.full((240, 320, 3), 80, dtype=np.uint8)
arr[150:200, :, :] = 60
Image.fromarray(arr).save(bg_path)
print(f"bg: {bg_path} ({bg_path.stat().st_size} bytes)")

from Production.tools.magic_compositor import MagicCompositor
mc = MagicCompositor(
    background_path=str(bg_path),
    path_pts=[(0.05, 0.75), (0.30, 0.72), (0.55, 0.70), (0.80, 0.68)],
    style="tessa_ori", duration=0.5, fps=24, seed=42,
    output_dir=str(sandbox), label=f"WIN_smoke_{ts}",
    module_id=1, event_id=1, beat_id="win_smoke_test_beat",
    scene_key=f"WIN_smoke_test_{ts}",
    tags=["LD422", "WIN_smoke", "DELETE_ME"],
)
preview_path = mc.render_preview(frame_idx=8)
video_path = mc.render_video()

from Production.tools import registered_write as rw
results = rw.search(f"WIN_smoke_test_{ts}", limit=10)
print(f"search found {len(results)}")

found_preview = found_video = None
for r in results:
    print(f"  id={r.get('id')} type={r.get('asset_type')} match={r.get('_match_source')}")
    if r.get('asset_type') == 'composite': found_preview = r['id']
    elif r.get('asset_type') == 'magic_clip': found_video = r['id']

# Cleanup
client = rw._client()
for aid in (found_preview, found_video):
    if aid: client._request('DELETE', f'/items/prod_assets/{aid}')
for p in (bg_path, Path(preview_path), Path(video_path)):
    if p.exists(): p.unlink()

status = "PASS" if (found_preview and found_video) else "FAIL"
print(f"=== WINDOWS SMOKE TEST {status} ===")
sys.exit(0 if status == "PASS" else 1)
PYEOF
```

**Expected last line:** `=== WINDOWS SMOKE TEST PASS ===` and exit code 0.

### Step 6 — find_asset preview-launch check

Verify the cross-platform browser-launch in find_asset works on Windows. Run a
benign search and confirm it opens a browser tab WITHOUT calling the Mac-only
`open` / `osascript`:

```bash
python3 Production/tools/find_asset.py --phrase "M1 INTRO" --no-preview
```

The `--no-preview` flag skips the browser launch — confirm the search itself works
on Windows (returns asset rows, no tracebacks). Then re-run WITHOUT `--no-preview`
and confirm a browser tab opens (Edge/Chrome/Firefox via `cmd /c start`).

---

## Recording the result

After all 6 steps pass, append a row to `prod_activity_log` from the Windows session:

```bash
python3 -c "
import sys, platform
from datetime import datetime
sys.path.insert(0, r'C:\Users\ECDS Clinical\Dropbox\Claude Mindfulnest Project Files')
from Production.tools.lib import credentials, directus
creds = credentials.load_credentials()
client = directus.DirectusClient(creds['directus_url'], creds['directus_email'], creds['directus_password'])
client._request('POST', '/items/prod_activity_log', data={
    'module_id': 1,
    'action': 'cross_platform_validation_complete:LD-421+LD-422',
    'details': {
        'platform': platform.system(),
        'machine': 'Kim work PC',
        'steps_passed': '1-6',
        'smoke_test_outcome': 'PASS',
        'parent_activity_log_id': 1349,
        'parent_preflight_id': 159,
    },
    'performed_by': 'claude',
    'kim_verdict': 'pending',
})
print('Windows validation logged.')
"
```

Then update LD-421 (decision_key=`ASSET_FINDABILITY_BUILD_V1`, id=422) notes to
mark Windows-validated:

```bash
python3 -c "
import sys
sys.path.insert(0, r'C:\Users\ECDS Clinical\Dropbox\Claude Mindfulnest Project Files')
from Production.tools.lib import credentials, directus
creds = credentials.load_credentials()
client = directus.DirectusClient(creds['directus_url'], creds['directus_email'], creds['directus_password'])
ld = client._request('GET', '/items/prod_locked_decisions/422')['data']
new_notes = (ld.get('notes') or '') + '\n\n[2026-MM-DD Windows validation PASS] All 6 steps passed on Kim work PC. Cross-platform LD-367 pattern verified end-to-end.'
client._request('PATCH', '/items/prod_locked_decisions/422', data={'notes': new_notes})
print('LD-421 notes updated.')
"
```

(Replace `2026-MM-DD` with the actual validation date when you run this.)

---

## If any step fails

1. **Step 1-3 fails** (PROJECT_ROOT wrong on Windows): inspect the affected file's
   import block. The `if _PROJECT_ROOT_ENV: ... elif _platform.system() == 'Windows': ... else: ...` 
   pattern must match exactly. Re-grep for any lingering hardcoded `/Users/kimberlysmith/...` in
   the import block.
2. **Step 4 fails** (Directus auth on Windows): Check `Production/API_KEYS_MASTER.md` is
   readable from the Windows path. If using Doppler, verify Doppler CLI is installed
   on Windows.
3. **Step 5 fails** (smoke test): Check the traceback. Common Windows-specific issues:
   - Permission errors on `Production/_sandbox` — verify the directory is writable
   - imageio ffmpeg backend missing — `pip install 'imageio[ffmpeg]'`
   - Font/render issues — usually safe to ignore for the smoke test
4. **Step 6 fails** (browser launch): Verify `cmd /c start` works in your shell. If
   not, the search itself still works — just the auto-open doesn't.

In all failure cases, file an `app_blockers` row referencing this document and
LD-421 / LD-422, and ping the next session for follow-up.

---

## Reference

- LD-421 `ASSET_FINDABILITY_BUILD_V1` (id=422) — full overhaul build
- LD-422 — visible-magic skill wiring follow-up
- LD-367 `DIRECTUS_ADMIN_CLIENT_CROSS_PLATFORM_PATH_V1` — canonical pattern
- LD-327 `APP_REPO_SESSION_DIRECTUS_CRED_LOADING_V1` — credential loading
- `Production/specs/asset_findability_overhaul_v1.md` §5.1, §9.1, §9.2.1 — spec
- `Production/scripts/docx_confirmation_hook.py:45-53` — canonical platform-branch reference
- `prod_activity_log` id=1349 — LD-422 wiring activity entry (Mac side)
- `prod_preflight_reviews` id=159 — LD-422 architectural classification + Phase 0 record
