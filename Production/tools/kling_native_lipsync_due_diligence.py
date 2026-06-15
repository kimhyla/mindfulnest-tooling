#!/usr/bin/env python3
"""Full QA matrix for native Kling lipsync wrapper replacement.

Runs (or reuses) classified experiment cases and writes a single due-diligence
report under Event_1/kling_native_lipsync_experiments/_due_diligence_<stamp>/.

Never approves beats. Never writes approval fields.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROD = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(PROD) not in sys.path:
    sys.path.insert(0, str(PROD))

import beat_generator as bg_sidecar  # noqa: E402
from kling_native_lipsync_experiment import (  # noqa: E402
    PASS_MIN_DIMENSION,
    probe_media,
    run_experiment,
    run_schema_discovery,
)
from kling_native_lipsync_adapters import route_statuses  # noqa: E402
from lib.paths import EVENT_DIR  # noqa: E402


EVENT1 = Path(EVENT_DIR(1))
TESSA_G0 = EVENT1 / "kling_o3_clips/bg_arc1_event1_pre_tessa_o3_canonical_g0.mp4"
BEAT_10_AUDIO = (
    EVENT1
    / "story_scene_tts_v2/storyboard_v59_prod/line_10_arlo_voice_lipsync_padded.mp3"
)

REUSE_MANIFESTS = {
    "DD-01_arlo_wavespeed_control": EVENT1
    / "kling_native_lipsync_experiments/bg_arc1_event1_pre_beat_10/control_wavespeed_20260610t2042z/manifest.json",
    "DD-02_arlo_native_lip_sync_url": EVENT1
    / "kling_native_lipsync_experiments/bg_arc1_event1_pre_beat_10/native_kling_arlo_post_purchase_20260610t2300z/manifest.json",
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def classify_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    raw_profile = manifest.get("raw_profile") or {}
    poll = manifest.get("poll") or {}
    passed = manifest.get("passed_gate")
    if passed is None:
        passed = bool(
            raw_profile.get("has_audio")
            and int(raw_profile.get("min_dimension") or 0) >= PASS_MIN_DIMENSION
        )
    status = manifest.get("status")
    error_code = manifest.get("error_code")
    if status == "passed" or passed:
        bucket = "GATE_PASS"
    elif error_code == "PROVIDER_RAW_GATE_FAILED":
        bucket = "PROVIDER_OK_GATE_FAIL"
    elif error_code == "provider_billing_or_auth_error":
        bucket = "BILLING_AUTH"
    elif poll.get("error") or manifest.get("error"):
        bucket = "PROVIDER_REJECT"
    elif status == "failed":
        bucket = "FAILED"
    else:
        bucket = "UNKNOWN"
    return {
        "bucket": bucket,
        "passed_gate": passed,
        "status": status,
        "error": manifest.get("error") or poll.get("error"),
        "error_code": error_code,
        "raw_min_dimension": raw_profile.get("min_dimension"),
        "raw_has_audio": raw_profile.get("has_audio"),
        "route_id": manifest.get("route_id"),
        "provider": manifest.get("provider"),
    }


def load_or_run_case(
    *,
    case_id: str,
    route_id: str,
    output_root: Path,
    beat_id: str | None = None,
    input_video: Path | None = None,
    input_audio: Path | None = None,
    reuse_manifest: Path | None = None,
    timeout_s: int = 900,
    run_live: bool,
) -> dict[str, Any]:
    attempt_id = f"{case_id.lower()}_{utc_stamp()}"
    if reuse_manifest and reuse_manifest.is_file():
        manifest = json.loads(reuse_manifest.read_text(encoding="utf-8"))
        return {
            "case_id": case_id,
            "mode": "reused_manifest",
            "manifest_path": str(reuse_manifest),
            "manifest": manifest,
            "classification": classify_manifest(manifest),
        }
    if not run_live:
        return {
            "case_id": case_id,
            "mode": "skipped",
            "reason": "no reuse manifest and --run-live not set",
        }
    manifest = run_experiment(
        route_id=route_id,
        beat_id=beat_id,
        input_video=input_video,
        input_audio=input_audio,
        attempt_id=attempt_id,
        output_root=output_root,
        timeout_s=timeout_s,
        return_on_fail=True,
    )
    manifest_path = Path(manifest["work_dir"]) / "manifest.json"
    return {
        "case_id": case_id,
        "mode": "live",
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "classification": classify_manifest(manifest),
    }


def build_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "DD-01",
            "name": "arlo_wavespeed_control",
            "route_id": "wavespeed_kling_lipsync_baseline",
            "beat_id": "bg_arc1_event1_pre_beat_10",
            "reuse_key": "DD-01_arlo_wavespeed_control",
            "purpose": "Control: WaveSpeed wrapper lipsyncs Arlo but raw sub-720.",
        },
        {
            "case_id": "DD-02",
            "name": "arlo_native_lip_sync_url",
            "route_id": "native_kling_lip_sync_a2v",
            "beat_id": "bg_arc1_event1_pre_beat_10",
            "reuse_key": "DD-02_arlo_native_lip_sync_url",
            "purpose": "Primary native route parity vs WaveSpeed on identical beat_10 input.",
        },
        {
            "case_id": "DD-03",
            "name": "arlo_native_lip_sync_b64",
            "route_id": "native_kling_lip_sync_a2v_b64",
            "beat_id": "bg_arc1_event1_pre_beat_10",
            "purpose": "Native route with audio_type=file base64 transport.",
        },
        {
            "case_id": "DD-04",
            "name": "tessa_native_lip_sync_url",
            "route_id": "native_kling_lip_sync_a2v",
            "input_video": TESSA_G0,
            "input_audio": BEAT_10_AUDIO,
            "purpose": "Humanoid control clip on native /v1/videos/lip-sync (gate proof path).",
        },
        {
            "case_id": "DD-05",
            "name": "tessa_native_identify_face_advanced",
            "route_id": "native_kling_identify_face_advanced_lipsync",
            "input_video": TESSA_G0,
            "input_audio": BEAT_10_AUDIO,
            "purpose": "Secondary native route; not Beat Gen production shape.",
        },
    ]


def run_due_diligence(*, event_dir: Path, run_live: bool, timeout_s: int) -> dict[str, Any]:
    stamp = utc_stamp()
    output_root = event_dir / "kling_native_lipsync_experiments" / f"_due_diligence_{stamp}"
    schema = run_schema_discovery(output_root / "schema_discovery")
    results: list[dict[str, Any]] = []
    for case in build_cases():
        reuse = REUSE_MANIFESTS.get(case.get("reuse_key", ""))
        result = load_or_run_case(
            case_id=case["case_id"],
            route_id=case["route_id"],
            output_root=output_root,
            beat_id=case.get("beat_id"),
            input_video=case.get("input_video"),
            input_audio=case.get("input_audio"),
            reuse_manifest=reuse,
            timeout_s=timeout_s,
            run_live=run_live,
        )
        result["name"] = case["name"]
        result["purpose"] = case["purpose"]
        results.append(result)

    gate_pass = [r for r in results if (r.get("classification") or {}).get("bucket") == "GATE_PASS"]
    provider_ok = [r for r in results if (r.get("classification") or {}).get("bucket") == "PROVIDER_OK_GATE_FAIL"]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_root": str(output_root),
        "pass_min_dimension": PASS_MIN_DIMENSION,
        "promotion_ready": bool(
            any(
                (r.get("classification") or {}).get("bucket") == "GATE_PASS"
                and (r.get("name") or "").startswith("arlo")
                for r in results
            )
        ),
        "summary": {
            "cases_total": len(results),
            "gate_pass": len(gate_pass),
            "provider_ok_gate_fail": len(provider_ok),
            "provider_reject": sum(1 for r in results if (r.get("classification") or {}).get("bucket") == "PROVIDER_REJECT"),
            "skipped": sum(1 for r in results if r.get("mode") == "skipped"),
        },
        "route_statuses": schema["route_statuses"],
        "cases": results,
        "conclusions": [
            "Beat Gen production lipsync = Kling via WaveSpeed kwaivgi/kling-lipsync/audio-to-video.",
            "Native Developer API primary target = POST /v1/videos/lip-sync (mode audio2video).",
            "identify-face + advanced-lip-sync is a secondary route, not production parity shape.",
            "Promotion blocked until a native route returns raw min(width,height) >= 720 with audio.",
        ],
    }
    write_json(output_root / "qa_report.json", report)
    write_json(output_root / "qa_report_public.json", {
        k: v for k, v in report.items() if k != "cases"
    } | {
        "cases": [
            {
                "case_id": c.get("case_id"),
                "name": c.get("name"),
                "mode": c.get("mode"),
                "classification": c.get("classification"),
                "manifest_path": c.get("manifest_path"),
            }
            for c in results
        ]
    })
    return report


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-dir", type=Path, default=EVENT1)
    parser.add_argument("--run-live", action="store_true", help="Execute live provider cases (costs credits).")
    parser.add_argument("--timeout-s", type=int, default=900)
    args = parser.parse_args()
    bg_sidecar.init_bg_paths(args.event_dir)
    report = run_due_diligence(event_dir=args.event_dir, run_live=args.run_live, timeout_s=args.timeout_s)
    print(json.dumps(report["summary"], indent=2))
    print(f"report={report['output_root']}/qa_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
