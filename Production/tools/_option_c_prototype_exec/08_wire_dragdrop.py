"""Attach the dragdrop interface to prod_storyboard_beats.image_override and
seed ~8 gallery images (Tessa stills from Event_1) into directus_files.
"""
from __future__ import annotations
import sys, json, mimetypes, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import local, LOCAL_URL  # type: ignore
from credentials_lib.directus import DirectusError  # type: ignore

BEATS = "prod_storyboard_beats"

EVENT_1_ROOT = Path(
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/"
    "Production/Event_1"
)

GALLERY_IMAGES = [
    (EVENT_1_ROOT / "m1_phase_b_still_v3a.png", "Tessa still v3a"),
    (EVENT_1_ROOT / "m1_phase_b_still_v3b.png", "Tessa still v3b"),
    (EVENT_1_ROOT / "m1_phase_b_still_v3c.png", "Tessa still v3c"),
    (EVENT_1_ROOT / "m1_phase_b_still_rub_v5d.png", "Tessa rub v5d"),
    (EVENT_1_ROOT / "m1_phase_b_still_rub_v5e.png", "Tessa rub v5e"),
    (EVENT_1_ROOT / "m1_phase_b_still_rub_v5f.png", "Tessa rub v5f"),
    (EVENT_1_ROOT / "beat11_frame_09.png", "Tessa beat11 frame"),
    (EVENT_1_ROOT / "shot3_keyframe.png", "Tessa shot3 keyframe"),
]


def upload_file(c, source_path: Path, title: str):
    boundary = "----optionCgallery9e4b"
    headers = {
        "Authorization": f"Bearer {c._token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    mime = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"

    body = b""
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="title"\r\n\r\n'
    body += title.encode() + b"\r\n"
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
        return json.loads(r.read())["data"]


def seed_gallery(c):
    existing = c._request("GET", "/files", params={
        "filter[type][_starts_with]": "image/", "limit": 100,
    }).get("data", [])
    if len(existing) >= 8:
        print(f"  gallery already has {len(existing)} images — skipping uploads")
        return
    for path, title in GALLERY_IMAGES:
        if not path.exists():
            print(f"  skip missing {path.name}")
            continue
        try:
            upload_file(c, path, title)
            print(f"  uploaded gallery: {path.name}")
        except Exception as e:
            print(f"  upload failed {path.name}: {e}")


def wire_image_override(c):
    r = c._request("GET", f"/fields/{BEATS}/image_override")
    field = r.get("data", {})
    meta = field.get("meta", {}) or {}
    current_iface = meta.get("interface")
    if current_iface == "image-dragdrop":
        print("  image_override already uses image-dragdrop")
        return
    meta["interface"] = "image-dragdrop"
    meta["options"] = {"galleryLimit": 12}
    # Keep special=['file'] so Directus still treats the uuid as a file FK
    meta["special"] = ["file"]
    c._request("PATCH", f"/fields/{BEATS}/image_override", data={"meta": meta})
    print(f"  wired {BEATS}.image_override -> interface=image-dragdrop (was {current_iface})")


def main():
    c = local()
    seed_gallery(c)
    wire_image_override(c)
    # Summary
    r = c._request("GET", "/files", params={
        "filter[type][_starts_with]": "image/", "limit": 100,
    }).get("data", [])
    print(f"\n  gallery has {len(r)} images")


if __name__ == "__main__":
    main()
