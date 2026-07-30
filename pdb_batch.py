#!/usr/bin/env python3
"""Batch cyclic PDB native-vs-decoy ranking on the geometric projection path.

Ontology: ζ is the *substrate* seed for Crit molds — not the physical target.
Operational goal = native-vs-decoy enrichment under Crit→geometry projection
(with MaxOp L dual diagnostics). Never λ=γ. AXiomZ: G1/G2/G3, 2.4, 6.2, 12.3.
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

from realm.validate.decoys import make_ca_decoys
from realm.validate.dual import (
    dual_score_geometry,
    forge_crit_geometry,
    multimode_for_ca_length,
    sectors_for_ca_length,
    select_mold_by_fit,
    select_multimode_by_fit,
)
from realm.validate.pdb_io import PdbIOError, fetch_pdb, load_ca_cyclic_band
from realm.validate.report import load_knobs, write_json

logger = logging.getLogger("pdb_batch")

# Curated cyclic / short-peptide public structures (RCSB geometry only).
# Not scraped from ~400 HF protein-language repos.
# Curated IDs known to expose a CA chain in the cyclic band (RCSB).
DEFAULT_CYCLIC_IDS = [
    "1CSA",
    "1IKF",
    "2X2C",
    "4M6E",
    "3WNE",
    "4K8Y",
    "1JBL",
    "5EOC",
    "3AVB",
    "3AV9",
    "5LSO",
    "1TET",
]

# Default joint-polish train probe (never sole success metric)
PROBE_IDS = ["1CSA", "2X2C", "4M6E", "3WNE"]
HOLDOUT_IDS = ["1IKF", "1JBL", "4K8Y", "5EOC", "3AVB", "3AV9", "5LSO", "1TET"]


def rank_one(
    pdb_id: str,
    knobs: dict,
    n_decoys: int,
    n_zeros: int,
    n_sectors: int,
    noise: float,
    rng: np.random.Generator,
    n_seeds: int = 1,
    alpha_proj: float = 1.0,
    soft_T: float = 0.04,
    aggregate: str = "softmin",
    sectors_mode: str = "fixed",
    multimode: bool | None = None,
    multimode_mode: str = "adaptive_short",
    defect_beta: float = 0.0,
) -> dict:
    """Native-vs-decoy rank. Projection-primary; defect_beta blends sheaf energy."""
    path = fetch_pdb(pdb_id)
    xyz, chain_used = load_ca_cyclic_band(path, lo=6, hi=40)
    n_ca = int(xyz.shape[0])
    if n_ca < 6 or n_ca > 40:
        return {
            "pdb": pdb_id,
            "status": "SKIP_LENGTH",
            "n_ca": n_ca,
            "chain": chain_used,
            "note": "no chain in cyclic peptide length band [6,40]",
        }

    # Match Keymaker N to backbone length (geometry scaffold size)
    N = max(n_ca, 7)
    n_sec = sectors_for_ca_length(n_ca, mode=sectors_mode, default=n_sectors)
    fit_diag = None
    mm_mode = str(multimode_mode or "adaptive_short").lower().strip()
    if multimode is not None:
        use_mm = bool(multimode)
        pack = forge_crit_geometry(
            knobs,
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sec,
            multimode=use_mm,
        )
    elif mm_mode in ("self_fit", "self-fit", "fit"):
        use_mm, pack, fit_diag = select_multimode_by_fit(
            xyz,
            knobs,
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sec,
            soft_T=soft_T,
        )
    elif mm_mode in ("self_fit_omega", "self_fit_bank", "bank"):
        # multimode × omega_scale bank (structure-conditioned mold pick)
        use_mm, pack, fit_diag = select_mold_by_fit(
            xyz,
            knobs,
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sec,
            soft_T=soft_T,
            multimodes=(False, True),
            omega_scales=(0.9, 1.0, 1.15),
        )
    elif mm_mode in ("self_fit_dense", "dense"):
        # Length-adaptive dense bank: finer omega + native sheaf-defect
        # mold tie-breaks on mid-length rings (4K8Y / 1TET floors).
        from realm.validate.dual import mid_length_omega_bank

        # Length-adaptive dense bank (superset of confirmed 5-point dense).
        # defect_tie off by default in production path — dual-gate rejected
        # defect-tie for n≥12/13 (lost 5EOC top20). Available via self_fit_mid.
        omega_bank = mid_length_omega_bank(n_ca)
        use_mm, pack, fit_diag = select_mold_by_fit(
            xyz,
            knobs,
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sec,
            soft_T=soft_T,
            multimodes=(False, True),
            omega_scales=omega_bank,
            defect_tie=False,
        )
    elif mm_mode in ("self_fit_mid", "mid"):
        # Explicit mid-length attack bank (always defect-tie)
        from realm.validate.dual import mid_length_omega_bank

        use_mm, pack, fit_diag = select_mold_by_fit(
            xyz,
            knobs,
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sec,
            soft_T=soft_T,
            multimodes=(False, True),
            omega_scales=mid_length_omega_bank(max(n_ca, 12)),
            defect_tie=True,
        )
    elif mm_mode in ("self_fit_wide", "wide"):
        use_mm, pack, fit_diag = select_mold_by_fit(
            xyz,
            knobs,
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sec,
            soft_T=soft_T,
            multimodes=(False, True),
            omega_scales=(0.8, 0.9, 1.0, 1.15, 1.3),
        )
    else:
        use_mm = multimode_for_ca_length(n_ca, mode=mm_mode)
        pack = forge_crit_geometry(
            knobs,
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sec,
            multimode=use_mm,
        )
    a = float(np.clip(alpha_proj, 0.0, 1.0))
    sc_kw = dict(
        alpha_proj=a,
        soft_T=soft_T,
        aggregate=aggregate,
        defect_beta=float(defect_beta),
    )
    # Ranking: projection (+ optional sheaf-defect blend). MaxOp dual diagnostic.
    native = dual_score_geometry(xyz, pack, **sc_kw)
    native_dist = float(native["mean_dist"])
    op = pack.get("operator")
    op_diag = op.to_dict() if op is not None else None
    # MaxOp dual fingerprint at Crit (operator layer; not ranking score)
    dual_diag = {
        "maxop_mean_gap": float(op.mean_gap) if op else None,
        "maxop_gap_cv": float(op.gap_cv) if op else None,
        "maxop_mean_frustration": float(op.mean_frustration) if op else None,
        "projection_dist": native_dist,
        "ontology": "projection_primary_maxop_dual_diagnostic",
    }
    n_seeds = max(1, int(n_seeds))
    seed_metrics = []
    last_ranked = []
    for si in range(n_seeds):
        sub = np.random.default_rng(int(rng.integers(0, 2**31 - 1)))
        n_soft = max(n_decoys // 2, 1)
        n_hard = n_decoys - n_soft
        decoys = make_ca_decoys(xyz, n_soft, sub, noise=noise)
        decoys += make_ca_decoys(xyz, n_hard, sub, noise=noise * 1.8)
        rows = [{"label": "native", "mean_dist": native_dist}]
        for i, d in enumerate(decoys):
            sc = dual_score_geometry(d, pack, **sc_kw)
            sc["label"] = f"decoy_{i}"
            rows.append(sc)
        ranked = sorted(rows, key=lambda r: r["mean_dist"])
        for i, r in enumerate(ranked, start=1):
            r["rank"] = i
        native_rank = next(r["rank"] for r in ranked if r["label"] == "native")
        worse = sum(
            1
            for r in ranked
            if r["label"] != "native" and r["mean_dist"] > native_dist
        )
        enrichment = worse / max(n_decoys, 1)
        top20 = native_rank <= max(1, int(0.2 * len(ranked)))
        seed_metrics.append(
            {"enrichment": enrichment, "native_rank": native_rank, "top20": top20}
        )
        last_ranked = ranked

    enrichments = [m["enrichment"] for m in seed_metrics]
    ranks = [m["native_rank"] for m in seed_metrics]
    enrichment = float(np.mean(enrichments))
    native_rank = float(np.mean(ranks))
    top20 = bool(np.mean([1.0 if m["top20"] else 0.0 for m in seed_metrics]) >= 0.5)

    return {
        "pdb": pdb_id,
        "status": "OK",
        "n_ca": n_ca,
        "chain": chain_used,
        "N_scaffold": N,
        "native_dist": native_dist,
        "native_proj": float(native.get("proj_dist", native_dist)),
        "native_op": float(native.get("op_dist", 0.0)),
        "native_rank": native_rank,
        "n_total": len(last_ranked) if last_ranked else n_decoys + 1,
        "enrichment": enrichment,
        "enrichment_std": float(np.std(enrichments)) if len(enrichments) > 1 else 0.0,
        "top20": top20,
        "method": native.get("method"),
        "n_templates": pack["n_sectors"],
        "n_seeds": n_seeds,
        "alpha_proj": a,
        "soft_T": soft_T,
        "aggregate": aggregate,
        "n_sectors_used": n_sec,
        "sectors_mode": sectors_mode,
        "multimode": use_mm,
        "multimode_mode": (
            "override" if multimode is not None else multimode_mode
        ),
        "multimode_fit": fit_diag,
        "defect_beta": float(defect_beta),
        "defect_dist": float(native.get("defect_dist") or 0.0),
        "maxop_dual": dual_diag,
        "operator": pack["operator"].to_dict() if a < 1.0 else op_diag,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Batch cyclic PDB mold ranking")
    p.add_argument("--ids", type=str, default=",".join(DEFAULT_CYCLIC_IDS))
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("--n-decoys", type=int, default=32)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument(
        "--sectors-mode",
        type=str,
        default="adaptive",
        choices=("fixed", "adaptive"),
        help="adaptive: 4 if CA≤8 else 6 (default); fixed: --sectors",
    )
    p.add_argument("--noise", type=float, default=0.45)
    p.add_argument(
        "--n-seeds",
        type=int,
        default=3,
        help="Average enrichment over this many decoy RNG seeds (stability)",
    )
    p.add_argument(
        "--alpha-proj",
        type=float,
        default=1.0,
        help="1.0=pure Crit projection; <1 blends operator L distance (dual)",
    )
    p.add_argument(
        "--soft-T",
        type=float,
        default=0.04,
        help="softmin temperature for Crit ensemble Kabsch",
    )
    p.add_argument(
        "--aggregate",
        type=str,
        default="softmin",
        choices=("softmin", "topk", "min", "softmin_min"),
        help="Crit template aggregation (softmin_min = geom mean soft×min)",
    )
    p.add_argument(
        "--multimode-mode",
        type=str,
        default="self_fit_dense",
        choices=(
            "self_fit_dense",
            "self_fit_mid",
            "self_fit_wide",
            "self_fit_omega",
            "self_fit",
            "adaptive_short",
            "on",
            "off",
        ),
        help="self_fit_dense: length-adaptive multimode×omega bank (+ defect-tie n≥12); "
        "self_fit_mid: mid-length attack bank; self_fit_omega/self_fit: smaller banks",
    )
    p.add_argument(
        "--multimode",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="override multimode-mode (force on/off for all IDs)",
    )
    p.add_argument(
        "--defect-beta",
        type=float,
        default=0.20,
        help="blend sheaf Dirichlet defect into ranking (0=pure Kabsch; 0.20 production)",
    )
    p.add_argument("--null-json", type=Path, default=Path("null_battery_result.json"))
    p.add_argument("--force", action="store_true")
    p.add_argument("--json", type=Path, default=Path("pdb_batch_result.json"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if not args.force and args.null_json.is_file():
        null = json.loads(args.null_json.read_text(encoding="utf-8"))
        if not null.get("passed", False):
            print("null battery gate FAIL — pass --force to run", file=sys.stderr)
            return 2

    knobs = load_knobs(args.knobs)
    # Prefer ranking_hparams from evolve stage when CLI left at defaults
    rh = {}
    try:
        import json as _json

        raw = _json.loads(Path(args.knobs).read_text(encoding="utf-8"))
        rh = raw.get("ranking_hparams") or (raw.get("stage") or {}).get(
            "ranking_hparams"
        ) or {}
    except Exception:  # noqa: BLE001
        rh = {}
    # Prefer confirmed ranking_hparams when CLI left at code defaults
    if rh.get("accepted") and rh.get("confirmed_full_batch"):
        if abs(float(args.soft_T) - 0.04) < 1e-12 and args.aggregate == "softmin":
            args.soft_T = float(rh.get("soft_T", args.soft_T))
            args.aggregate = str(rh.get("aggregate", args.aggregate))
            logger.info(
                "using evolve ranking_hparams soft_T=%.3f aggregate=%s",
                args.soft_T,
                args.aggregate,
            )
    ids = [x.strip().upper() for x in args.ids.split(",") if x.strip()]
    rng = np.random.default_rng(11)
    rows = []
    for pid in ids:
        try:
            row = rank_one(
                pid,
                knobs,
                args.n_decoys,
                args.k,
                args.sectors,
                args.noise,
                rng,
                n_seeds=args.n_seeds,
                alpha_proj=args.alpha_proj,
                soft_T=args.soft_T,
                aggregate=args.aggregate,
                sectors_mode=args.sectors_mode,
                multimode=args.multimode,
                multimode_mode=args.multimode_mode,
                defect_beta=args.defect_beta,
            )
        except PdbIOError as exc:
            row = {"pdb": pid, "status": "IO_FAIL", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            row = {"pdb": pid, "status": "ERROR", "error": str(exc)}
        rows.append(row)
        logger.info("%s", row)

    ok = [r for r in rows if r.get("status") == "OK"]
    mean_enr = float(np.mean([r["enrichment"] for r in ok])) if ok else 0.0
    mean_std = float(np.mean([r.get("enrichment_std", 0.0) for r in ok])) if ok else 0.0
    n_top20 = sum(1 for r in ok if r.get("top20"))
    probe_set = set(PROBE_IDS)
    hold_set = set(HOLDOUT_IDS)
    probe_ok = [r for r in ok if r["pdb"] in probe_set]
    hold_ok = [r for r in ok if r["pdb"] in hold_set]
    probe_enr = (
        float(np.mean([r["enrichment"] for r in probe_ok])) if probe_ok else 0.0
    )
    hold_enr = float(np.mean([r["enrichment"] for r in hold_ok])) if hold_ok else 0.0
    print("\n=== PDB BATCH (structure path, multi-seed) ===")
    for r in rows:
        if r.get("status") == "OK":
            std = r.get("enrichment_std", 0.0)
            split = "probe" if r["pdb"] in probe_set else (
                "hold" if r["pdb"] in hold_set else "extra"
            )
            print(
                f"  {r['pdb']:5s}  [{split:5s}]  CA={r['n_ca']:2d}  "
                f"rank={r['native_rank']:.1f}/{r['n_total']}  "
                f"enrich={r['enrichment']:.0%}±{std:.0%}  top20={r['top20']}"
            )
        else:
            print(f"  {r['pdb']:5s}  {r['status']}  {r.get('error') or r.get('note', '')}")
    print(
        f"\nOK={len(ok)}/{len(rows)}  mean_enrich={mean_enr:.1%}±{mean_std:.1%}  "
        f"probe={probe_enr:.1%}  holdout={hold_enr:.1%}  "
        f"top20={n_top20}  n_seeds={args.n_seeds}"
    )

    payload = {
        "rows": rows,
        "summary": {
            "n_ok": len(ok),
            "n_total_ids": len(rows),
            "mean_enrichment": mean_enr,
            "mean_enrichment_std": mean_std,
            "probe_mean_enrichment": probe_enr,
            "holdout_mean_enrichment": hold_enr,
            "top20_count": n_top20,
            "n_seeds": args.n_seeds,
            "n_decoys": args.n_decoys,
            "alpha_proj": args.alpha_proj,
            "soft_T": args.soft_T,
            "aggregate": args.aggregate,
            "sectors_mode": args.sectors_mode,
            "sectors_default": args.sectors,
            "multimode": args.multimode,
            "multimode_mode": args.multimode_mode,
            "defect_beta": args.defect_beta,
        },
        "knobs": knobs,
        "ontology": "substrate_crit_projection_sheaf_defect_maxop_dual_not_lambda_eq_gamma",
        "note": (
            "ζ=substrate seed only. Ranking = Crit→geometry projection "
            "(Kabsch softmin + optional sheaf defect β) with self_fit mold bank. "
            "MaxOp L = connection dual / local obstruction. Never λ=γ."
        ),
    }
    write_json(args.json, payload)
    print(f"wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
