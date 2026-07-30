#!/usr/bin/env python3
"""Phase 1: null battery — hard zeta preference gate on F."""

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

KINDS = ("zeta", "scramble", "goe", "poisson")
NULL_KINDS = ("scramble", "goe", "poisson")
GATE = 0.8


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Null battery: zeta vs scramble/GOE/Poisson")
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("-N", type=int, default=13)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--workers", type=int, default=-1)
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
                    "rng_seed": rep + (0 if kind == "zeta" else 100 * (1 + KINDS.index(kind))),
                }
            )
    # zeta is deterministic — one rep enough for mean; still run reps for API symmetry
    results = []
    if workers <= 1:
        for j in jobs:
            r = _worker_job(j)
            results.append(r)
            logger.info("kind=%s seed=%s F=%.4f R=%.4f", r["kind"], r["rng_seed"], r["F"], r["R"])
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_worker_job, j) for j in jobs]
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                logger.info(
                    "kind=%s seed=%s F=%.4f R=%.4f",
                    r["kind"],
                    r["rng_seed"],
                    r["F"],
                    r["R"],
                )

    by_kind: dict[str, list] = {k: [] for k in KINDS}
    for r in results:
        by_kind[r["kind"]].append(r)

    means = {}
    for kind, rows in by_kind.items():
        if not rows:
            means[kind] = {"F": 10.0, "R": 10.0, "dens_return": 1.0, "occupancy": 0.0, "n": 0}
            continue
        dens = [
            float((row.get("diagnostics") or {}).get("density_return_l1", 1.0))
            for row in rows
        ]
        means[kind] = {
            "F": float(sum(row["F"] for row in rows) / len(rows)),
            "R": float(sum(row["R"] for row in rows) / len(rows)),
            "dens_return": float(sum(dens) / len(dens)),
            "occupancy": float(sum(row["occupancy"] for row in rows) / len(rows)),
            "n": len(rows),
        }

    f_zeta = means["zeta"]["F"]
    f_nulls = {k: means[k]["F"] for k in NULL_KINDS}
    min_null = min(f_nulls.values()) if f_nulls else 10.0
    passed = f_zeta < GATE * min_null

    print("\n=== NULL BATTERY ===")
    for kind in KINDS:
        m = means[kind]
        print(
            f"  {kind:10s}  mean_F={m['F']:.4f}  mean_R={m['R']:.4f}  "
            f"dens={m['dens_return']:.4f}  occ={m['occupancy']:.0%}"
        )
    print(
        f"\nGate: F_zeta={f_zeta:.4f}  <  {GATE} * min_null={GATE * min_null:.4f}  "
        f"→ {'PASS' if passed else 'FAIL'}"
    )

    payload = {
        "passed": passed,
        "gate": {"rule": f"F_zeta < {GATE} * min(F_nulls)", "margin": GATE},
        "means": means,
        "f_zeta": f_zeta,
        "min_null_F": min_null,
        "config": {
            "N": args.N,
            "n_zeros": args.k,
            "n_sectors": args.sectors,
            "reps": args.reps,
            "workers": workers,
        },
        "knobs": knobs,
        "runs": results,
        "ontology": "null_battery_not_lambda_eq_gamma",
    }
    write_json(args.json, payload)
    print(f"wrote {args.json}", file=sys.stderr)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
