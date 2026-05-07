#!/usr/bin/env python3
"""
Path B patch: Inject a new image into a storyboard's image library and
optionally assign it to a beat line — WITHOUT rebuilding the storyboard.

This is a surgical, non-destructive edit:
  1. Adds a full-res <div class="ic"> to the gallery
  2. Adds a TH["key"] thumbnail entry
  3. Optionally reassigns a beat's i:"key" in the L array
  4. Verifies ALL existing base64 images are preserved byte-identical

Usage:
  python3 inject_image_into_storyboard.py <image_path> <storyboard_html> [--assign-beat N] [--output out.html]

Example:
  python3 inject_image_into_storyboard.py crops/beat02_guidebird_closeup.png storyboard_v28_prod.html --assign-beat 2 --output storyboard_v29_prod.html
"""
import argparse
import base64
import io
import re
import sys
from pathlib import Path


THUMB_SIZE = 80  # px, matches existing storyboard thumbnails


def make_thumbnail_b64(img_path: Path, size: int = THUMB_SIZE) -> str:
    """Create a small thumbnail and return as base64 data URI."""
    try:
        from PIL import Image
        img = Image.open(img_path)
        # Maintain aspect ratio
        ratio = size / min(img.width, img.height)
        new_w = int(img.width * ratio)
        new_h = int(img.height * ratio)
        thumb = img.resize((new_w, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        thumb.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except ImportError:
        print("WARNING: Pillow not available — using full image as thumbnail (larger file)")
        raw = img_path.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:image/png;base64,{b64}"


def derive_key(filename: str) -> str:
    """Convert filename to storyboard key (no extension, spaces→underscores)."""
    stem = Path(filename).stem
    return stem.replace(" ", "_")


def inject(html: str, img_path: Path, assign_beat: int | None, key_override: str | None) -> str:
    key = key_override or derive_key(img_path.name)
    print(f"Image key: {key}")

    # --- 1. Snapshot existing base64 images for verification ---
    existing_b64 = re.findall(r'data:image/[^"]{100,}', html)
    print(f"Existing base64 images: {len(existing_b64)}")

    # --- 2. Base64-encode the full-res image ---
    raw = img_path.read_bytes()
    full_b64 = base64.b64encode(raw).decode("ascii")
    full_uri = f"data:image/png;base64,{full_b64}"
    print(f"Full image: {len(raw):,} bytes → {len(full_b64):,} chars base64")

    # --- 3. Generate thumbnail ---
    thumb_uri = make_thumbnail_b64(img_path)
    print(f"Thumbnail generated")

    # --- 4. Insert gallery <div class="ic"> ---
    # Find the closing </div></div> after the last .ic div (end of .gg gallery grid)
    ic_positions = [m.end() for m in re.finditer(r'<div class="ic"><img[^>]+><p>[^<]+</p></div>', html)]
    if not ic_positions:
        print("ERROR: Could not find any .ic gallery divs")
        sys.exit(1)
    last_ic_end = ic_positions[-1]

    gallery_entry = f'\n<div class="ic"><img src="{full_uri}"><p>{img_path.name}</p></div>'
    html = html[:last_ic_end] + gallery_entry + html[last_ic_end:]
    print(f"Inserted gallery entry after position {last_ic_end}")

    # --- 5. Insert into IN (image name map — required for drag-drop) ---
    display_name = img_path.name
    in_match = re.search(r'(var IN\s*=\s*\{[^}]*)"none"', html)
    if in_match:
        insert_pos = in_match.end() - len('"none"')
        in_entry = f'"{key}": "{display_name}", '
        html = html[:insert_pos] + in_entry + html[insert_pos:]
        print(f"Inserted IN[\"{key}\"]")

    # --- 6. Insert TH["key"] thumbnail ---
    # Find the last TH["..."] assignment and insert after it
    th_matches = list(re.finditer(r'TH\["[^"]+"\]\s*=\s*"[^"]*"\s*;', html))
    if not th_matches:
        print("ERROR: Could not find TH dictionary entries")
        sys.exit(1)
    last_th_end = th_matches[-1].end()

    th_entry = f'\nTH["{key}"]="{thumb_uri}";'
    html = html[:last_th_end] + th_entry + html[last_th_end:]
    print(f"Inserted TH[\"{key}\"] thumbnail")

    # --- 6. Optionally reassign a beat's i: value ---
    if assign_beat is not None:
        # L array is 0-indexed, beats are 1-indexed
        # Find the Nth entry in the L array
        l_match = re.search(r'var L\s*=\s*\[', html)
        if not l_match:
            print("ERROR: Could not find L array")
            sys.exit(1)

        # Parse L array entries — each is {...}
        l_start = l_match.end()
        # Find entries by counting { } pairs
        entries = []
        depth = 0
        entry_start = None
        for i in range(l_start, len(html)):
            if html[i] == '{':
                if depth == 0:
                    entry_start = i
                depth += 1
            elif html[i] == '}':
                depth -= 1
                if depth == 0 and entry_start is not None:
                    entries.append((entry_start, i + 1))
                    entry_start = None
            elif html[i] == ']' and depth == 0:
                break

        beat_idx = assign_beat - 1  # Convert 1-based beat to 0-based index
        if beat_idx < 0 or beat_idx >= len(entries):
            print(f"ERROR: Beat {assign_beat} out of range (L has {len(entries)} entries)")
            sys.exit(1)

        entry_start, entry_end = entries[beat_idx]
        entry_text = html[entry_start:entry_end]
        old_i = re.search(r'i:"([^"]*)"', entry_text)
        if old_i:
            old_key = old_i.group(1)
            new_entry = entry_text[:old_i.start()] + f'i:"{key}"' + entry_text[old_i.end():]
            html = html[:entry_start] + new_entry + html[entry_end:]
            print(f"Reassigned beat {assign_beat} (L[{beat_idx}]): i:\"{old_key}\" → i:\"{key}\"")
        else:
            print(f"WARNING: No i:\"...\" found in L[{beat_idx}], skipping assignment")

    # --- 7. Verify all pre-existing base64 images are preserved ---
    new_b64 = re.findall(r'data:image/[^"]{100,}', html)
    # The new image adds 2 entries (full + thumbnail), so expect existing + 2
    expected_count = len(existing_b64) + 2
    if len(new_b64) != expected_count:
        print(f"WARNING: Expected {expected_count} base64 images, found {len(new_b64)}")

    # Verify each original image is still present byte-identical
    for i, orig in enumerate(existing_b64):
        if orig not in html:
            print(f"CRITICAL: Existing base64 image {i} was CORRUPTED or LOST. Aborting.")
            sys.exit(1)
    print(f"Verified: all {len(existing_b64)} original base64 images preserved byte-identical")

    return html


def main():
    parser = argparse.ArgumentParser(description="Inject image into storyboard library")
    parser.add_argument("image", type=Path, help="Path to PNG image to inject")
    parser.add_argument("storyboard", type=Path, help="Path to storyboard HTML")
    parser.add_argument("--assign-beat", type=int, default=None,
                        help="Beat number (1-based) to assign this image to")
    parser.add_argument("--key", type=str, default=None,
                        help="Override the image key (default: derived from filename)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output path (default: overwrite input)")

    args = parser.parse_args()

    if not args.image.exists():
        print(f"ERROR: Image not found: {args.image}")
        sys.exit(1)
    if not args.storyboard.exists():
        print(f"ERROR: Storyboard not found: {args.storyboard}")
        sys.exit(1)

    html = args.storyboard.read_text(encoding="utf-8")
    html = inject(html, args.image, args.assign_beat, args.key)

    output = args.output or args.storyboard
    output.write_text(html, encoding="utf-8")

    size_kb = output.stat().st_size / 1024
    print(f"\nDone: {output.name} ({size_kb:,.0f} KB)")


if __name__ == "__main__":
    main()
