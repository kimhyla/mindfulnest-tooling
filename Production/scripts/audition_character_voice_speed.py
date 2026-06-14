#!/usr/bin/env python3
"""Generate ElevenLabs speed-ladder auditions before Kling Element re-register.

Usage:
  # Step 3 — speed ladder (writes session.json with element_sample_lines)
  python3 scripts/audition_character_voice_speed.py --char Chipper \\
      --line 'Ready? Just focus on the Teleport Glass. Here we go!'

  # Step 3b — after Kim picks letter D at 1.15, update roster speed, then lock:
  python3 scripts/audition_character_voice_speed.py --char Chipper \\
      --lock-speed 1.15 \\
      --from-dir kling_voice_audition/samples/chipper/speed_compare_20260604

  # Step 4 — register (requires lock; clones locked element_sample_lines MP3)
  python3 scripts/setup_all_kling_character_voices.py --char Chipper --force

See Production/docs/BEAT_GEN_CHARACTER_ONBOARDING_v1.md §3–4.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD_ROOT = HERE.parent
TOOLS_DIR = PROD_ROOT / "tools"
if str(PROD_ROOT) not in sys.path:
    sys.path.insert(0, str(PROD_ROOT))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib.credential_store import get_secret  # noqa: E402
from kling_element_voice import ELEVENLABS_VOICE_ROSTER  # noqa: E402
from kling_voice_sample_lock import (  # noqa: E402
    default_element_sample_lines,
    join_element_sample_lines,
    load_audition_session,
    lock_from_session,
    write_audition_session,
)
from tools import kling_character_registry as reg  # noqa: E402

ELEVENLABS_TTS = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

ARCHETYPE_SPEED_LADDER: dict[str, list[float]] = {
    "guide": [0.93, 1.00, 1.08, 1.15, 1.20],
    "vulnerable": [0.90, 0.95, 1.00, 1.05, 1.10],
    "warm_adult": [0.90, 0.95, 1.00, 1.05, 1.10],
    "comic": [0.95, 1.00, 1.08, 1.12, 1.18],
    "default": [0.93, 1.00, 1.08, 1.15, 1.20],
}

CHARACTER_ARCHETYPE: dict[str, str] = {
    "Chipper": "guide",
    "Tessa": "vulnerable",
    "Benson": "warm_adult",
    "Ember": "warm_adult",
    "Bramble": "warm_adult",
    "Bork": "comic",
    "Luna": "vulnerable",
    "Oliver": "warm_adult",
    "Grizzle": "warm_adult",
    "Willow": "warm_adult",
    "The King": "warm_adult",
    "Lorelai": "vulnerable",
}


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("'", "")


def _speed_slug(speed: float) -> str:
    return str(speed).replace(".", "p")


def _speed_label(speed: float, roster_speed: float) -> str:
    if abs(speed - roster_speed) < 0.005:
        return f"A_current_{_speed_slug(speed)}"
    order = "BCDEFGHI"
    idx = min(int(speed * 10) % 10, len(order) - 1)
    return f"{order[idx]}_{_speed_slug(speed)}"


def _parse_element_lines(raw: str | None, char_name: str, audition_line: str) -> list[str]:
    if raw:
        parts = [p.strip() for p in raw.split("|") if p.strip()]
        if parts:
            return parts
    locked = default_element_sample_lines(char_name, audition_line)
    if locked:
        return locked
    return [audition_line] if audition_line else []


def synthesize(
    voice_id: str,
    text: str,
    voice_settings: dict,
    dest: Path,
    api_key: str,
) -> bool:
    body = json.dumps({
        "text": text,
        "model_id": voice_settings.pop("_model", "eleven_v3"),
        "voice_settings": voice_settings,
    })
    url = ELEVENLABS_TTS.format(voice_id=voice_id)
    r = subprocess.run(
        [
            "curl", "-s", "-S", "-m", "90", "-X", "POST",
            "-H", f"xi-api-key: {api_key}",
            "-H", "Content-Type: application/json",
            "-H", "Accept: audio/mpeg",
            "-d", body,
            "-o", str(dest),
            url,
        ],
        capture_output=True,
        text=True,
        timeout=100,
    )
    return r.returncode == 0 and dest.is_file() and dest.stat().st_size > 1000


def write_listen_html(
    out_dir: Path,
    char_name: str,
    line: str,
    element_lines: list[str],
    entries: list[dict],
) -> Path:
    element_preview = join_element_sample_lines(element_lines)
    out_ref = out_dir
    try:
        out_ref = out_dir.relative_to(PROD_ROOT)
    except ValueError:
        out_ref = out_dir
    rows = "\n".join(
        f'<tr class="{"rec" if e.get("recommended") else ""}">'
        f'<td>{e["speed"]}</td>'
        f'<td><audio controls src="{e["file"]}"></audio></td>'
        f'<td>{e["label"]}</td>'
        f'<td><code style="font-size:11px">--lock-speed {e["speed"]}</code></td></tr>'
        for e in entries if e.get("ok")
    )
    html = out_dir / "listen.html"
    html.write_text(
        f"""<!DOCTYPE html>
