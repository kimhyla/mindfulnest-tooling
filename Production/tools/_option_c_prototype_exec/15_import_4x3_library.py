"""Import Kim's Event_1 4:3 image library into local Directus prod_visual_assets.

Sources:
1. Production/Event_1/_temp_images/*_4x3.png (4 named thumbs)
2. Production/Event_1/gb_solo_c1_cropped_4x3.png
3. Production/Event_1/_tmp_tessa_initial_4x3_upscaled_*.png (Rule 6 upscale variants)
4. Production/Event_1/crops/*.png — only those matching 4:3 aspect
5. Production/Event_1/gemini_stills/crops/*.png — only 4:3
6. storyboard_v37_prod.html embedded base64 4:3 images ≥ 600px shortest side
   and not already imported from disk (dedup by md5).

Excludes: 16:9 crops, square 1:1 crops, archive/, *_tmp_ debug files beyond
the explicitly-listed upscaled variants, and embedded thumbnails below Rule 6.

Registers each as a prod_visual_assets row with asset_type=crop, module_id=1
(Event_1 is Tessa M1), file FK pointing at the uploaded directus_files row.
"""
from __future__ import annotations
import sys, json, hashlib, base64, re, struct, mimetypes, urllib.request, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import local, LOCAL_URL  # type: ignore

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
EVENT_1 = PROJECT / "Production" / "Event_1"
STORYBOARD_HTML = EVENT_1 / "storyboard_v37_prod.html"


def png_dims(raw: bytes):
    try:
        return struct.unpack(">II", raw[16:24])
    except Exception:
        return None, None


def jpg_dims(raw: bytes):
    try:
        i = 0
        while i < len(raw) - 1:
            if raw[i] == 0xFF and raw[i+1] in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", raw[i+5:i+9])
                return w, h
            i += 1
    except Exception:
        pass
    return None, None


def dims_for_bytes(raw: bytes, fmt: str):
    return png_dims(raw) if fmt == "png" else jpg_dims(raw)


def is_4x3(w, h, tol=0.05):
    if not w or not h:
        return False
    return abs(w / h - 4 / 3) < tol


def md5_first(b: bytes, n: int = 65536) -> str:
    return hashlib.md5(b[:n]).hexdigest()


# --- Directus upload via multipart ---

