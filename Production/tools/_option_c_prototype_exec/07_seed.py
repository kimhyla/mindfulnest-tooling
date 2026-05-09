"""Seed 33 Luna (M2) beats + A/B/C candidates into local Directus.

Uploads 3 real Event_1 mp4 clips (beat_03 option_A, option_2, option_3) to
directus_files so beat_03 specifically has three real video candidates for
Kim's test script (row #2, 3-up A/B/C compare). Remaining 32 beats use
placeholder candidates (no clip_path) so the Kanban renders at full density
without requiring hundreds of MB of mp4 uploads into a throwaway SQLite DB.

Status distribution tests Kanban density across all 4 swim lanes:
- 10 pending, 8 animating, 7 lipsyncing, 8 approved.

Dialogue text is labeled prototype placeholder to avoid Rule 11 (Source
Fidelity) issues with Kim-authored Luna dialogue.
"""
from __future__ import annotations
import sys, json, mimetypes, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import local, LOCAL_URL  # type: ignore
from credentials_lib.directus import DirectusError  # type: ignore

BEATS = "prod_storyboard_beats"
CANDIDATES = "prod_video_candidates"

EVENT_1_CLIPS = Path(
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/"
    "Production/Event_1/animation_clips"
)

# Placeholder dialogue for prototype only — does NOT represent Luna's actual
# Kim-authored script. Clearly labeled.
BEAT_LINES = [
    "Luna notices the meteor trail.",
    "Luna flaps wildly, sputters.",
    "Luna: 'Owl Peace Prize!'",
    "Luna meets Tessa at the stone.",
    "Luna examines the watching stone.",
    "Luna tries to focus.",
    "Luna gets distracted by shadows.",
    "Luna: 'HOW DID YOU DO THIS!?!?'",
    "Tessa demonstrates now-watching.",
    "Luna practices the technique.",
    "Luna settles into the rhythm.",
    "(Phase A demo – show stillness.)",
    "(Phase A demo – show restlessness.)",
    "(Phase A demo – comparison.)",
    "(Phase B meditation opens.)",
    "(Phase B – observe the breath.)",
    "(Phase B – observe without grabbing.)",
    "(Phase B – micro-attention return.)",
    "(Phase B – widen the frame.)",
    "(Phase B – rest in the frame.)",
    "(Phase B closes; eyes open.)",
    "Luna opens her eyes, quiet.",
    "Luna: 'Stay loose and light.'",
    "The stone awakens, yellow glow.",
    "Luna thanks the child.",
    "Tessa nods to the child.",
    "Chipper arrives with the next hint.",
    "Chipper: 'The next rune waits.'",
    "Luna waves goodbye.",
    "Child returns to the map.",
    "Map shows Watching Stone lit.",
    "Progress bar advances to 2/6.",
    "Module complete.",
]

# Beat-number -> status. Distribution: 10 pending, 8 animating, 7 lipsyncing, 8 approved.
STATUS_MAP = {}
def _fill_status():
    order = ["pending"] * 10 + ["animating"] * 8 + ["lipsyncing"] * 7 + ["approved"] * 8
    for i, s in enumerate(order, start=1):
        STATUS_MAP[i] = s
_fill_status()

# Phase map: beats 1-11 are phase A (setup), 12-21 phase B (meditation), 22-33 phase C (resolution)
def _phase(n):
    return "A" if n <= 11 else ("B" if n <= 21 else "C")

SPEAKERS = [
    "Luna", "Luna", "Luna", "Tessa", "Luna", "Luna", "Luna", "Luna",
    "Tessa", "Luna", "Luna",
    "Cedric", "Cedric", "Cedric", "Cedric", "Cedric", "Cedric", "Cedric",
    "Cedric", "Cedric", "Cedric",
    "Luna", "Luna", "narration", "Luna", "Tessa", "Chipper", "Chipper",
    "Luna", "narration", "narration", "narration", "narration",
]


