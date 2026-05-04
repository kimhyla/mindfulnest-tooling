#!/usr/bin/env python3
"""
patch_magic_server.py
Adds visible-magic Phase 2 API routes to production_server.py.

Safe patch strategy:
  1. Back up the original file
  2. Three targeted string replacements (job dict, GET routes, POST routes, handlers)
  3. Import-verify the result
  4. Roll back on any failure

Run: python3 patch_magic_server.py
"""

import importlib.util
import shutil
import sys
import time
from pathlib import Path

SERVER = Path(__file__).parent / "production_server.py"
BAK    = Path(__file__).parent / f"production_server.py.bak_magic_{int(time.time())}"

# ── Patch 1 — add _MAGIC_JOBS dict after _ASSEMBLE_JOBS ──────────────────

PATCH1_OLD = (
    "# Background assembly jobs: group_id → "
    "{status, assembled_clip_path?, duration?, file_size_bytes?, error?}\n"
    "_ASSEMBLE_JOBS: dict = {}"
)

PATCH1_NEW = (
    "# Background assembly jobs: group_id → "
    "{status, assembled_clip_path?, duration?, file_size_bytes?, error?}\n"
    "_ASSEMBLE_JOBS: dict = {}\n\n"
    "# Visible-magic render jobs: job_id → "
    "{status, message, scene_key, preview_path, video_path, error}\n"
    "_MAGIC_JOBS: dict = {}"
)

# ── Patch 2 — add GET routes in do_GET before 404 fallback ───────────────

PATCH2_OLD = (
    "            if path.startswith(\"/api/storyboard/list\"):\n"
    "                return self._handle_storyboard_list()\n"
    "            return self._send_json(404, {\"error\": \"not found\", \"path\": path})"
)

PATCH2_NEW = (
    "            if path.startswith(\"/api/storyboard/list\"):\n"
    "                return self._handle_storyboard_list()\n"
    "            # ── Visible Magic Phase 2 (2026-04-24) ──────────────────────────────\n"
    "            if path == \"/magic\":\n"
    "                return self._serve_magic_picker()\n"
    "            if path == \"/api/magic/status\":\n"
    "                return self._handle_magic_status()\n"
    "            if path == \"/api/magic/resolve_bg\":\n"
    "                return self._handle_magic_resolve_bg()\n"
    "            return self._send_json(404, {\"error\": \"not found\", \"path\": path})"
)

# ── Patch 3 — add POST route in do_POST before 404 fallback ──────────────

PATCH3_OLD = (
    "            if path == \"/api/storyboard/switch\":\n"
    "                return self._handle_storyboard_switch(body)\n"
    "            return self._send_json(404, {\"error\": \"not found\", \"path\": path})"
)

PATCH3_NEW = (
    "            if path == \"/api/storyboard/switch\":\n"
    "                return self._handle_storyboard_switch(body)\n"
    "            # ── Visible Magic Phase 2 (2026-04-24) ──────────────────────────────\n"
    "            if path == \"/api/magic/submit_path\":\n"
    "                return self._handle_magic_submit_path(body)\n"
    "            return self._send_json(404, {\"error\": \"not found\", \"path\": path})"
)

# ── Patch 4 — add handler methods before _handle_bg_segments ─────────────

PATCH4_OLD = "    def _handle_bg_segments(self) -> None:"

