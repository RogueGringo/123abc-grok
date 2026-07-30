#!/usr/bin/env python3
"""Phase 1 instrument: seating check + informative residual table.

RETRACTED CLAIM (2026-07-29): a PASS under frozen ζ-fitted knobs is **not**
evidence of ζ preference. The legacy residual is largely zero by construction
for any spectrum with enough Crit minima; nulls never received a tuning budget.

This CLI still reports:
  - seating_check: old frozen-knob legacy comparison (artifact, for the record)
  - informative means: density-return R under the same frozen knobs (honest shape score)
  - arith arm: permanent constant-gap control

ζ preference requires equal-budget refit (fair_fight.py) + held-out transfer
(transfer.py). Ontology: never λ=γ.
"""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.hw import apply_blas_thread_env, recommend_workers
from realm.validate.harness import _worker_job
from realm.validate.report import load_knobs, write_json

logger = logging.getLogger("null_battery")

# gue = GUE surmise (correct for ζ); goe kept as alias in seeds.py only
KINDS = ("zeta", "scramble", "gue", "poisson", "arith")
NULL_KINDS = ("scramble", "gue", "poisson", "arith")
GATE = 0.8


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Null battery (seating check + informative residual; ζ claim retracted)"
    )
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("-N", type=int, default=13)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--workers", type=int, default=-1)
    p.add_argument(
        "--fitness",
        choices=("informative", "legacy"),
        default="informative",
        help="residual fitness for F/R columns (default: informative)",
    )
    p.add_argument("--json", type=Path, default=Path("null_battery_result.json"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    knobs = load_knobs(args.knobs)
    profile = recommend_workers(None if args.workers < 0 else args.workers)
    apply_blas_thread_env(profile.blas_threads)
    workers = profile.workers
    logger.info("Compute: %s", profile.notes)
    logger.warning(
        "ζ-preference claim RETRACTED for frozen-knob battery; "
        "see docs/RETRACTION_residual_instrument.md"
    )

    jobs = []
    for kind in KINDS:
        for rep in range(args.reps):
            jobs.append(
                {
                    "kind": kind,
                    "knobs": knobs,
                    "N": args.N,
                    "n_zeros": args.k,
                    "n_sectors": args.sectors,
                    "rng_seed": rep
                    + (0 if kind == "zeta" else 100 * (1 + KINDS.index(kind))),
                    "fitness": args.fitness,
                }
            )
    results = []
    if workers <= 1:
        for j in jobs:
            r = _worker_job(j)
            results.append(r)
            logger.info(
                "kind=%s seed=%s F=%.4f R=%.4f R_leg=%.4f",
                r["kind"],
                r["rng_seed"],
                r["F"],
                r["R"],
                r.get("R_legacy", r["R"]),
            )
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_worker_job, j) for j in jobs]
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                logger.info(
                    "kind=%s seed=%s F=%.4f R=%.4f R_leg=%.4f",
                    r["kind"],
                    r["rng_seed"],
                    r["F"],
                    r["R"],
                    r.get("R_legacy", r["R"]),
                )

    by_kind: dict[str, list] = {k: [] for k in KINDS}
    for r in results:
        by_kind.setdefault(r["kind"], []).append(r)

    means = {}
    for kind, rows in by_kind.items():
        if not rows:
            means[kind] = {
                "F": 10.0,
                "R": 10.0,
                "R_legacy": 10.0,
                "R_informative": 10.0,
                "dens_return": 1.0,
                "occupancy": 0.0,
                "n": 0,
            }
            continue
        dens = [
            float((row.get("diagnostics") or {}).get("density_return_l1", 1.0))
            for row in rows
        ]
        means[kind] = {
            "F": float(sum(row["F"] for row in rows) / len(rows)),
            "R": float(sum(row["R"] for row in rows) / len(rows)),
            "R_legacy": float(sum(row.get("R_legacy", row["R"]) for row in rows) / len(rows)),
            "R_informative": float(
                sum(row.get("R_informative", row["R"]) for row in rows) / len(rows)
            ),
            "dens_return": float(sum(dens) / len(dens)),
            "occupancy": float(sum(row["occupancy"] for row in rows) / len(rows)),
            "n": len(rows),
        }

    # Seating check uses *legacy* F under frozen knobs — known artifact
    f_zeta_leg = means["zeta"]["R_legacy"]
    f_nulls_leg = {k: means[k]["R_legacy"] for k in NULL_KINDS}
    min_null_leg = min(f_nulls_leg.values()) if f_nulls_leg else 10.0
    seating_pass = f_zeta_leg < GATE * min_null_leg

    # Informative comparison (still frozen knobs — not equal-budget)
    f_zeta_inf = means["zeta"]["R_informative"]
    f_nulls_inf = {k: means[k]["R_informative"] for k in NULL_KINDS}
    min_null_inf = min(f_nulls_inf.values()) if f_nulls_inf else 10.0
    # arith is the permanent falsifier control
    arith_beats_zeta = means["arith"]["R_informative"] < f_zeta_inf

    print("\n=== NULL BATTERY (instrument recalibrated) ===")
    print("  claim_zeta_preference: RETRACTED (frozen knobs + degenerate residual)")
    for kind in KINDS:
        m = means[kind]
        print(
            f"  {kind:10s}  R_info={m['R_informative']:.4f}  R_leg={m['R_legacy']:.4f}  "
            f"dens={m['dens_return']:.4f}  occ={m['occupancy']:.0%}"
        )
    print(
        f"\n  seating_check (legacy, frozen knobs): "
        f"Rζ_leg={f_zeta_leg:.4f}  <  {GATE}*min_null={GATE * min_null_leg:.4f}  "
        f"→ {'PASS (artifact)' if seating_pass else 'FAIL'}"
    )
    print(
        f"  informative (frozen knobs, not equal-budget): "
        f"Rζ_info={f_zeta_inf:.4f}  min_null_info={min_null_inf:.4f}  "
        f"arith_beats_ζ={arith_beats_zeta}"
    )
    print(
        "  For ζ evidence see transfer.py (held-out windows) and "
        "fair_fight.py (equal-budget refit)."
    )

    payload = {
        "zeta_preference_claim": "RETRACTED",
        "seating_check": {
            "passed": seating_pass,
            "rule": f"R_legacy_zeta < {GATE} * min(R_legacy_nulls) under frozen knobs",
            "margin": GATE,
            "f_zeta_legacy": f_zeta_leg,
            "min_null_legacy": min_null_leg,
            "interpretation": (
                "Self-consistency of lock–key seating under ζ-fitted knobs; "
                "NOT spectrum discrimination"
            ),
        },
        "informative": {
            "f_zeta": f_zeta_inf,
            "min_null": min_null_inf,
            "means_R": {k: means[k]["R_informative"] for k in KINDS},
            "arith_beats_zeta": arith_beats_zeta,
            "note": (
                "Still frozen knobs — equal-budget required before preference claims"
            ),
        },
        "means": means,
        "config": {
            "N": args.N,
            "n_zeros": args.k,
            "n_sectors": args.sectors,
            "reps": args.reps,
            "workers": workers,
            "fitness": args.fitness,
            "kinds": list(KINDS),
        },
        "knobs": knobs,
        "runs": results,
        "ontology": "null_battery_not_lambda_eq_gamma",
        "instrument": "post_falsification_2026-07-29",
    }
    write_json(args.json, payload)
    print(f"wrote {args.json}", file=sys.stderr)
    # Exit 0: instrument ran. Do not encode retracted ζ preference as success.
    # Exit 2 only if ζ seating itself is broken (champion knobs fail on ζ).
    if means["zeta"]["occupancy"] < 0.5:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
