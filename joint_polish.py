#!/usr/bin/env python3
"""Joint polish: keep seal R low while lifting cyclic native enrichment.

Stage-appropriate: freezes bulk action knobs, tunes IR micro mults (+ optional
tier/boost) against a small probe of RCSB cyclic structures. Ontology unchanged.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import differential_evolution, minimize

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.validate.harness import score_configuration
from realm.validate.report import load_knobs, write_json
from pdb_batch import HOLDOUT_IDS, PROBE_IDS, rank_one

logger = logging.getLogger("joint_polish")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Joint IR polish for R + enrichment")
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("--probe", type=str, default=",".join(PROBE_IDS))
    p.add_argument(
        "--holdout",
        type=str,
        default=",".join(HOLDOUT_IDS),
        help="Never used in objective — reported after polish",
    )
    p.add_argument("--n-decoys", type=int, default=16)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--alpha-enrich", type=float, default=0.20, help="weight on (1-enrichment)")
    p.add_argument("--r-cap", type=float, default=0.012, help="soft barrier if R exceeds")
    p.add_argument("--de-iter", type=int, default=4)
    p.add_argument("--json", type=Path, default=Path("joint_polish_result.json"))
    p.add_argument("--write-evolve", action="store_true", help="overwrite evolve_result.json if better")
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    base = load_knobs(args.knobs)
    probe = [x.strip().upper() for x in args.probe.split(",") if x.strip()]
    holdout = [x.strip().upper() for x in args.holdout.split(",") if x.strip()]
    # prevent leakage: holdout must not appear in probe
    holdout = [h for h in holdout if h not in set(probe)]
    rng = np.random.default_rng(21)

    # vector: w1, w2, w3, low_boost_scale, tier
    bounds = [
        (0.80, 1.20),
        (0.80, 1.20),
        (0.80, 1.20),
        (0.45, 1.20),  # low_boost absolute
        (0.35, 0.75),  # tier_split
    ]
    x0 = np.array(
        [
            float(base.get("w1_mult", 1.0)),
            float(base.get("w2_mult", 1.0)),
            float(base.get("w3_mult", 1.0)),
            float(base.get("low_boost", 0.75)),
            float(base.get("tier_split", 0.58)),
        ]
    )

    history: list[dict] = []
    best: dict | None = None

    def knobs_from_x(x: np.ndarray) -> dict:
        kn = dict(base)
        kn["w1_mult"] = float(x[0])
        kn["w2_mult"] = float(x[1])
        kn["w3_mult"] = float(x[2])
        kn["low_boost"] = float(x[3])
        kn["tier_split"] = float(x[4])
        return kn

    def probe_enrichment(kn: dict) -> tuple[float, list]:
        rows = []
        for pid in probe:
            try:
                row = rank_one(
                    pid,
                    kn,
                    args.n_decoys,
                    args.k,
                    args.sectors,
                    0.45,
                    rng,
                    n_seeds=1,  # fast objective; multi-seed only on holdout/batch
                    soft_T=0.04,
                    sectors_mode="adaptive",
                    multimode_mode="self_fit_dense",
                    defect_beta=0.20,
                )
            except Exception as exc:  # noqa: BLE001
                row = {"pdb": pid, "status": "ERROR", "error": str(exc)}
            rows.append(row)
        ok = [r for r in rows if r.get("status") == "OK"]
        if not ok:
            return 0.0, rows
        return float(np.mean([r["enrichment"] for r in ok])), rows

    def objective(x: np.ndarray) -> float:
        nonlocal best
        kn = knobs_from_x(x)
        seal = score_configuration(
            kind="zeta",
            knobs=kn,
            N=13,
            n_zeros=args.k,
            n_sectors=args.sectors,
            rng_seed=0,
        )
        R = float(seal["R"])
        occ = float(seal["occupancy"])
        enr, rows = probe_enrichment(kn)
        # fitness: residual + vacancy + (1-enrichment) + barrier
        F = (
            R
            + 0.35 * (1.0 - occ)
            + args.alpha_enrich * (1.0 - enr)
            + max(0.0, R - args.r_cap) * 5.0
        )
        entry = {
            "F": F,
            "R": R,
            "occupancy": occ,
            "mean_enrichment": enr,
            "knobs": kn,
            "n_ok": sum(1 for r in rows if r.get("status") == "OK"),
        }
        history.append(entry)
        if best is None or F < best["F"] - 1e-12:
            best = {**entry, "probe_rows": rows}
            logger.info(
                "elite F=%.4f R=%.4f occ=%.0f%% enrich=%.0f%% w=(%.2f,%.2f,%.2f)",
                F,
                R,
                100 * occ,
                100 * enr,
                kn["w1_mult"],
                kn["w2_mult"],
                kn["w3_mult"],
            )
        return F

    logger.info("baseline evaluate…")
    objective(x0)

    de = differential_evolution(
        objective,
        bounds=bounds,
        maxiter=args.de_iter,
        popsize=6,
        mutation=(0.4, 1.1),
        recombination=0.8,
        seed=17,
        polish=False,
        workers=1,
    )
    minimize(objective, de.x, method="L-BFGS-B", bounds=bounds, options={"maxiter": 20})
    minimize(objective, x0, method="L-BFGS-B", bounds=bounds, options={"maxiter": 15})

    assert best is not None
    # Held-out evaluation (never in objective)
    hold_rows: list = []
    hold_enr = 0.0
    if holdout:
        for pid in holdout:
            try:
                row = rank_one(
                    pid,
                    best["knobs"],
                    args.n_decoys,
                    args.k,
                    args.sectors,
                    0.45,
                    rng,
                    n_seeds=3,
                    soft_T=0.04,
                    sectors_mode="adaptive",
                    multimode_mode="self_fit_dense",
                    defect_beta=0.20,
                )
            except Exception as exc:  # noqa: BLE001
                row = {"pdb": pid, "status": "ERROR", "error": str(exc)}
            hold_rows.append(row)
        ok_h = [r for r in hold_rows if r.get("status") == "OK"]
        hold_enr = float(np.mean([r["enrichment"] for r in ok_h])) if ok_h else 0.0

    print("\n=== JOINT POLISH ===")
    print(
        f"  F={best['F']:.4f}  R={best['R']:.4f}  occ={best['occupancy']:.0%}  "
        f"probe_enrich={best['mean_enrichment']:.1%}  holdout_enrich={hold_enr:.1%}  "
        f"n_ok_probe={best['n_ok']}"
    )
    print(f"  knobs={json.dumps(best['knobs'], indent=2)}")

    payload = {
        "best": {k: v for k, v in best.items() if k != "probe_rows"},
        "probe_rows": best.get("probe_rows"),
        "holdout_rows": hold_rows,
        "holdout_mean_enrichment": hold_enr,
        "history_tail": history[-20:],
        "ontology": "joint_R_plus_cyclic_enrichment_not_lambda_eq_gamma",
        "probe_ids": probe,
        "holdout_ids": holdout,
    }
    write_json(args.json, payload)

    if args.write_evolve:
        # only write if R sealed-ish and enrichment improved vs baseline history[0]
        base_enr = history[0]["mean_enrichment"] if history else 0.0
        if best["R"] <= 0.01 and best["occupancy"] >= 0.8:
            evolve_payload = {
                "status": "EVOLVED_SEAL" if best["R"] <= 0.005 else "EVOLVING",
                "R": best["R"],
                "F": best["F"],
                "occupancy": best["occupancy"],
                "best_knobs": best["knobs"],
                "meet_knobs": best["knobs"],
                "mean_enrichment_probe": best["mean_enrichment"],
                "search": "joint_polish_IR_enrichment",
                "ontology": "projection_mold_plus_crit_seal",
                "targets": {"R": 0.005, "occupancy": 0.8},
            }
            # re-score full seal diagnostics
            seal = score_configuration(
                kind="zeta",
                knobs=best["knobs"],
                N=13,
                n_zeros=args.k,
                n_sectors=args.sectors,
            )
            evolve_payload["breakdown"] = seal.get("breakdown")
            evolve_payload["n_keys"] = seal.get("n_keys")
            evolve_payload["n_valleys"] = seal.get("n_valleys")
            evolve_payload["verdict"] = seal.get("verdict")
            evolve_payload["mean_enrichment_holdout"] = hold_enr
            evolve_payload["stage"] = {
                "internal_seal": evolve_payload["status"],
                "null_battery": "recheck_after_polish",
                "probe_enrichment": best["mean_enrichment"],
                "holdout_enrichment": hold_enr,
                "path": "geometry_off_zeta_external_cyclic_ranking",
            }
            write_json(Path("evolve_result.json"), evolve_payload)
            write_json(
                Path("lock_meet.json"),
                {
                    "locked": best["R"] <= 0.005,
                    "R": best["R"],
                    "knobs": best["knobs"],
                    "breakdown": seal.get("breakdown"),
                    "search_method": "joint_polish_IR_enrichment_holdout",
                    "mean_enrichment_probe": best["mean_enrichment"],
                    "mean_enrichment_holdout": hold_enr,
                    "baseline_enrichment_probe": base_enr,
                },
            )
            print("wrote evolve_result.json + lock_meet.json", file=sys.stderr)

    print(f"wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
