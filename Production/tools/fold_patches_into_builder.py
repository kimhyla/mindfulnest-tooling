#!/usr/bin/env python3
"""
fold_patches_into_builder.py
============================
Folds all storyboard_v44_prod.html patch layers back into build_storyboard.py
so every future storyboard is born with full functionality.

Groups:
  GROUP 1 — Steps 1-3: SERVER vars, regen audio button, --with-extras default-on
  GROUP 2 — Steps 4-22: Extract 19 patch blocks from v44, embed in append_extras_tabs()

Run once from the project root:
    python3 Production/tools/fold_patches_into_builder.py

Creates a backup at build_storyboard.py.pre_fold_backup before writing.
"""

import base64
import os
import re
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))

BUILDER = os.path.join(PROJECT_ROOT, "Production", "tools", "build_storyboard.py")
V44_HTML = os.path.join(PROJECT_ROOT, "Production", "Event_1", "storyboard_v44_prod.html")
BACKUP   = BUILDER + ".pre_fold_backup"


def main():
    # ── Read sources ──────────────────────────────────────────────────────────
    with open(BUILDER, "r", encoding="utf-8") as f:
        builder = f.read()
    with open(V44_HTML, "r", encoding="utf-8") as f:
        v44 = f.read()

    # ── Backup ────────────────────────────────────────────────────────────────
    shutil.copy(BUILDER, BACKUP)
    print(f"✓ Backup: {os.path.basename(BACKUP)}")

    # =========================================================================
    # GROUP 1 — Step 1: Add _TOP_SERVER / SERVER vars after `var TH={};`
    # =========================================================================
    OLD_TH = "parts.append('var TH={};')"
    NEW_TH = (
        "parts.append('var TH={};')\n"
        "    parts.append('var _TOP_SERVER=\"http://localhost:5111\";')\n"
        "    parts.append('var SERVER=_TOP_SERVER; /* SERVER-SCOPE-V1: global alias for render() fetch calls */')"
    )
    assert OLD_TH in builder, "Step 1 FAIL: anchor 'var TH={}' not found in builder"
    builder = builder.replace(OLD_TH, NEW_TH, 1)
    print("✓ Step 1: SERVER-SCOPE-V1 vars injected after var TH={}")

    # =========================================================================
    # GROUP 1 — Step 2: Add regen audio button (REGEN-TIMEOUT-V1) to render()
    # Extract the rbtn block from v44 (Decision 181 comment → ptb.appendChild(rbtn);)
    # =========================================================================
    rbtn_match = re.search(
        r'/\* Decision 181.*?ptb\.appendChild\(rbtn\);',
        v44, re.DOTALL
    )
    assert rbtn_match, "Step 2 FAIL: rbtn block not found in v44 (Decision 181 anchor)"
    rbtn_block = rbtn_match.group(0)

    # Inject between ptb.appendChild(pbtn); and r.appendChild(ptb);
    OLD_PTB = 'ptb.appendChild(pbtn);r.appendChild(ptb);'
    NEW_PTB = 'ptb.appendChild(pbtn);\n' + rbtn_block + '\nr.appendChild(ptb);'
    assert OLD_PTB in builder, "Step 2 FAIL: anchor 'ptb.appendChild(pbtn);r.appendChild(ptb);' not found"
    builder = builder.replace(OLD_PTB, NEW_PTB, 1)
    print("✓ Step 2: REGEN-TIMEOUT-V1 regen audio button added to render()")

    # =========================================================================
    # GROUP 1 — Step 3: --with-extras → default-on, add --no-extras opt-out
    # =========================================================================
    OLD_EXTRAS = (
        'parser.add_argument("--with-extras", action="store_true",\n'
        '                        help="Append Beat Generator + Cropper tabs to the built storyboard HTML (Path A)")'
    )
    NEW_EXTRAS = (
        'parser.add_argument("--no-extras", dest="with_extras", action="store_false",\n'
        '                        help="Skip Beat Generator + Cropper + patch tabs (Path A extras off)")\n'
        '    parser.set_defaults(with_extras=True)'
    )
    assert OLD_EXTRAS in builder, "Step 3 FAIL: --with-extras anchor not found"
    builder = builder.replace(OLD_EXTRAS, NEW_EXTRAS, 1)
    print("✓ Step 3: --with-extras is now default-on; --no-extras added as opt-out")

    # =========================================================================
    # GROUP 2 — Extract patch section from v44 (FIX-C through CRFIX-BGACCEPT-V12)
    # =========================================================================
    FIX_C_MARKER = "// FIX-C STATIC STILLS PATCH"
    fix_c_idx = v44.find(FIX_C_MARKER)
    assert fix_c_idx != -1, "GROUP 2 FAIL: FIX-C marker not found in v44"

    # Opening <script> tag just before FIX-C
    script_open_idx = v44.rfind("<script>", 0, fix_c_idx)
    assert script_open_idx != -1, "GROUP 2 FAIL: <script> tag before FIX-C not found"

    # Closing </script> just before </html>
    html_end_idx = v44.rfind("</html>")
    last_close_idx = v44.rfind("</script>", 0, html_end_idx)
    assert last_close_idx != -1, "GROUP 2 FAIL: closing </script> not found"
    patch_section = v44[script_open_idx : last_close_idx + len("</script>")]

    # Sanity-check: verify all 19 expected blocks are present
    expected_blocks = [
        "FIX-C STATIC STILLS", "FIX-C3b", "FIX-D BG PANEL", "FIX-F",
        "FIX-G SEGMENT", "FIX-H:", "FIX-H2:", "FIXLIB-FINAL",
        "LIBDROP-TO-SLOT", "LIBFIX-V2", "LIBFIX-V3",
        "CRFIX-LIBFIX-V4", "CRFIX-LIBFIX-V5", "CRFIX-LIBFIX-V6",
        "CRFIX-LIBFIX-V8", "CRFIX-LIBFIX-V9", "CRFIX-LIBFIX-V10",
        "CRFIX-BGACCEPT-V11", "CRFIX-BGACCEPT-V12",
    ]
    missing = [b for b in expected_blocks if b not in patch_section]
    if missing:
        print(f"  WARNING: missing blocks in patch section: {missing}")
    else:
        print(f"  All 19 expected patch blocks present in extracted section")

    patch_chars = len(patch_section)
    print(f"✓ GROUP 2: Extracted {patch_chars:,} chars of patches from v44")

    # Encode as base64 so embedding in Python source is escape-free
    patch_b64 = base64.b64encode(patch_section.encode("utf-8")).decode("ascii")

    # =========================================================================
    # GROUP 2 — Inject into append_extras_tabs() before the final write
    # =========================================================================
    OLD_WRITE = (
        '    with open(output_path, "w", encoding="utf-8") as f:\n'
        '        f.write(html)\n'
        '    print(f"  [--with-extras] Beat Generator + Cropper injected. Size: {len(html)//1024}KB")\n'
        '    return output_path'
    )
    NEW_WRITE = (
        '    # GROUP 2 — Inject v44 CRFIX/LIBFIX patch blocks before </body>\n'
        '    # Stored as base64 to avoid Python string-escape fragility.\n'
        '    _PATCHES_B64 = (\n'
        '        "' + patch_b64 + '"\n'
        '    )\n'
        '    _patches_html = base64.b64decode(_PATCHES_B64).decode("utf-8")\n'
        '    if "</body>" in html:\n'
        '        html = html.replace("</body>", _patches_html + "\\n</body>", 1)\n'
        '    else:\n'
        '        html += _patches_html\n'
        '\n'
        '    with open(output_path, "w", encoding="utf-8") as f:\n'
        '        f.write(html)\n'
        '    print(f"  [--with-extras] Beat Generator + Cropper + v44 patches injected. Size: {len(html)//1024}KB")\n'
        '    return output_path'
    )
    assert OLD_WRITE in builder, "GROUP 2 FAIL: 'with open' anchor not found in append_extras_tabs()"
    builder = builder.replace(OLD_WRITE, NEW_WRITE, 1)
    print("✓ Steps 4-22: v44 patches embedded in append_extras_tabs() via base64")

    # =========================================================================
    # Write modified builder
    # =========================================================================
    with open(BUILDER, "w", encoding="utf-8") as f:
        f.write(builder)

    new_lines = builder.count("\n")
    print(f"\n✅ Done. Modified build_storyboard.py ({new_lines} lines)")
    print(f"   Backup: {BACKUP}")
    print(f"\nNext: python3 {os.path.basename(BUILDER)} --smoke-test")
    print(f"      python3 {os.path.basename(BUILDER)} --config <minimal.json> --output /tmp/test_storyboard.html")
    print(f"      python3 {os.path.basename(BUILDER)} --audit-previous Production/Event_1/storyboard_v44_prod.html")


if __name__ == "__main__":
    main()
