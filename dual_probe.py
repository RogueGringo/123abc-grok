#!/usr/bin/env python3
"""Dual probe: substrate → (L operator, Crit projection) on cyclic PDBs.

Reports:
  1. Operator fingerprints per substrate (ζ / arith / gue / poisson)
  2. Native-vs-decoy enrichment under pure projection and dual blend
  3. Cross-substrate projection ranking (frozen knobs — seating knobs, not
     equal-budget ζ claim)

Ontology: substrate = seed field; L = baseline op matrix; geometry = projection.
Never λ=γ. Does not restore retracted residual ζ-preference claim.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.validate.decoys import make_ca_decoys
from realm.validate.dual import dual_score_geometry, forge_crit_geometry
from realm.validate.pdb_io import fetch_pdb, load_ca_cyclic_band
from realm.validate.report import load_knobs, write_json
from realm.validate.seeds import make_seed
from pdb_batch import HOLDOUT_IDS, PROBE_IDS

logger = logging.getLogger("dual_probe")

SUBSTRATES = ("zeta", "arith", "gue", "poisson")


def _enrich(
    xyz: np.ndarray,
    pack: dict,
    *,
    n_decoys: int,
    noise: float,
    rng: np.random.Generator,
    alpha_proj: float,
    n_seeds: int,
) -> dict:
    seed_e, seed_r, seed_top = [], [], []
    for _ in range(max(1, n_seeds)):
        sub = np.random.default_rng(int(rng.integers(0, 2**31 - 1)))
        n_soft = max(n_decoys // 2, 1)
        n_hard = n_decoys - n_soft
        decoys = make_ca_decoys(xyz, n_soft, sub, noise=noise)
        decoys += make_ca_decoys(xyz, n_hard, sub, noise=noise * 1.8)
        native = dual_score_geometry(xyz, pack, alpha_proj=alpha_proj)
        nd = float(native["mean_dist"])
        scores = [nd]
        for d in decoys:
            scores.append(
                float(dual_score_geometry(d, pack, alpha_proj=alpha_proj)["mean_dist"])
            )
        worse = sum(1 for s in scores[1:] if s > nd)
        rank = 1 + sum(1 for s in scores[1:] if s < nd)
        n_tot = len(scores)
        seed_e.append(worse / max(n_decoys, 1))
        seed_r.append(rank)
        seed_top.append(rank <= max(1, int(0.2 * n_tot)))
    return {
        "enrichment": float(np.mean(seed_e)),
        "enrichment_std": float(np.std(seed_e)) if len(seed_e) > 1 else 0.0,
        "native_rank": float(np.mean(seed_r)),
        "top20": bool(np.mean(seed_top) >= 0.5),
        "native_proj": float(
            dual_score_geometry(xyz, pack, alpha_proj=1.0)["proj_dist"]
        ),
        "native_dual": float(
            dual_score_geometry(xyz, pack, alpha_proj=alpha_proj)["mean_dist"]
        ),
        "native_op": float(
            dual_score_geometry(xyz, pack, alpha_proj=0.0)["op_dist"]
        ),
        "alpha_proj": alpha_proj,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Dual L-vs-projection probe")
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument(
        "--ids",
        type=str,
        default=",".join(PROBE_IDS + HOLDOUT_IDS[:3]),
    )
    p.add_argument("--substrates", type=str, default=",".join(SUBSTRATES))
    p.add_argument("--n-decoys", type=int, default=24)
    p.add_argument("--n-seeds", type=int, default=2)
    p.add_argument("--noise", type=float, default=0.45)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument(
        "--alpha",
        type=float,
        default=0.85,
        help="weight on projection in dual blend (1=pure Kabsch TOPK)",
    )
    p.add_argument("--json", type=Path, default=Path("dual_probe_result.json"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    knobs = load_knobs(args.knobs)
    ids = [x.strip().upper() for x in args.ids.split(",") if x.strip()]
    substrates = [x.strip().lower() for x in args.substrates.split(",") if x.strip()]
    rng = np.random.default_rng(19)

    rows = []
    op_table = {}

    for pid in ids:
        path = fetch_pdb(pid)
        xyz, chain = load_ca_cyclic_band(path, lo=6, hi=40)
        n_ca = int(xyz.shape[0])
        N = max(n_ca, 7)
        logger.info("%s CA=%d chain=%s N=%d", pid, n_ca, chain, N)

        by_sub = {}
        for kind in substrates:
            g = make_seed(kind, args.k, np.random.default_rng(0 if kind == "zeta" else 7))
            pack = forge_crit_geometry(
                knobs,
                N=N,
                n_zeros=args.k,
                n_sectors=args.sectors,
                gammas=g,
            )
            # cache operator summary once per (kind, N) shape
            key = f"{kind}_N{N}"
            if key not in op_table:
                op_table[key] = pack["operator"].to_dict()

            pure = _enrich(
                xyz,
                pack,
                n_decoys=args.n_decoys,
                noise=args.noise,
                rng=rng,
                alpha_proj=1.0,
                n_seeds=args.n_seeds,
            )
            dual = _enrich(
                xyz,
                pack,
                n_decoys=args.n_decoys,
                noise=args.noise,
                rng=rng,
                alpha_proj=args.alpha,
                n_seeds=args.n_seeds,
            )
            by_sub[kind] = {
                "projection": pure,
                "dual": dual,
                "n_templates": pack["n_sectors"],
                "op_mean_gap": pack["operator"].mean_gap,
                "op_gap_cv": pack["operator"].gap_cv,
            }
            logger.info(
                "  %s  proj_enr=%.0f%%  dual_enr=%.0f%%  gap=%.4f",
                kind,
                100 * pure["enrichment"],
                100 * dual["enrichment"],
                pack["operator"].mean_gap,
            )

        rows.append(
            {
                "pdb": pid,
                "n_ca": n_ca,
                "chain": chain,
                "N_scaffold": N,
                "substrates": by_sub,
            }
        )

    # summaries: mean enrichment per substrate under projection / dual
    summary = {"projection": {}, "dual": {}}
    for kind in substrates:
        pe = [
            r["substrates"][kind]["projection"]["enrichment"]
            for r in rows
            if kind in r["substrates"]
        ]
        de = [
            r["substrates"][kind]["dual"]["enrichment"]
            for r in rows
            if kind in r["substrates"]
        ]
        summary["projection"][kind] = float(np.mean(pe)) if pe else 0.0
        summary["dual"][kind] = float(np.mean(de)) if de else 0.0

    print("\n=== DUAL PROBE (substrate × projection / dual) ===")
    print(f"  alpha_proj={args.alpha}  n_decoys={args.n_decoys}  n_seeds={args.n_seeds}")
    print("  mean enrichment by substrate:")
    for kind in substrates:
        print(
            f"    {kind:8s}  projection={summary['projection'][kind]:.1%}  "
            f"dual={summary['dual'][kind]:.1%}"
        )
    # zeta vs arith on projection (honest: frozen knobs)
    if "zeta" in summary["projection"] and "arith" in summary["projection"]:
        dz = summary["projection"]["zeta"] - summary["projection"]["arith"]
        print(
            f"\n  proj ζ−arith = {dz:+.1%}  "
            f"(positive ⇒ ζ mold ranks natives better under frozen seating knobs)"
        )
    print(
        "\n  note: frozen knobs are ζ-seating; not equal-budget preference claim. "
        "Ontology: L vs projection dual; never λ=γ."
    )

    payload = {
        "rows": rows,
        "summary": summary,
        "operator_fingerprints": op_table,
        "config": {
            "ids": ids,
            "substrates": substrates,
            "n_decoys": args.n_decoys,
            "n_seeds": args.n_seeds,
            "alpha_proj": args.alpha,
            "k": args.k,
            "sectors": args.sectors,
        },
        "knobs": knobs,
        "ontology": "dual_operator_vs_projection_not_lambda_eq_gamma",
        "instrument_note": (
            "Substrate→Crit→(L fingerprint, CA projection). "
            "ζ residual preference remains RETRACTED; this is geometry/dual path."
        ),
    }
    write_json(args.json, payload)
    print(f"wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