# ------------ File upload to /files (multipart/form-data) ---------------------

def upload_file(c, source_path: Path, title: str):
    """Upload a local file via Directus multipart /files endpoint."""
    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    # Build multipart body manually (stdlib only)
    boundary = "----optionCprototype7e4b9a"
    headers = {
        "Authorization": f"Bearer {c._token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    mime = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"

    body = b""
    # title part
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="title"\r\n\r\n'
    body += title.encode() + b"\r\n"
    # file part
    body += f"--{boundary}\r\n".encode()
    body += (f'Content-Disposition: form-data; name="file"; '
             f'filename="{source_path.name}"\r\n').encode()
    body += f"Content-Type: {mime}\r\n\r\n".encode()
    with open(source_path, "rb") as f:
        body += f.read()
    body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{LOCAL_URL}/files", data=body, method="POST", headers=headers,
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read())
    return resp["data"]


# ------------ Seed main ------------------------------------------------------

def seed(c):
    existing_beats = c.get(BEATS, limit=1)
    if existing_beats:
        print(f"  seed already present: {len(c.get(BEATS, limit=200))} beats — skipping insert")
        return

    # Upload 3 real Event_1 mp4s for beat_03
    beat3_clips = {
        "A": EVENT_1_CLIPS / "beat_03_option_A.mp4",
        "B": EVENT_1_CLIPS / "beat_03_option_2.mp4",
        "C": EVENT_1_CLIPS / "beat_03_option_3.mp4",
    }
    uploaded = {}
    for label, path in beat3_clips.items():
        print(f"  uploading {path.name} ({path.stat().st_size/1024/1024:.1f} MB)")
        f = upload_file(c, path, f"prototype beat_03 option {label}")
        uploaded[label] = f["id"]

    # Insert 33 beat rows
    beat_rows = []
    for n in range(1, 34):
        dialogue = BEAT_LINES[n - 1]
        speaker = SPEAKERS[n - 1]
        beat = c.create(BEATS, {
            "module_id": 2,  # Luna M2
            "beat_number": n,
            "beat_order": n,
            "phase": _phase(n),
            "speaker": speaker,
            "dialogue_text": f"[prototype placeholder] {dialogue}",
            "status": STATUS_MAP[n],
            "kim_verdict": "pending",
            "lipsync_status": "none",
        })
        beat_rows.append(beat)
        if n in (1, 3, 17, 33):
            print(f"  created beat {n} (status={STATUS_MAP[n]}, phase={_phase(n)})")
    print(f"  created {len(beat_rows)} beats total")

    # Beat_03 gets 3 real candidates
    beat_03_id = beat_rows[2]["id"]
    for label, path_key in (("A", "A"), ("B", "B"), ("C", "C")):
        c.create(CANDIDATES, {
            "beat_id": beat_03_id,
            "option_label": label,
            "source": "event1_reuse",
            "clip_path": f"/assets/{uploaded[path_key]}",
            "duration_ms": 8000,
        })
    print(f"  created 3 real candidates for beat_03")

    # Every OTHER beat gets 3 stub candidates so the 3-up compare view renders
    # something per beat, even if clip_path is empty
    stub_count = 0
    for i, beat in enumerate(beat_rows):
        if i == 2:  # beat_03 already populated
            continue
        for label in ("A", "B", "C"):
            c.create(CANDIDATES, {
                "beat_id": beat["id"],
                "option_label": label,
                "source": "event1_reuse",
                "clip_path": "",  # empty; stub
                "duration_ms": 0,
            })
            stub_count += 1
    print(f"  created {stub_count} stub candidates")

    total_candidates = len(c.get(CANDIDATES, limit=200, fields=["id"]))
    print(f"\n  total: {len(beat_rows)} beats, {total_candidates} candidates (3 real + {total_candidates - 3} stubs)")


def main():
    c = local()
    seed(c)


if __name__ == "__main__":
    main()