PATCH4_NEW = '''    # ================================================================
    # Visible Magic Phase 2 handlers (2026-04-24)
    # ================================================================

    def _serve_magic_picker(self) -> None:
        """Serve path_picker.html for the /magic route."""
        import urllib.parse as _up
        picker = Path(__file__).parent / "path_picker.html"
        if not picker.exists():
            return self._send_json(404, {"error": "path_picker.html not found"})
        html = picker.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(html)

    def _handle_magic_resolve_bg(self) -> None:
        """Resolve background still path for a scene_key."""
        import urllib.parse as _up
        import yaml as _yaml
        qs = _up.parse_qs(_up.urlparse(self.path).query)
        scene_key = (qs.get("scene_key") or [None])[0]
        if not scene_key:
            return self._send_json(400, {"ok": False, "error": "scene_key required"})
        reg_path = Path(__file__).parent / "scene_registry.yaml"
        if not reg_path.exists():
            return self._send_json(404, {"ok": False, "error": "scene_registry.yaml not found"})
        registry = _yaml.safe_load(reg_path.read_text()) or {}
        scene = registry.get(scene_key, {})
        # Resolve from well-known paths
        db = Path(__file__).parent.parent.parent  # Dropbox/Claude Mindfulnest Project Files
        shot_role = scene.get("source_asset_query", {}).get("filter", {}).get("shot_role", "")
        event_id = scene.get("event_id", "e1").replace("e", "Event_")
        candidates = []
        if shot_role:
            candidates.append(db / "Production" / event_id / "resolution_stills" / f"{shot_role}.png")
        # Known scene-key → file fallback map
        _KNOWN_STILLS = {
            "m1_e1_res_beat_01_heartwood": "heartwood_3q_left_1456.png",
            "m1_e1_res_beat_01_heartwood_wide": "heartwood_wide_1456.png",
            "m1_e1_res_beat_02_runestone": "still_3_body_stone_glow_v9.png",
        }
        if scene_key in _KNOWN_STILLS:
            candidates.append(db / "Production" / "Event_1" / "resolution_stills" / _KNOWN_STILLS[scene_key])
        for c in candidates:
            if c.exists():
                bg_url = f"/files?path={_up.quote(str(c))}"
                return self._send_json(200, {"ok": True, "bg_url": bg_url, "bg_path": str(c)})
        return self._send_json(404, {"ok": False, "error": f"No background still found for {scene_key}"})

    def _handle_magic_status(self) -> None:
        """Poll magic render job status."""
        import urllib.parse as _up
        qs = _up.parse_qs(_up.urlparse(self.path).query)
        job_id = (qs.get("job_id") or [None])[0]
        if not job_id:
            return self._send_json(400, {"ok": False, "error": "job_id required"})
        job = _MAGIC_JOBS.get(job_id)
        if not job:
            return self._send_json(404, {"ok": False, "error": "job not found"})
        # Translate file paths to serveable URLs
        import urllib.parse as _up2
        resp = dict(job)
        for key in ("preview_path", "video_path"):
            if resp.get(key):
                resp[key + "_url"] = f"/files?path={_up2.quote(str(resp[key]))}"
        return self._send_json(200, {"ok": True, **resp})

    def _handle_magic_submit_path(self, body: dict) -> None:
        """Validate clicked path, write registry, kick off render pipeline."""
        import threading as _th
        import traceback as _tb
        import uuid as _uuid
        import urllib.parse as _up

        scene_key   = body.get("scene_key", "").strip()
        manual_path = body.get("manual_path", [])
        style       = body.get("style", "tessa_ori")

        # ── Validation ────────────────────────────────────────────────
        if not scene_key:
            return self._send_json(400, {"ok": False, "error": "scene_key required"})
        if not manual_path or not isinstance(manual_path, list):
            return self._send_json(400, {"ok": False, "error": "manual_path required"})
        if len(manual_path) < 2:
            return self._send_json(400, {"ok": False, "error": "manual_path must have ≥ 2 points"})
        if len(manual_path) > 20:
            return self._send_json(400, {"ok": False, "error": "manual_path max 20 points"})
        for i, pt in enumerate(manual_path):
            try:
                x, y = float(pt[0]), float(pt[1])
            except (TypeError, IndexError, ValueError):
                return self._send_json(400, {"ok": False, "error": f"point {i} malformed: {pt}"})
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                return self._send_json(400, {"ok": False,
                    "error": f"point {i} out of range: [{x},{y}] must be in [0,1]"})

        # Normalize to list of [float, float]
        path_pts_clean = [[float(pt[0]), float(pt[1])] for pt in manual_path]

        # ── Job setup ─────────────────────────────────────────────────
        job_id = f"magic_{int(time.time())}_{scene_key[-20:]}"
        _MAGIC_JOBS[job_id] = {
            "status": "pending",
            "message": "Queued",
            "scene_key": scene_key,
            "preview_path": None,
            "video_path": None,
            "error": None,
        }

        def _run():
            import yaml as _yaml
            import datetime as _dt
            import json as _json
            try:
                # ── Step 1: Write to scene_registry.yaml ──────────────
                _MAGIC_JOBS[job_id].update({"status": "writing_registry",
                                            "message": "Saving path to scene registry..."})
                reg_path = Path(__file__).parent / "scene_registry.yaml"
                bak_path = reg_path.with_suffix(f".yaml.bak_magic_{int(time.time())}")
                shutil.copy2(reg_path, bak_path)

                try:
                    import ruamel.yaml as _ry
                    ry = _ry.YAML()
                    ry.preserve_quotes = True
                    with open(reg_path) as f:
                        registry = ry.load(f)
                    if registry is None:
                        registry = {}
                    if scene_key not in registry:
                        registry[scene_key] = {
                            "archetype": "ground_left_to_target",
                            "description": f"Magic trail for {scene_key}",
                            "module_id": body.get("module_id", "m1"),
                            "event_id": body.get("event_id", "e1"),
                            "beat": body.get("beat", "res_beat_01"),
                            "style": style,
                            "color_target": "orange",
                            "direction": "left",
                        }
                    registry[scene_key]["manual_path"] = path_pts_clean
                    registry[scene_key]["style"] = style
                    with open(reg_path, "w") as f:
                        ry.dump(registry, f)
                except ImportError:
                    # ruamel not available — use pyyaml fallback
                    registry = _yaml.safe_load(reg_path.read_text()) or {}
                    if scene_key not in registry:
                        registry[scene_key] = {
                            "archetype": "ground_left_to_target",
                            "module_id": body.get("module_id", "m1"),
                            "event_id": body.get("event_id", "e1"),
                            "beat": body.get("beat", "res_beat_01"),
                            "style": style,
                        }
                    registry[scene_key]["manual_path"] = path_pts_clean
                    reg_path.write_text(_yaml.dump(registry, default_flow_style=False))

                # ── Step 2: Resolve background still ──────────────────
                _MAGIC_JOBS[job_id].update({"status": "rendering_preview",
                                            "message": "Resolving background still..."})
                db = Path(__file__).parent.parent.parent
                _KNOWN_STILLS = {
                    "m1_e1_res_beat_01_heartwood": "heartwood_3q_left_1456.png",
                    "m1_e1_res_beat_01_heartwood_wide": "heartwood_wide_1456.png",
                    "m1_e1_res_beat_02_runestone": "still_3_body_stone_glow_v9.png",
                }
                reg2 = _yaml.safe_load(reg_path.read_text()) or {}
                scene = reg2.get(scene_key, {})
                shot_role = scene.get("source_asset_query", {}).get("filter", {}).get("shot_role", "")
                event_id = scene.get("event_id", "e1")
                event_dir = db / "Production" / f"Event_{event_id.replace('e','')}" / "resolution_stills"
                bg_path = None
                if shot_role:
                    cand = event_dir / f"{shot_role}.png"
                    if cand.exists():
                        bg_path = str(cand)
                if bg_path is None and scene_key in _KNOWN_STILLS:
                    cand = event_dir / _KNOWN_STILLS[scene_key]
                    if cand.exists():
                        bg_path = str(cand)
                if bg_path is None:
                    raise FileNotFoundError(
                        f"Cannot find background still for {scene_key}. "
                        f"Add to _KNOWN_STILLS in production_server.py or set source_asset_query."
                    )

                # ── Step 3: Render preview still ──────────────────────
                _MAGIC_JOBS[job_id].update({"message": "Rendering preview still (final frame)..."})
                sys.path.insert(0, str(Path(__file__).parent))
                from magic_compositor import MagicCompositor
                out_dir = db / "Production" / "Event_1" / "kling_clips"
                out_dir.mkdir(parents=True, exist_ok=True)
                path_pts_tuples = [tuple(pt) for pt in path_pts_clean]
                mc = MagicCompositor(
                    background_path=bg_path,
                    path_pts=path_pts_tuples,
                    style=style,
                    duration=3.5,
                    fps=24,
                    seed=99,
                    output_dir=str(out_dir),
                    label=f"{scene_key}_server",
                )
                total_frames = int(mc.duration * mc.fps)
                preview_path = mc.render_preview(frame_idx=total_frames - 2)
                _MAGIC_JOBS[job_id]["preview_path"] = preview_path

                # ── Step 4: Render full video ──────────────────────────
                _MAGIC_JOBS[job_id].update({"status": "rendering_video",
                                            "message": "Rendering full video (84 frames)..."})
                video_path = mc.render_video()
                _MAGIC_JOBS[job_id]["video_path"] = video_path

                # ── Step 5: Directus two-write ─────────────────────────
                _MAGIC_JOBS[job_id].update({"status": "registering",
                                            "message": "Registering in Directus..."})
                try:
                    import urllib.request as _req
                    api_keys_path = db / "Production" / "API_KEYS_MASTER.md"
                    # Parse token from API_KEYS_MASTER.md
                    token = None
                    base_url = "https://directus-production-3460.up.railway.app"
                    if api_keys_path.exists():
                        txt = api_keys_path.read_text()
                        import re as _re
                        em = _re.search(r"directus.*?email[\s:]+(\S+)", txt, _re.I)
                        pw = _re.search(r"directus.*?password[\s:]+(\S+)", txt, _re.I)
                        if em and pw:
                            auth_body = _json.dumps({"email": em.group(1), "password": pw.group(1)}).encode()
                            req = _req.Request(f"{base_url}/auth/login",
                                              data=auth_body,
                                              headers={"Content-Type": "application/json"})
                            with _req.urlopen(req, timeout=15) as resp:
                                token = _json.loads(resp.read())["data"]["access_token"]
                    if token:
                        hdrs = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
                        # Write 1: prod_magic_clips
                        clip_payload = _json.dumps({
                            "scene_key": scene_key,
                            "style": style,
                            "manual_path": path_pts_clean,
                            "preview_path": preview_path,
                            "video_path": video_path,
                            "geometry_confirmed_at": _dt.datetime.utcnow().isoformat(),
                            "status": "approved",
                        }).encode()
                        req1 = _req.Request(f"{base_url}/items/prod_magic_clips",
                                            data=clip_payload, headers=hdrs)
                        try:
                            _req.urlopen(req1, timeout=15)
                        except Exception as e1:
                            print(f"[magic] prod_magic_clips write failed: {e1}", file=sys.stderr)
                        # Write 2: prod_activity_log
                        log_payload = _json.dumps({
                            "session_date": _dt.date.today().isoformat(),
                            "activity_type": "magic_render_approved",
                            "description": (f"Magic trail auto-rendered for {scene_key}. "
                                            f"{len(path_pts_clean)} pts. Video: {video_path}"),
                            "output_file": video_path,
                            "kim_verdict": "approved",
                        }).encode()
                        req2 = _req.Request(f"{base_url}/items/prod_activity_log",
                                            data=log_payload, headers=hdrs)
                        try:
                            _req.urlopen(req2, timeout=15)
                        except Exception as e2:
                            print(f"[magic] prod_activity_log write failed: {e2}", file=sys.stderr)
                except Exception as reg_e:
                    # Registration failure is non-blocking — log and continue
                    print(f"[magic] Directus registration failed: {reg_e}", file=sys.stderr)
                    pending = db / "Production" / "Event_1" / "PENDING_REGISTRATIONS.json"
                    try:
                        existing = _json.loads(pending.read_text()) if pending.exists() else []
                        existing.append({"scene_key": scene_key, "video_path": video_path,
                                         "error": str(reg_e), "at": _dt.datetime.utcnow().isoformat()})
                        pending.write_text(_json.dumps(existing, indent=2))
                    except Exception:
                        pass

                # ── Done ──────────────────────────────────────────────
                _MAGIC_JOBS[job_id].update({"status": "done",
                                            "message": "Magic render complete."})

            except Exception as exc:
                _tb.print_exc()
                _MAGIC_JOBS[job_id].update({"status": "error",
                                            "message": str(exc),
                                            "error": str(exc)})

        _th.Thread(target=_run, daemon=True).start()
        return self._send_json(200, {
            "ok": True,
            "job_id": job_id,
            "poll": f"/api/magic/status?job_id={job_id}",
        })

    def _handle_bg_segments(self) -> None:'''