def upload_disk_file(c, source: Path, title: str):
    boundary = "----va4x3import9e4b"
    headers = {
        "Authorization": f"Bearer {c._token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="title"\r\n\r\n'
    body += title.encode() + b"\r\n"
    body += f"--{boundary}\r\n".encode()
    body += (f'Content-Disposition: form-data; name="file"; '
             f'filename="{source.name}"\r\n').encode()
    body += f"Content-Type: {mime}\r\n\r\n".encode()
    body += source.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{LOCAL_URL}/files", data=body, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["data"]


def upload_bytes_file(c, raw: bytes, filename: str, title: str, content_type: str):
    boundary = "----va4x3bytes9e4b"
    headers = {
        "Authorization": f"Bearer {c._token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="title"\r\n\r\n'
    body += title.encode() + b"\r\n"
    body += f"--{boundary}\r\n".encode()
    body += (f'Content-Disposition: form-data; name="file"; '
             f'filename="{filename}"\r\n').encode()
    body += f"Content-Type: {content_type}\r\n\r\n".encode()
    body += raw
    body += f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{LOCAL_URL}/files", data=body, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["data"]


# --- Source collection ---

def list_disk_candidates():
    """Return list of (path, asset_type, source_note)."""
    items = []
    # 4 _temp_images named 4x3 thumbs
    for name in ("tessa_initial_4x3.png", "tessa_closeup_4x3.png",
                 "guidebird_closeup_4x3.png", "gb_sideview_4x3.png"):
        p = EVENT_1 / "_temp_images" / name
        if p.exists():
            items.append((p, "thumbnail", "Event_1/_temp_images (named 4x3 thumbnail)"))

    # gb_solo_c1 full-res crop
    p = EVENT_1 / "gb_solo_c1_cropped_4x3.png"
    if p.exists():
        items.append((p, "crop", "Event_1 root (gb_solo_c1 4:3 crop)"))

    # Upscale variants
    for p in EVENT_1.glob("_tmp_tessa_initial_4x3_upscaled*.png"):
        items.append((p, "upscale", "Event_1 root (Rule 6 upscale of tessa_initial_4x3)"))

    # crops/ — filter by actual aspect
    crops_dir = EVENT_1 / "crops"
    if crops_dir.exists():
        for p in sorted(crops_dir.glob("*.png")):
            raw = p.read_bytes()
            w, h = png_dims(raw)
            if is_4x3(w, h):
                items.append((p, "crop", f"Event_1/crops ({w}x{h} 4:3 match)"))

    # gemini_stills/crops/ — filter
    gemini_crops = EVENT_1 / "gemini_stills" / "crops"
    if gemini_crops.exists():
        for p in sorted(gemini_crops.glob("*.png")):
            raw = p.read_bytes()
            w, h = png_dims(raw)
            if is_4x3(w, h):
                items.append((p, "crop", f"Event_1/gemini_stills/crops ({w}x{h} 4:3 match)"))

    return items


def collect_storyboard_base64(min_shortest_side: int, known_hashes: set):
    """Extract unique 4:3 base64 images from the storyboard HTML whose
    shortest side >= min_shortest_side AND whose content hash is not in
    known_hashes (so we don't double-count disk files)."""
    if not STORYBOARD_HTML.exists():
        print(f"  no storyboard at {STORYBOARD_HTML}")
        return []
    text = STORYBOARD_HTML.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(r"data:image/(png|jpe?g);base64,([A-Za-z0-9+/=]{200,})")
    found = []
    seen_hashes = set()
    for fmt, blob in pattern.findall(text):
        try:
            blob_padded = blob + "=" * ((4 - len(blob) % 4) % 4)
            raw = base64.b64decode(blob_padded)
        except Exception:
            continue
        h = md5_first(raw)
        if h in seen_hashes or h in known_hashes:
            continue
        seen_hashes.add(h)
        w, height = dims_for_bytes(raw, "png" if fmt == "png" else "jpg")
        if not is_4x3(w, height):
            continue
        if not w or not height:
            continue
        if min(w, height) < min_shortest_side:
            continue
        found.append((raw, fmt, w, height, h))
    return found


# --- Registry insert ---

def already_registered(c, filename: str) -> bool:
    rows = c.get("prod_visual_assets",
                 filters={"filename": {"_eq": filename}}, limit=1)
    return bool(rows)


def register(c, *, filename, filepath, asset_type, width, height,
             file_id, source_note, shot_number=None, module_id=1, event_number=1):
    c.create("prod_visual_assets", {
        "module_id": module_id,
        "event_number": event_number,
        "filename": filename,
        "filepath": filepath,
        "asset_type": asset_type,
        "status": "approved",
        "shot_number": shot_number,
        "width": width,
        "height": height,
        "rule6_compliant": bool(width and height and min(width, height) >= 600),
        "file": file_id,
        "source_note": source_note,
    })


def main():
    c = local()

    imported_counts = {"disk_thumbs": 0, "disk_crops": 0, "disk_upscales": 0,
                       "storyboard_base64": 0, "skipped_existing": 0,
                       "skipped_bad_dims": 0}
    known_hashes = set()

    # --- Disk imports ---
    for path, asset_type, note in list_disk_candidates():
        raw = path.read_bytes()
        w, h = png_dims(raw)
        if not w or not h:
            imported_counts["skipped_bad_dims"] += 1
            continue
        known_hashes.add(md5_first(raw))

        filename = path.name
        if already_registered(c, filename):
            imported_counts["skipped_existing"] += 1
            continue

        title = f"{path.stem} (4:3, {w}x{h})"
        file_rec = upload_disk_file(c, path, title)
        register(c, filename=filename, filepath=str(path.relative_to(PROJECT)),
                 asset_type=asset_type, width=w, height=h,
                 file_id=file_rec["id"], source_note=note)
        if asset_type == "thumbnail":
            imported_counts["disk_thumbs"] += 1
        elif asset_type == "upscale":
            imported_counts["disk_upscales"] += 1
        else:
            imported_counts["disk_crops"] += 1
        print(f"  imported {filename}  ({w}x{h} {asset_type})")

    # --- Storyboard base64 (≥256px shortest side so we include mid-res
    # production crops but still skip ≤200 thumbs that are pure UI artifacts;
    # dedupe against disk files via md5_first hash). rule6_compliant boolean
    # is stored on the row so the widget can filter if needed.
    sb = collect_storyboard_base64(min_shortest_side=256, known_hashes=known_hashes)
    for raw, fmt, w, h, digest in sb:
        filename = f"storyboard_embed_{digest[:8]}_{w}x{h}.{fmt}"
        if already_registered(c, filename):
            imported_counts["skipped_existing"] += 1
            continue
        content_type = f"image/{fmt if fmt != 'jpg' else 'jpeg'}"
        file_rec = upload_bytes_file(c, raw, filename, f"storyboard embed {digest[:8]}", content_type)
        register(c, filename=filename, filepath=f"(embedded base64 in storyboard_v37_prod.html)",
                 asset_type="crop", width=w, height=h,
                 file_id=file_rec["id"],
                 source_note=f"storyboard_v37_prod.html base64 ({w}x{h})")
        imported_counts["storyboard_base64"] += 1
        print(f"  imported {filename}  ({w}x{h} from storyboard base64)")

    print("\n=== Import summary ===")
    for k, v in imported_counts.items():
        print(f"  {k}: {v}")
    total = c.get("prod_visual_assets", fields=["id"], limit=500)
    print(f"\nprod_visual_assets now has {len(total)} row(s) total.")


if __name__ == "__main__":
    main()
