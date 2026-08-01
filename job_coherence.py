#!/usr/bin/env python3
"""Oilfield Job Coherence OS CLI (P5: EOW package ship + recipe attach).

observe → negotiate free parameters → re-ingest → until coherent or budget.

LOCKED: QC pin (depth mono, required channels for pack, unit sanity).
FREE: align_mode, window_scale, channel_pack, null_policy, survey_gate, regime_mode.

P2: --micropulse joins GAMMA/SHOCK/VIBE/PULSE/TELEM/TEMP/FLOW fibers;
structural depth/time glue (not score-chase).

P3: survey stalk (B) — parse MicroPulse SURVEY or --survey CSV;
QC total G / MagF; optional discrete holonomy; --require-survey gates is_solved.
Never invent Inc/Azi.

P4: regime stalk (C) — windowed H0 on SSSI/TOR/RPM; shock exceedance;
--with-regime / --with-science dual-gate (native vs time-scramble) info only;
--require-regime optional commercial gate. Science score never sets SOLVED alone.

P5: --eow-package PATH after SOLVED (or with full run then ship);
writes eow/PACKAGE_INDEX.json + SHIP.md with integrity hashes; references
PARTNER_RECIPE. Refuse unless SOLVED unless --force-ship (UNSOLVED_SHIP banner).

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

from realm.job_os.audit import audit_job_run, audit_rotation_batch
from realm.job_os.catalog import write_job_os_catalog
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.rotation import run_job_rotation
from realm.job_os.types import FreeParams, JobThresholds

logger = logging.getLogger("job_coherence")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Oilfield Job Coherence OS: negotiate align/window/pack/null/survey_gate/"
            "regime_mode until job routine fixed-point. QC pin locked. "
            "Optional MicroPulse + survey + regime science + EOW ship. "
            "Not ROP score-chase."
        )
    )
    p.add_argument(
        "--catalog",
        action="store_true",
        help="scan --out-dir for Job OS runs; write INDEX.json + INDEX.md (no negotiate)",
    )
    p.add_argument(
        "--rotation",
        type=Path,
        default=None,
        help=(
            "multi-well rotation manifest JSON (Mode C): same pin thresholds, "
            "per-well Job OS OS runs, ROTATION_REPORT under --out-dir"
        ),
    )
    p.add_argument(
        "--rotation-dry-run",
        action="store_true",
        help="with --rotation: validate manifest and write dry-run report only",
    )
    p.add_argument(
        "--audit",
        type=Path,
        default=None,
        help=(
            "partner audit: Job OS run_dir (COHERENCE/FIREWALL) or rotation batch_dir "
            "(ROTATION_REPORT.json); no re-ingest, no pin retune"
        ),
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
        "--survey",
        type=Path,
        default=None,
        help="optional survey CSV (MicroPulse SURVEY format or simple MD/Inc/Azi table)",
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
        "--survey-gate",
        type=str,
        default="off",
        choices=("off", "qc_only", "holonomy"),
        help="P3 free param: survey stalk depth (off | qc_only | holonomy)",
    )
    p.add_argument(
        "--require-survey",
        action="store_true",
        help="P3: is_solved requires present survey stations + survey_gate stalk_ok",
    )
    p.add_argument(
        "--regime-mode",
        type=str,
        default="off",
        choices=("off", "persist_h0", "dual_gate_windows"),
        help="P4 free param: regime stalk mode",
    )
    p.add_argument(
        "--with-regime",
        action="store_true",
        help="P4: enable regime stalk report (windowed H0 / shock) each cycle",
    )
    p.add_argument(
        "--with-science",
        action="store_true",
        help="P4: write dual-gate science annex (native vs time-scramble; info only)",
    )
    p.add_argument(
        "--with-dynamical-topology",
        action="store_true",
        help=(
            "Write run-level DYNAMICAL_TOPOLOGY.json (stage-axis measure from "
            "cycle artifacts; never pin / never ACCEPTANCE)"
        ),
    )
    p.add_argument(
        "--topo-stability",
        action="store_true",
        help=(
            "CONTROL: SOLVED requires topology_stable for stability-K consecutive "
            "cycles (auto-enables dynamical topology measure; never pin)"
        ),
    )
    p.add_argument(
        "--require-regime",
        action="store_true",
        help="P4: is_solved requires regime_mode != off + regime stalk_ok "
        "(science score alone never gates)",
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
    p.add_argument(
        "--max-depth-mono-violations",
        type=int,
        default=0,
        help=(
            "pin config (not free): allow N finite-depth decreases "
            "(EDR re-logs); default 0=strict"
        ),
    )
    p.add_argument(
        "--eow-package",
        type=Path,
        default=None,
        help=(
            "P5: EOW-like directory to inventory after SOLVED "
            "(surveys/LAS/pdfs/xlsx); writes eow/PACKAGE_INDEX.json + SHIP.md"
        ),
    )
    p.add_argument(
        "--force-ship",
        action="store_true",
        help=(
            "P5: allow EOW SHIP when not SOLVED; status UNSOLVED_SHIP with banner "
            "(never pretends commercial fixed-point)"
        ),
    )
    p.add_argument(
        "--chunk-rows",
        type=int,
        default=None,
        help="KB D: out-of-core chunk size for CHUNK_INSPECT.json (row windows)",
    )
    p.add_argument(
        "--max-chunks",
        type=int,
        default=32,
        help="KB D: max chunks to inspect when --chunk-rows set",
    )
    p.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="KB D: cap LAS ASCII rows loaded into the negotiate cycle (huge files)",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if args.catalog:
        cat = write_job_os_catalog(args.out_dir)
        print(
            json.dumps(
                {
                    "catalog": True,
                    "n_runs": cat.get("n_runs"),
                    "n_solved": cat.get("n_solved"),
                    "root": cat.get("root"),
                    "index_md": str(Path(args.out_dir) / "INDEX.md"),
                    "note": "catalog not ACCEPTANCE",
                },
                indent=2,
            )
        )
        return 0

    if args.audit is not None:
        target = Path(args.audit)
        if not target.exists():
            logger.error("--audit path not found: %s", target)
            return 2
        if (target / "ROTATION_REPORT.json").is_file():
            body = audit_rotation_batch(target)
        else:
            body = audit_job_run(target)
        print(json.dumps(body, indent=2))
        return 0 if body.get("ok") else 5

    if args.rotation is not None:
        try:
            report = run_job_rotation(
                args.rotation,
                out_root=args.out_dir,
                max_rounds=int(args.max_rounds),
                max_rows=args.max_rows,
                dry_run=bool(args.rotation_dry_run),
            )
        except FileNotFoundError as exc:
            logger.error("%s", exc)
            return 2
        except ValueError as exc:
            logger.error("%s", exc)
            return 2
        print(
            json.dumps(
                {
                    "rotation": True,
                    "batch_id": report.get("batch_id"),
                    "branch": report.get("branch"),
                    "n_wells": (report.get("classification") or {}).get("n_wells"),
                    "n_firewall_certified": (report.get("classification") or {}).get(
                        "n_firewall_certified"
                    ),
                    "pin_identical": report.get("pin_identical_across_wells"),
                    "batch_dir": report.get("batch_dir"),
                    "dry_run": report.get("dry_run"),
                    "note": "ROTATION branch from firewall_certified; residue not accept",
                },
                indent=2,
            )
        )
        branch = str(report.get("branch") or "")
        if branch == "ROTATION_PASS":
            return 0
        if branch == "DRY_RUN":
            return 0
        if branch == "ROTATION_PARTIAL":
            return 3
        return 4

    if args.eow_package is not None and not args.eow_package.exists():
        logger.error("--eow-package path not found: %s", args.eow_package)
        return 2

    if args.resume is not None:
        if not (args.resume / "RUN.json").is_file():
            logger.error("resume path missing RUN.json: %s", args.resume)
            return 2
        try:
            result = run_job_coherence_loop(
                las_path=args.las,
                micropulse_path=args.micropulse,
                survey_path=args.survey,
                out_root=args.out_dir,
                max_rounds=int(args.max_rounds),
                resume_dir=args.resume,
                stability_k=int(args.stability_k),
                os_mode=True,
                with_regime=bool(args.with_regime),
                with_science=bool(args.with_science),
                with_dynamical_topology=bool(args.with_dynamical_topology),
                topo_stability=bool(args.topo_stability),
                eow_package=args.eow_package,
                force_ship=bool(args.force_ship),
                chunk_rows=args.chunk_rows,
                max_chunks=int(args.max_chunks),
                max_rows=args.max_rows,
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
        if args.survey is not None and not args.survey.is_file():
            logger.error("--survey path not found: %s", args.survey)
            return 2
        try:
            result = run_job_coherence_loop(
                las_path=args.las,
                micropulse_path=args.micropulse,
                survey_path=args.survey,
                out_root=args.out_dir,
                initial=FreeParams(
                    align_mode=args.align_mode,
                    window_scale=int(args.window_scale),
                    channel_pack=args.channel_pack,
                    null_policy=args.null_policy,
                    survey_gate=args.survey_gate,
                    regime_mode=args.regime_mode,
                ),
                thresholds=JobThresholds(
                    min_export_ok_fraction=1.0,
                    max_physics_fail=int(args.max_physics_fail),
                    min_align_score=float(args.min_align_score),
                    require_verify_ok=True,
                    require_pin=True,
                    depth_mono_eps=float(args.depth_mono_eps),
                    max_depth_mono_violations=int(args.max_depth_mono_violations),
                    require_survey=bool(args.require_survey),
                    require_regime=bool(args.require_regime),
                ),
                max_rounds=int(args.max_rounds),
                stability_k=int(args.stability_k),
                os_mode=bool(args.os),
                run_id=args.run_id,
                with_regime=bool(args.with_regime),
                with_science=bool(args.with_science),
                with_dynamical_topology=bool(args.with_dynamical_topology),
                topo_stability=bool(args.topo_stability),
                eow_package=args.eow_package,
                force_ship=bool(args.force_ship),
                chunk_rows=args.chunk_rows,
                max_chunks=int(args.max_chunks),
                max_rows=args.max_rows,
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

    eow = result.get("eow_ship") or {}
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
                "eow_ship_status": result.get("eow_ship_status"),
                "eow_shipped": eow.get("shipped"),
                "eow_refused": eow.get("refused"),
                "eow_banner": eow.get("banner"),
                "pin_ok": (result.get("pin_locked") or {}).get("last_ok"),
                "micropulse_kinds": result.get("micropulse_kinds"),
                "survey_n_stations": result.get("survey_n_stations"),
                "require_survey": result.get("require_survey"),
                "require_regime": result.get("require_regime"),
                "with_regime": result.get("with_regime"),
                "with_science": result.get("with_science"),
                "chunk_inspect_n": (result.get("chunk_inspect") or {}).get("n_chunks"),
                "out": result.get("out_root"),
                "note": (
                    "pin locked; free params only; OS fixed-point K; "
                    "glue structural; survey never invents Inc/Azi; "
                    "science info only; EOW ship post-SOLVED; chunk inspect optional; not ROP"
                ),
            },
            indent=2,
        )
    )
    if eow.get("refused") and not result.get("solved"):
        return 1
    return 0 if result.get("solved") else 1


if __name__ == "__main__":
    raise SystemExit(main())
