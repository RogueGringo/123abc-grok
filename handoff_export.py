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
    generate_structure_ensemble,
    merge_and_rank,
)
from realm.handoff.physics import get_physics_adapter
from realm.handoff.pipeline import (
    DEFAULT_HANDOFF_IDS,
    export_structure_batch,
    export_structure_handoff,
    resolve_pdb_id_list,
)
from realm.handoff.types import BackboneArtifact, DecorateRequest
from realm.validate.pdb_write import write_mold_pair
from realm.validate.report import load_knobs, write_json

logger = logging.getLogger("handoff_export")


def _resnames_from_sequence(seq: str | None, N: int) -> list[str] | None:
    if not seq:
        return None
    s = seq.strip()
    aa1 = {
        "A": "ALA", "G": "GLY", "V": "VAL", "L": "LEU", "I": "ILE", "P": "PRO",
        "F": "PHE", "Y": "TYR", "W": "TRP", "S": "SER", "T": "THR", "C": "CYS",
        "M": "MET", "N": "ASN", "Q": "GLN", "D": "ASP", "E": "GLU", "K": "LYS",
        "R": "ARG", "H": "HIS",
    }
    if len(s) == N and s.isalpha():
        return [aa1.get(c.upper(), "GLY") for c in s]
    parts = [p.strip().upper() for p in s.replace(",", " ").split() if p.strip()]
    if len(parts) == N:
        return parts
    raise SystemExit(f"--sequence length must match N={N}")


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
    p.add_argument(
        "--mode",
        choices=("proposal", "structure", "dual-gate"),
        default="proposal",
        help=(
            "proposal: Crit×omega bank; structure: native self_fit; "
            "dual-gate: production LengthPolicy stamp + structure export"
        ),
    )
    p.add_argument(
        "--pdb",
        type=str,
        default=None,
        help="PDB id for --mode structure|dual-gate (uses data/pdb cache / RCSB)",
    )
    p.add_argument(
        "--pdb-ids",
        type=str,
        default=None,
        help=(
            "dual-gate batch: comma IDs, or tokens default|probe|holdout "
            f"(default campaign={','.join(DEFAULT_HANDOFF_IDS[:4])}…)"
        ),
    )
    p.add_argument(
        "--with-enrichment",
        action="store_true",
        help="dual-gate: stamp read-only rank_one enrichment into index (slow)",
    )
    p.add_argument(
        "--no-biopython-check",
        action="store_true",
        help="dual-gate: skip optional BioPython open check",
    )
    p.add_argument(
        "--sequence",
        type=str,
        default=None,
        help="1-letter or 3-letter seq for resnames",
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
    if args.mode == "dual-gate":
        ids: list[str] = []
        if args.pdb_ids:
            ids.extend(resolve_pdb_id_list(args.pdb_ids))
        if args.pdb:
            ids.append(args.pdb.strip().upper())
        _seen: set[str] = set()
        uniq: list[str] = []
        for x in ids:
            if x and x not in _seen:
                _seen.add(x)
                uniq.append(x)
        ids = uniq
        if not ids:
            logger.error(
                "--mode dual-gate requires --pdb and/or --pdb-ids "
                "(use --pdb-ids default|probe|holdout)"
            )
            return 2
        logger.info("dual-gate handoff ids=%s top_k=%d …", ids, int(args.top_k))
        dg_kw = dict(
            top_k=int(args.top_k),
            n_zeros=int(args.k),
            include_coutsias=("coutsias" in sources),
            decorate=args.decorate,
            physics=args.physics,
            with_enrichment=bool(args.with_enrichment),
            with_biopython_check=not bool(args.no_biopython_check),
        )
        if len(ids) == 1:
            idx = export_structure_handoff(
                ids[0],
                knobs,
                out_dir=args.out_dir,
                **dg_kw,
            )
            logger.info(
                "wrote %s status=%s molds=%s manifest=%s",
                args.out_dir,
                idx.get("status"),
                idx.get("n_molds"),
                Path(args.out_dir) / "manifest.tsv",
            )
            return 0 if idx.get("status") == "OK" else 1
        summary = export_structure_batch(
            ids,
            knobs,
            out_root=args.out_dir,
            **dg_kw,
        )
        logger.info(
            "batch n_ok=%s / %s manifest=%s → %s",
            summary["n_ok"],
            summary["n_ids"],
            summary.get("manifest"),
            args.out_dir,
        )
        return 0 if summary["n_ok"] > 0 else 1

    if args.mode == "structure":
        if not args.pdb:
            logger.error("--mode structure requires --pdb")
            return 2
        logger.info(
            "structure mode pdb=%s sources=%s top_k=%d …",
            args.pdb,
            sorted(sources),
            int(args.top_k),
        )
        ranked = generate_structure_ensemble(
            args.pdb,
            knobs,
            n_zeros=int(args.k),
            top_k=int(args.top_k),
            include_coutsias=("coutsias" in sources),
            soft_T=None,  # dual-gate LengthPolicy soft_T
        )
    else:
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

    if not ranked:
        logger.error("no molds generated")
        return 1
    out = Path(args.out_dir)
    molds_dir = out / "molds"
    molds_dir.mkdir(parents=True, exist_ok=True)

    decorate_ad = select_adapter(args.decorate)
    physics_ad = get_physics_adapter(args.physics)

    # Proposal: sequence must match args.N once. Structure: per-mold N.
    resnames_proposal: list[str] | None = None
    if args.sequence and args.mode == "proposal":
        resnames_proposal = _resnames_from_sequence(args.sequence, int(args.N))

    index_molds = []
    for i, m in enumerate(ranked):
        stem = f"{i:03d}_{m.source}"
        mold_N = int(m.N)
        if args.mode == "proposal":
            mold_resnames = resnames_proposal
        elif args.sequence:
            s = args.sequence.strip()
            parts = [
                p.strip().upper()
                for p in s.replace(",", " ").split()
                if p.strip()
            ]
            if (len(s) == mold_N and s.isalpha()) or len(parts) == mold_N:
                mold_resnames = _resnames_from_sequence(args.sequence, mold_N)
            else:
                logger.warning(
                    "--sequence length does not match mold N=%d for %s; "
                    "skipping sequence for this mold",
                    mold_N,
                    stem,
                )
                mold_resnames = None
        else:
            mold_resnames = None
        paths = write_mold_pair(
            molds_dir,
            stem,
            m.xyz,
            source=m.source,
            rank_score=m.rank_score,
            method=m.method,
            twist=m.twist,
            maxop_gap=m.maxop_gap,
            resnames=mold_resnames,
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

    n_export = int(ranked[0].N) if ranked else int(args.N)
    payload = {
        "n_molds": len(index_molds),
        "N": n_export if args.mode == "structure" else int(args.N),
        "mode": args.mode,
        "pdb": args.pdb,
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