# ══════════════════════════════════════════════════════════════════════════
# Execute the patch
# ══════════════════════════════════════════════════════════════════════════

def apply_patch():
    src = SERVER.read_text(encoding="utf-8")
    original = src

    # Verify pre-conditions
    for marker, name in [
        (PATCH1_OLD, "PATCH1_OLD (_ASSEMBLE_JOBS)"),
        (PATCH2_OLD, "PATCH2_OLD (do_GET 404 fallback)"),
        (PATCH3_OLD, "PATCH3_OLD (do_POST 404 fallback)"),
        (PATCH4_OLD, "PATCH4_OLD (_handle_bg_segments)"),
    ]:
        if marker not in src:
            print(f"ERROR: marker not found: {name}", file=sys.stderr)
            print("Possible causes: server already patched, or file changed.", file=sys.stderr)
            sys.exit(1)

    # Check not already patched
    if "_MAGIC_JOBS" in src:
        print("Server appears already patched (_MAGIC_JOBS found). Skipping.", flush=True)
        return

    # Back up
    shutil.copy2(SERVER, BAK)
    print(f"Backup: {BAK.name}", flush=True)

    # Apply patches
    src = src.replace(PATCH1_OLD, PATCH1_NEW, 1)
    src = src.replace(PATCH2_OLD, PATCH2_NEW, 1)
    src = src.replace(PATCH3_OLD, PATCH3_NEW, 1)
    src = src.replace(PATCH4_OLD, PATCH4_NEW, 1)

    # Verify all patches applied
    assert "_MAGIC_JOBS" in src, "PATCH1 failed"
    assert '"/magic"' in src, "PATCH2 failed"
    assert '"/api/magic/submit_path"' in src, "PATCH3 failed"
    assert "_handle_magic_submit_path" in src, "PATCH4 failed"

    # Write
    SERVER.write_text(src, encoding="utf-8")
    print("production_server.py patched.", flush=True)

    # Import-verify
    spec = importlib.util.spec_from_file_location("production_server", SERVER)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        print("Import verification: OK", flush=True)
    except Exception as e:
        print(f"Import FAILED: {e} — rolling back", file=sys.stderr)
        shutil.copy2(BAK, SERVER)
        sys.exit(1)

    print("\nAll patches applied successfully.", flush=True)
    print(f"Backup at: {BAK.name}", flush=True)


if __name__ == "__main__":
    apply_patch()