<html><head><meta charset=utf-8><title>{char_name} speed audition</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 820px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
td {{ padding: 0.6rem 0; vertical-align: middle; }}
.rec {{ background: #f0fdf4; }}
code {{ font-size: 0.9em; }}
ol.steps li {{ margin: 0.4rem 0; }}
</style></head>
<body>
<h1>{char_name} — Beat Gen speed choice board</h1>
<p><strong>① Listen</strong> — speed ladder uses this line only:</p>
<p><em>{line}</em></p>
<p><strong>② Element create-voice mix</strong> (what Kling clones — written on lock):</p>
<ul>{"".join(f"<li><em>{x}</em></li>" for x in element_lines)}</ul>
<ol class="steps">
  <li>Pick a speed row below (letter is for your notes only).</li>
  <li>Set <code>speed</code> in <code>kling_element_voice.py</code> → <code>ELEVENLABS_VOICE_ROSTER["{char_name}"]</code>.</li>
  <li>Lock session (copy speed from chosen row):<br>
    <code>cd Production &amp;&amp; python3 scripts/audition_character_voice_speed.py --char {char_name} --lock-speed SPEED --from-dir {out_ref}</code></li>
  <li>Register Element (~$0.045):<br>
    <code>doppler run -- python3 scripts/setup_all_kling_character_voices.py --char {char_name} --force</code></li>
  <li>Deploy storyboard → one smoke beat in Beat Gen → listen → batch.</li>
</ol>
<table>
<tr><th>Speed</th><th>Listen</th><th>Label</th><th>Lock flag</th></tr>
{rows}
</table>
<p><small>Create-voice MP3 text: <em>{element_preview[:240]}{"…" if len(element_preview) > 240 else ""}</em></small></p>
<p><small>Session file: <code>{out_ref}/session.json</code> — required for step 3.</small></p>
</body></html>""",
        encoding="utf-8",
    )
    return html


def cmd_lock_speed(args: argparse.Namespace, char_name: str, cfg: dict) -> int:
    session_dir = Path(args.from_dir)
    if not session_dir.is_absolute():
        session_dir = PROD_ROOT / session_dir
    session = load_audition_session(session_dir)
    if session.get("character") and session["character"] != char_name:
        sys.exit(f"Session character {session['character']!r} ≠ {char_name!r}")

    locked_speed = float(args.lock_speed)
    roster_speed = float(ELEVENLABS_VOICE_ROSTER[char_name].get("speed") or 0)
    if abs(roster_speed - locked_speed) > 0.005:
        print(
            f"WARNING: roster speed is {roster_speed} but locking {locked_speed}. "
            "Update ELEVENLABS_VOICE_ROSTER in kling_element_voice.py first.",
            file=sys.stderr,
        )

    data = reg.load_character_subjects()
    chars = data.get("characters") or {}
    updated = lock_from_session(char_name, cfg, session, locked_speed)
    chars[char_name] = updated
    data["characters"] = chars
    reg.save_character_subjects(data)

    print(f"Locked {char_name} voice sample:")
    print(f"  session: {session_dir.name}")
    print(f"  speed: {locked_speed}")
    print(f"  audition_line: {updated['audition_line'][:80]}…")
    print(f"  element_sample_lines: {len(updated['element_sample_lines'])} lines")
    print(f"  fingerprint: {updated['voice_sample_lock']['sample_text_fingerprint']}")
    print("\nNext: python3 scripts/setup_all_kling_character_voices.py "
          f"--char {char_name} --force")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ElevenLabs speed ladder before Element register")
    parser.add_argument("--char", required=True, help="Character name (e.g. Chipper)")
    parser.add_argument(
        "--line",
        help="Spoken line for speed ladder (default: first element line or audition_line)",
    )
    parser.add_argument(
        "--element-lines",
        help="Pipe-separated lines for create-voice MP3 (default: char DEFAULT_ELEMENT_SAMPLE_LINES)",
    )
    parser.add_argument(
        "--speeds",
        help="Comma-separated speeds (default: archetype ladder incl. current roster speed)",
    )
    parser.add_argument("--out-dir", help="Override output directory")
    parser.add_argument("--dry-run", action="store_true", help="Write listen.html + session.json only, no API")
    parser.add_argument(
        "--lock-speed",
        type=float,
        help="Persist session → character_subjects voice_sample_lock (requires --from-dir)",
    )
    parser.add_argument(
        "--from-dir",
        help="Speed compare dir containing session.json (for --lock-speed)",
    )
    args = parser.parse_args()

    char_name = args.char.strip()
    if char_name not in ELEVENLABS_VOICE_ROSTER:
        matches = [k for k in ELEVENLABS_VOICE_ROSTER if k.lower() == char_name.lower()]
        if not matches:
            sys.exit(f"Unknown character {char_name!r}. Roster: {list(ELEVENLABS_VOICE_ROSTER)}")
        char_name = matches[0]

    roster = dict(ELEVENLABS_VOICE_ROSTER[char_name])
    subjects = reg.load_character_subjects().get("characters") or {}
    cfg = subjects.get(char_name) or {}

    if args.lock_speed is not None:
        if not args.from_dir:
            sys.exit("--lock-speed requires --from-dir (speed_compare_* directory with session.json)")
        return cmd_lock_speed(args, char_name, cfg)

    element_lines = _parse_element_lines(
        args.element_lines,
        char_name,
        (args.line or cfg.get("audition_line") or "").strip(),
    )
    if not element_lines:
        sys.exit(f"Need --line, --element-lines, or audition_line for {char_name}")

    line = (args.line or element_lines[0]).strip()
    if len(line) < 10:
        sys.exit(f"Audition line too short for {char_name}")

    roster_speed = float(roster.get("speed") or 1.0)
    if args.speeds:
        speeds = sorted({float(s.strip()) for s in args.speeds.split(",") if s.strip()})
    else:
        archetype = CHARACTER_ARCHETYPE.get(char_name, "default")
        speeds = list(ARCHETYPE_SPEED_LADDER.get(archetype, ARCHETYPE_SPEED_LADDER["default"]))
        if roster_speed not in speeds:
            speeds = sorted(set(speeds + [roster_speed]))

    stamp = date.today().isoformat().replace("-", "")
    out_dir = Path(args.out_dir) if args.out_dir else (
        reg.audition_dir() / "samples" / _slug(char_name) / f"speed_compare_{stamp}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{char_name} speed audition")
    print(f"  ladder line: {line[:80]}{'…' if len(line) > 80 else ''}")
    print(f"  element lines: {len(element_lines)}")
    print(f"  roster speed: {roster_speed}")
    print(f"  ladder: {speeds}")
    print(f"  out: {out_dir}\n")

    session_path = write_audition_session(
        out_dir,
        char_name=char_name,
        audition_line=line,
        element_sample_lines=element_lines,
        speeds=speeds,
        roster_speed=roster_speed,
    )
    print(f"  session: {session_path.name}")

    if args.dry_run:
        entries = [
            {"speed": s, "file": f"{_slug(char_name)}_{_speed_label(s, roster_speed)}.mp3",
             "label": _speed_label(s, roster_speed), "ok": True,
             "recommended": abs(s - roster_speed) < 0.01}
            for s in speeds
        ]
        html = write_listen_html(out_dir, char_name, line, element_lines, entries)
        print(f"[dry-run] wrote {html}")
        return 0

    api_key = get_secret("ELEVENLABS_API_KEY")
    if not api_key:
        sys.exit("FATAL: ELEVENLABS_API_KEY required")

    voice_id = roster["elevenlabs_voice_id"]
    base_settings = {
        k: float(roster[k])
        for k in ("stability", "similarity_boost", "style")
        if roster.get(k) is not None
    }
    base_settings["_model"] = roster.get("model") or "eleven_v3"

    entries: list[dict] = []
    ok_count = 0
    for speed in speeds:
        slug = _speed_label(speed, roster_speed)
        dest = out_dir / f"{_slug(char_name)}_{slug}.mp3"
        settings = {**base_settings, "speed": speed}
        success = synthesize(voice_id, line, settings, dest, api_key)
        size = dest.stat().st_size if dest.is_file() else 0
        print(f"  {'OK' if success else 'FAIL'} speed={speed} → {dest.name} ({size} B)")
        entries.append({
            "speed": speed,
            "file": dest.name,
            "label": slug.replace("_", " ").replace("p", "."),
            "ok": success,
            "recommended": abs(speed - roster_speed) < 0.01,
        })
        if success:
            ok_count += 1

    html = write_listen_html(out_dir, char_name, line, element_lines, entries)
    print(f"\nDone: {ok_count}/{len(speeds)} samples")
    print(f"Open: file://{html.resolve()}")
    print(f"\nAfter picking speed: update roster, then:")
    print(f"  python3 scripts/audition_character_voice_speed.py --char {char_name} \\")
    print(f"    --lock-speed <speed> --from-dir {out_dir}")
    return 0 if ok_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
