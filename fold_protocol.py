#!/usr/bin/env python3
"""Ultimate fold protocol CLI — projected elements under AXiomZ CTS.

Runs:
  1) Configurational Term Series (internal structure)
  2) Equal-budget substrate projection table (controls)
  3) Optional full multi-seed ranking on curated cyclics (ζ substrate)
  4) AQFT-local MaxOp dual nets on molds

Ontology: ζ=substrate only; ranking=Crit→geometry projection; MaxOp=L dual.
Never λ=γ. Does not auto-claim ζ preference.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdb_batch import DEFAULT_CYCLIC_IDS, HOLDOUT_IDS, PROBE_IDS, rank_one
from realm.axiomz import activation_signature, run_term_series
from realm.fold_protocol import (
    DEFECT_BETA,
    DENSE_OMEGA,
    fold_one_structure,
    substrate_projection_table,
)
from realm.ontology import ONTOLOGY, ontology_note
from realm.validate.report import load_knobs, write_json

logger = logging.getLogger("fold_protocol")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Fold protocol: substrate→Crit→MaxOp→projection")
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument(
        "--ids",
        type=str,
        default=",".join(PROBE_IDS + HOLDOUT_IDS[:4]),
        help="PDB ids for substrate table / fold-one (default: probe+partial holdout)",
    )
    p.add_argument(
        "--kinds",
        type=str,
        default="zeta,arith,gue,poisson,scramble",
        help="substrate arms for equal mold-budget table",
    )
    p.add_argument("--n-decoys", type=int, default=24)
    p.add_argument("--n-seeds", type=int, default=2)
    p.add_argument("-k", type=int, default=14)
    p.add_argument(
        "--defect-beta",
        type=float,
        default=DEFECT_BETA,
        help="sheaf Dirichlet+chord defect blend (production 0.20)",
    )
    p.add_argument(
        "--full-batch",
        action="store_true",
        help="also run production pdb_batch-style ranking on DEFAULT_CYCLIC_IDS",
    )
    p.add_argument("--full-decoys", type=int, default=40)
    p.add_argument("--full-seeds", type=int, default=3)
    p.add_argument("--skip-cts", action="store_true")
    p.add_argument("--skip-substrate-table", action="store_true")
    p.add_argument("--json", type=Path, default=Path("fold_protocol_result.json"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    knobs = load_knobs(args.knobs)
    ids = [x.strip().upper() for x in args.ids.split(",") if x.strip()]
    kinds = tuple(x.strip().lower() for x in args.kinds.split(",") if x.strip())

    print("\n=== FOLD PROTOCOL ===")
    print(f"  {ontology_note()}")
    print(f"  framing: cellular sheaf L=δ*δ + Witten-Morse Crit(S) → geometry projection")

    payload: dict = {
        "signature": activation_signature(
            "fold_protocol",
            ["G1", "G2", "G3", "1.1", "2.4", "4.1", "5.2", "6.2", "12.3", "18.2"],
        ),
        "ontology": ONTOLOGY,
        "ontology_note": ontology_note(),
        "math_framing": {
            "substrate": "arithmetic base / ζ seed ordinates (generative)",
            "operation_matrix": "connection Laplacian L=δ*δ on cellular sheaf over C_N",
            "monodromy": "SO(2) holonomy on cut edge",
            "witten_morse": "S_Λ(θ) as Morse potential; Crit(S) selects preferred holonomies",
            "projection": "Crit multimode/planar embeds → Kabsch softmin ranking",
            "aqft_proxy": "local observables {gap,frustration,logZ} on Crit cycle net",
            "never": "lambda_eq_gamma",
        },
        "mold_bank": {
            "omega_scales": list(DENSE_OMEGA),
            "multimodes": [False, True],
            "defect_beta": float(args.defect_beta),
        },
        "tracks": {
            "sheaf_defects": "multi-residue chord + Dirichlet L=δ*δ",
            "witten_morse": "mid-band SpectralAction envelope",
            "projection": "Kabsch softmin primary + defect blend",
        },
    }

    # --- 1 CTS ---
    if not args.skip_cts:
        logger.info("CTS resolve…")
        payload["cts"] = run_term_series(
            knobs, N=13, n_zeros=args.k, n_sectors=6, prefer_maxop=True
        )
        q = payload["cts"]["cts"][4]
        print(
            f"  CTS quale: R_info={q['R_informative']:.4f}  "
            f"R_leg={q['R_legacy_seating']:.4f}  "
            f"persist_basins={q['n_persistent_crit_basins']}"
        )

    # --- 2 equal-budget substrate projection table ---
    if not args.skip_substrate_table:
        logger.info("substrate projection table (equal mold budget)…")
        table = substrate_projection_table(
            knobs,
            ids,
            kinds=kinds,
            n_decoys=args.n_decoys,
            n_seeds=args.n_seeds,
            n_zeros=args.k,
            defect_beta=args.defect_beta,
        )
        payload["substrate_projection"] = table
        print("\n  === SUBSTRATE PROJECTION (equal mold bank budget) ===")
        print(f"  note: {table['note']}")
        for kind, s in table["summary"].items():
            print(
                f"    {kind:10s}  mean_enrich={s['mean_enrichment']:.1%}  "
                f"±{s['std']:.1%}  n={s['n']}"
            )
        # headline: does ζ beat arith on this frozen-knob equal-mold budget?
        z = table["summary"].get("zeta", {}).get("mean_enrichment", 0)
        a = table["summary"].get("arith", {}).get("mean_enrichment", 0)
        print(
            f"  ζ−arith (mold budget only, knobs may be ζ-seating) = {z - a:+.1%}  "
            f"[not a preference claim]"
        )

    # --- 3 fold-one details on first id ---
    if ids:
        logger.info("fold_one %s…", ids[0])
        payload["fold_one"] = fold_one_structure(
            ids[0],
            knobs,
            n_decoys=min(args.n_decoys, 32),
            n_seeds=args.n_seeds,
            n_zeros=args.k,
            defect_beta=args.defect_beta,
        )
        fo = payload["fold_one"]
        print(
            f"\n  fold_one {fo['pdb']}: enrich={fo['ranking']['enrichment']:.0%}  "
            f"native_dist={fo['ranking']['native_dist']:.3f}  "
            f"method={fo['ranking'].get('method')}  "
            f"aqft adj_gap_corr={fo['aqft_dual']['net']['adjacent_gap_corr']:.3f}"
        )

    # --- 4 optional full multi-seed ζ ranking ---
    if args.full_batch:
        logger.info("full multi-seed ranking on DEFAULT_CYCLIC_IDS…")
        import numpy as np

        rng = np.random.default_rng(11)
        rows = []
        for pid in DEFAULT_CYCLIC_IDS:
            try:
                row = rank_one(
                    pid,
                    knobs,
                    args.full_decoys,
                    args.k,
                    6,
                    0.45,
                    rng,
                    n_seeds=args.full_seeds,
                    soft_T=0.04,
                    sectors_mode="adaptive",
                    multimode_mode="self_fit_dense",
                    defect_beta=args.defect_beta,
                )
            except Exception as exc:  # noqa: BLE001
                row = {"pdb": pid, "status": "ERROR", "error": str(exc)}
            rows.append(row)
            logger.info("%s", row)
        ok = [r for r in rows if r.get("status") == "OK"]
        mean_e = float(np.mean([r["enrichment"] for r in ok])) if ok else 0.0
        probe_set = set(PROBE_IDS)
        hold_set = set(HOLDOUT_IDS)
        pe = (
            float(np.mean([r["enrichment"] for r in ok if r["pdb"] in probe_set]))
            if any(r["pdb"] in probe_set for r in ok)
            else 0.0
        )
        he = (
            float(np.mean([r["enrichment"] for r in ok if r["pdb"] in hold_set]))
            if any(r["pdb"] in hold_set for r in ok)
            else 0.0
        )
        n_top = sum(1 for r in ok if r.get("top20"))
        payload["full_batch"] = {
            "rows": rows,
            "summary": {
                "n_ok": len(ok),
                "mean_enrichment": mean_e,
                "probe_mean_enrichment": pe,
                "holdout_mean_enrichment": he,
                "top20_count": n_top,
                "n_seeds": args.full_seeds,
                "n_decoys": args.full_decoys,
                "multimode_mode": "self_fit_dense",
                "defect_beta": float(args.defect_beta),
            },
        }
        print(
            f"\n  FULL BATCH: OK={len(ok)}/{len(rows)}  mean={mean_e:.1%}  "
            f"probe={pe:.1%}  holdout={he:.1%}  top20={n_top}  "
            f"defect_beta={args.defect_beta}"
        )

    payload["commit_policy"] = {
        "zeta_preference": False,
        "geometry_projection_ranking": True,
        "equal_budget_substrate_table": "diagnostic_control_not_preference_claim",
        "reason": ontology_note(),
    }

    write_json(args.json, payload)
    print(f"\nwrote {args.json}", file=sys.stderr)
    print("  commit: geometry projection only; ζ preference blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
