#!/usr/bin/env python3
"""Handoff CLI: Crit ∪ Coutsias molds → multi-level PDB + decorate/physics stubs.

Ontology: geometric upstream sieve — never λ=γ.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.handoff.decorate import select_adapter
from realm.handoff.generate import (
    generate_coutsias_ensemble,
    generate_crit_ensemble,
    merge_and_rank,
)
from realm.handoff.physics import get_physics_adapter
from realm.handoff.types import BackboneArtifact, DecorateRequest
from realm.validate.pdb_write import write_mold_pair
from realm.validate.report import load_knobs, write_json

logger = logging.getLogger("handoff_export")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Geometric handoff export (Crit+Coutsias)")
    p.add_argument("-N", type=int, default=11, help="cycle length (CA count)")
    p.add_argument("-k", type=int, default=14, help="n_zeros for Crit forge")
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument(
        "--sources",
        type=str,
        default="crit,coutsias",
        help="comma list: crit,coutsias",
    )
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--out-dir", type=Path, default=Path("out/handoff_run"))
    p.add_argument("--coutsias-starts", type=int, default=12)
    p.add_argument(
        "--decorate",
        type=str,
        default="null",
        choices=("null", "polyala", "auto"),
    )
    p.add_argument(
        "--physics",
        type=str,
        default="geometry",
        choices=("geometry", "none"),
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    knobs = load_knobs(args.knobs)
    if isinstance(knobs, dict) and "best_knobs" in knobs:
        knobs = knobs["best_knobs"]

    sources = {s.strip().lower() for s in args.sources.split(",") if s.strip()}
    molds = []
    if "crit" in sources:
        logger.info("generating Crit ensemble N=%d …", args.N)
        molds.extend(
            generate_crit_ensemble(knobs, N=int(args.N), n_zeros=int(args.k))
        )
    if "coutsias" in sources:
        logger.info("generating Coutsias ensemble N=%d …", args.N)
        molds.extend(
            generate_coutsias_ensemble(
                N=int(args.N), n_starts=int(args.coutsias_starts)
            )
        )
    if not molds:
        logger.error("no molds generated")
        return 1

    ranked = merge_and_rank(molds, top_k=int(args.top_k))
    out = Path(args.out_dir)
    molds_dir = out / "molds"
    molds_dir.mkdir(parents=True, exist_ok=True)

    decorate_ad = select_adapter(args.decorate)
    physics_ad = get_physics_adapter(args.physics)

    index_molds = []
    for i, m in enumerate(ranked):
        stem = f"{i:03d}_{m.source}"
        paths = write_mold_pair(
            molds_dir,
            stem,
            m.xyz,
            source=m.source,
            rank_score=m.rank_score,
            method=m.method,
            twist=m.twist,
            maxop_gap=m.maxop_gap,
        )
        art = BackboneArtifact(
            path_ca=Path(paths["path_ca"]),
            path_bb=Path(paths["path_bb"]),
            meta=m.meta,
        )
        dec = decorate_ad.decorate(
            DecorateRequest(backbone=art, poly_ala=True)
        )
        phys = None
        if physics_ad is not None:
            phys = physics_ad.filter(art.path_bb)
            phys_dir = out / "physics"
            phys_dir.mkdir(parents=True, exist_ok=True)
            (phys_dir / f"{stem}.json").write_text(
                json.dumps(phys.to_dict(), indent=2), encoding="utf-8"
            )
        entry = m.to_index_entry(
            {
                "ca": paths["path_ca"],
                "bb": paths["path_bb"],
                "decorated": None
                if dec.path_decorated is None
                else str(dec.path_decorated),
            }
        )
        entry["decorate"] = dec.to_dict()
        entry["physics"] = None if phys is None else phys.to_dict()
        index_molds.append(entry)
        logger.info(
            "  wrote %s score=%.4g decorate=%s physics=%s",
            stem,
            m.rank_score,
            dec.status,
            None if phys is None else phys.status,
        )

    payload = {
        "n_molds": len(index_molds),
        "N": int(args.N),
        "sources": sorted(sources),
        "top_k": int(args.top_k),
        "molds": index_molds,
        "ontology": "substrate_crit_projection_handoff_not_lambda_eq_gamma",
        "note": (
            "Upstream geometric sieve. Multi-level PDB for decorate/physics. "
            "Never λ=γ."
        ),
    }
    write_json(out / "index.json", payload)
    print(f"wrote {out / 'index.json'}  molds={len(index_molds)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
