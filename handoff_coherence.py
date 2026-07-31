#!/usr/bin/env python3
"""Cyclic coherence protocol for dual-gate handoff routines.

observe → negotiate free parameters → re-export → until coherent or budget.

LOCKED: soft_T(n=12)=0.036, seq_mix=0, face_weight=0.08 (never adapted).
FREE: decorate, physics, top_k only.

Never enrichment score-chase. Never lambda=gamma.
Sister protocol to evolve_ns (genotype knobs) — this loop is routine coherence.
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

from realm.handoff.coherence import (
    CoherenceThresholds,
    FreeParams,
    run_coherence_loop,
)
from realm.handoff.pipeline import resolve_pdb_id_list
from realm.handoff.verify import verify_dual_gate_pin
from realm.validate.report import load_knobs

logger = logging.getLogger("handoff_coherence")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Cyclic handoff coherence OS: negotiate decorate/physics/top_k until "
            "commercial routine fixed-point. Dual-gate pin locked. "
            "Not ACCEPTANCE enrichment chase."
        )
    )
    p.add_argument(
        "--pdb-ids",
        type=str,
        default="1CSA",
        help="IDs or tokens probe|holdout|default (default: 1CSA)",
    )
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("out/coherence"),
        help="root for cycle_* dirs + COHERENCE.json (OS: parent of run_id/)",
    )
    p.add_argument("--max-rounds", type=int, default=5)
    p.add_argument(
        "--os",
        action="store_true",
        help="OS v2: run_id/, RUN.json, ledger.jsonl, PARTNER_RECIPE, LATEST",
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
        "--decorate",
        type=str,
        default="null",
        choices=("null", "polyala", "sequence", "auto"),
        help="initial decorate (default null so loop can negotiate upward)",
    )
    p.add_argument(
        "--physics",
        type=str,
        default="geometry",
        choices=("geometry", "none"),
    )
    p.add_argument("--top-k", type=int, default=2)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--no-verify", action="store_true")
    p.add_argument(
        "--min-decorate-frac",
        type=float,
        default=0.5,
        help="min decorate OK fraction when decorate != null",
    )
    p.add_argument(
        "--max-physics-fail",
        type=int,
        default=0,
        help="max allowed physics FAIL counts",
    )
    p.add_argument(
        "--require-decorate",
        action="store_true",
        help="treat decorate=null as incoherent (negotiate toward sequence/polyala)",
    )
    p.add_argument(
        "--with-science",
        action="store_true",
        help=(
            "enable soft enrichment science channel (informational proposals only; "
            "never retunes dual-gate pin or gates commercial accept)"
        ),
    )
    p.add_argument(
        "--with-genotype",
        action="store_true",
        help=(
            "after free-param loop: optional NS micro-search on spectral knobs "
            "(if unsolved or science weak); never writes LengthPolicy pin"
        ),
    )
    p.add_argument("--genotype-epochs", type=int, default=2)
    p.add_argument("--genotype-pop", type=int, default=4)
    p.add_argument(
        "--science-weak",
        type=float,
        default=0.55,
        help="mean soft enrichment below this triggers genotype when --with-genotype",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    pin = verify_dual_gate_pin()
    if not pin.get("ok"):
        logger.error("dual-gate pin FAIL (locked — cannot negotiate): %s", pin)
        return 4

    if args.resume is not None:
        if not (args.resume / "RUN.json").is_file():
            logger.error("resume path missing RUN.json: %s", args.resume)
            return 2
        knobs_path = args.knobs
        if not knobs_path.is_file():
            logger.error("knobs missing: %s", knobs_path)
            return 2
        knobs = load_knobs(knobs_path)
        if isinstance(knobs, dict) and "best_knobs" in knobs:
            knobs = knobs["best_knobs"]
        result = run_coherence_loop(
            pdb_ids=[],  # restored from RUN.json
            knobs=knobs,
            out_root=args.out_dir,
            max_rounds=int(args.max_rounds),
            verify=not args.no_verify,
            n_zeros=int(args.k),
            resume_dir=args.resume,
            stability_k=int(args.stability_k),
            os_mode=True,
            with_genotype=bool(args.with_genotype),
            genotype_epochs=int(args.genotype_epochs),
            genotype_pop=int(args.genotype_pop),
            science_weak_threshold=float(args.science_weak),
        )
    else:
        ids = resolve_pdb_id_list(args.pdb_ids)
        if not ids:
            logger.error("no PDB ids from %r", args.pdb_ids)
            return 2

        if not args.knobs.is_file():
            logger.error("knobs missing: %s", args.knobs)
            return 2
        knobs = load_knobs(args.knobs)
        if isinstance(knobs, dict) and "best_knobs" in knobs:
            knobs = knobs["best_knobs"]

        dec0 = args.decorate
        if dec0 == "auto":
            dec0 = "sequence"

        result = run_coherence_loop(
            pdb_ids=list(ids),
            knobs=knobs,
            out_root=args.out_dir,
            initial=FreeParams(
                decorate=dec0,
                physics=args.physics,
                top_k=int(args.top_k),
            ),
            thresholds=CoherenceThresholds(
                min_export_ok_fraction=1.0,
                max_physics_fail=int(args.max_physics_fail),
                min_decorate_ok_fraction=float(args.min_decorate_frac),
                require_verify_ok=not args.no_verify,
                require_pin=True,
                require_decorate=bool(args.require_decorate),
            ),
            max_rounds=int(args.max_rounds),
            verify=not args.no_verify,
            n_zeros=int(args.k),
            with_science=bool(args.with_science),
            with_genotype=bool(args.with_genotype),
            genotype_epochs=int(args.genotype_epochs),
            genotype_pop=int(args.genotype_pop),
            science_weak_threshold=float(args.science_weak),
            stability_k=int(args.stability_k),
            os_mode=bool(args.os),
            run_id=args.run_id,
        )

    if result.get("stop_reason") == "pin_fail":
        print(json.dumps({"solved": False, "stop_reason": "pin_fail"}, indent=2))
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
                "final_knobs_source": result.get("final_knobs_source"),
                "partner_recipe": result.get("partner_recipe"),
                "genotype_improved": (result.get("genotype") or {}).get("improved"),
                "pin_soft_T": (result.get("pin_locked") or {}).get("soft_T_n12"),
                "out": result.get("out_root"),
                "note": "pin locked; free params + optional genotype; OS fixed-point K",
            },
            indent=2,
        )
    )
    return 0 if result.get("solved") else 1


if __name__ == "__main__":
    raise SystemExit(main())
