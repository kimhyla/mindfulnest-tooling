"""Attach video-compare-abc interface to prod_storyboard_beats.selected_option.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import local  # type: ignore

BEATS = "prod_storyboard_beats"

def main():
    c = local()
    r = c._request("GET", f"/fields/{BEATS}/selected_option")
    field = r.get("data", {})
    meta = field.get("meta", {}) or {}
    if meta.get("interface") == "video-compare-abc":
        print("  selected_option already uses video-compare-abc")
        return
    meta["interface"] = "video-compare-abc"
    meta["options"] = {
        "candidatesCollection": "prod_video_candidates",
        "beatFk": "beat_id",
        "pathField": "clip_path",
    }
    meta["special"] = ["m2o"]
    meta["width"] = "full"
    c._request("PATCH", f"/fields/{BEATS}/selected_option", data={"meta": meta})
    print(f"  wired {BEATS}.selected_option -> interface=video-compare-abc")

if __name__ == "__main__":
    main()
