#!/usr/bin/env python3
"""Oilfield Job Coherence OS CLI (P2: MicroPulse fiber join).

observe → negotiate free parameters → re-ingest → until coherent or budget.

LOCKED: QC pin (depth mono, required channels for pack, unit sanity).
FREE: align_mode, window_scale, channel_pack, null_policy.

P2: --micropulse joins GAMMA/SHOCK/VIBE/PULSE/TELEM/TEMP/FLOW fibers;
structural depth/time glue (not score-chase).

Never ROP score-chase. Never retune SOP pin mid-run. Never ζ→ROP.
Mirror of handoff_coherence OS v2 without protein adapters.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.types import FreeParams, JobThresholds

logger = logging.getLogger("job_coherence")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Oilfield Job Coherence OS: negotiate align/window/pack/null until "
            "job routine fixed-point. QC pin locked. Optional MicroPulse join. "
            "Not ROP score-chase."
        )
    )
    p.add_argument(
        "--las",
        type=Path,
        default=None,
        help="path to EDR LAS 2.0 file",
    )
    p.add_argument(
        "--micropulse",
        type=Path,
        default=None,
        help="MicroPulse memory path: directory of CSVs or a single CSV fiber",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("out/job_os"),
        help="root for cycle_* dirs + COHERENCE.json (OS: parent of run_id/)",
    )
    p.add_argument("--max-rounds", type=int, default=6)
    p.add_argument(
        "--os",
        action="store_true",
        help="OS mode: run_id/, RUN.json, ledger.jsonl, PARTNER_RECIPE, LATEST",
    )
    p.add_argument(
        "--resume",
        type=Path,
        default=None,
        help="resume incomplete OS run directory (contains RUN.json)",
    )
    p.add_argument(
        "--stability-k",
        type=int,
        default=1,
        help="fixed-point: is_solved ∧ empty board for K consecutive cycles",
    )
    p.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="optional explicit OS run_id (default: UTC stamp)",
    )
    p.add_argument(
        "--align-mode",
        type=str,
        default="depth_primary",
        choices=("none", "depth_primary", "time_primary", "survey_anchor"),
    )
    p.add_argument("--window-scale", type=int, default=1)
    p.add_argument(
        "--channel-pack",
        type=str,
        default="surface_min",
        choices=("surface_min", "surface_full", "mwd_full", "job_union"),
    )
    p.add_argument(
        "--null-policy",
        type=str,
        default="mark_only",
        choices=("drop", "hold_last", "mark_only"),
    )
    p.add_argument(
        "--min-align-score",
        type=float,
        default=0.5,
        help="min align/glue score for is_solved",
    )
    p.add_argument(
        "--max-physics-fail",
        type=int,
        default=0,
        help="max allowed physics FAIL counts",
    )
    p.add_argument(
        "--depth-mono-eps",
        type=float,
        default=1e-6,
        help="locked pin tolerance for depth monotonicity (config, not free)",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if args.resume is not None:
        if not (args.resume / "RUN.json").is_file():
            logger.error("resume path missing RUN.json: %s", args.resume)
            return 2
        try:
            result = run_job_coherence_loop(
                las_path=args.las,
                micropulse_path=args.micropulse,
                out_root=args.out_dir,
                max_rounds=int(args.max_rounds),
                resume_dir=args.resume,
                stability_k=int(args.stability_k),
                os_mode=True,
            )
        except FileNotFoundError as exc:
            logger.error("%s", exc)
            return 2
        except ValueError as exc:
            logger.error("%s", exc)
            return 2
    else:
        if args.las is None or not args.las.is_file():
            logger.error("--las required and must exist (got %s)", args.las)
            return 2
        if args.micropulse is not None and not args.micropulse.exists():
            logger.error("--micropulse path not found: %s", args.micropulse)
            return 2
        try:
            result = run_job_coherence_loop(
                las_path=args.las,
                micropulse_path=args.micropulse,
                out_root=args.out_dir,
                initial=FreeParams(
                    align_mode=args.align_mode,
                    window_scale=int(args.window_scale),
                    channel_pack=args.channel_pack,
                    null_policy=args.null_policy,
                ),
                thresholds=JobThresholds(
                    min_export_ok_fraction=1.0,
                    max_physics_fail=int(args.max_physics_fail),
                    min_align_score=float(args.min_align_score),
                    require_verify_ok=True,
                    require_pin=True,
                    depth_mono_eps=float(args.depth_mono_eps),
                ),
                max_rounds=int(args.max_rounds),
                stability_k=int(args.stability_k),
                os_mode=bool(args.os),
                run_id=args.run_id,
            )
        except FileNotFoundError as exc:
            logger.error("%s", exc)
            return 2
        except ValueError as exc:
            logger.error("%s", exc)
            return 2

    if result.get("stop_reason") == "pin_fail":
        print(
            json.dumps(
                {
                    "solved": False,
                    "stop_reason": "pin_fail",
                    "out": result.get("out_root"),
                },
                indent=2,
            )
        )
        return 4

    print(
        json.dumps(
            {
                "solved": result.get("solved"),
                "stop_reason": result.get("stop_reason"),
                "n_rounds": result.get("n_rounds"),
                "run_id": result.get("run_id"),
                "os_mode": result.get("os_mode"),
                "stability_k": result.get("stability_k"),
                "final_params": result.get("final_params"),
                "partner_recipe": result.get("partner_recipe"),
                "pin_ok": (result.get("pin_locked") or {}).get("last_ok"),
                "micropulse_kinds": result.get("micropulse_kinds"),
                "out": result.get("out_root"),
                "note": "pin locked; free params only; OS fixed-point K; glue structural; not ROP",
            },
            indent=2,
        )
    )
    return 0 if result.get("solved") else 1


if __name__ == "__main__":
    raise SystemExit(main())
