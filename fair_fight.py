#!/usr/bin/env python3
"""Equal-budget refit: every seed arm gets the same DE budget from a cold start.

Fairness guarantees:
  - no warm start from evolve_result.json
  - identical eval budget (tol=0, atol=0 → no early DE exit)
  - spectrum RNG and optimizer RNG from independent SeedSequence streams
  - permanent control: arith (constant-gap)

This is the instrument that can (eventually) support a ζ-preference claim.
Default budget is small for CI smoke; production sweeps use --de-iter 40+.
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

from realm.lock_key import Keymaker, build_key, build_lock, residual
from realm.projection import build_moduli_landscape, test_valley_occupancy
from realm.validate.report import write_json
from realm.validate.seeds import make_seed
from realm.zeta_field import ZETA_ZEROS_IMAG

logger = logging.getLogger("fair_fight")

ARMS = ("zeta", "arith", "scramble", "gue", "poisson")
BOUNDS = [
    (0.4, 4.5),
    (0.4, 2.8),
    (0.4, 2.8),
    (0.15, 0.75),
    (0.6, 3.5),
    (0.8, 1.2),
    (0.8, 1.2),
    (0.8, 1.2),
]


def _vec_to_knobs(v: np.ndarray, g_last: float) -> dict[str, float]:
    v = np.asarray(v, float).ravel()
    return {
        "Lambda": float(v[0]) * g_last,
        "omega_scale": float(v[1]),
        "weight_power": float(v[2]),
        "tier_split": float(v[3]),
        "low_boost": float(v[4]),
        "w1_mult": float(v[5]),
        "w2_mult": float(v[6]),
        "w3_mult": float(v[7]),
    }


def _score(
    kn: dict,
    gammas: np.ndarray,
    *,
    N: int,
    n_sectors: int,
    fitness: str,
) -> dict:
    n_zeros = int(gammas.size)
    der = Keymaker(N=N, n_zeros=n_zeros, n_sectors=n_sectors).forge(
        **{**kn, "gammas": gammas}
    )
    lock = build_lock(der)
    key = build_key(der)
    res = residual(lock, key, action=der.action, fitness=fitness)
    land = build_moduli_landscape(
        field=der.field, action=der.action, critical=der.critical
    )
    test = test_valley_occupancy(
        key.thetas,
        landscape=land,
        labels=[f"k{i+1}" for i in range(len(key.thetas))],
        spectral_gaps=key.spectral_gaps,
    )
    occ = float(test.occupancy_fraction)
    n_keys = len(key.thetas)
    n_valleys = len(land.valleys)
    F = (
        float(res.total)
        + 0.45 * (1.0 - occ)
        + 0.25 * max(0, n_sectors - n_keys) / max(n_sectors, 1)
        + 0.15 * max(0.0, 1.0 - n_valleys / max(n_sectors, 1))
    )
    return {
        "F": F,
        "R": float(res.total),
        "occupancy": occ,
        "n_keys": n_keys,
        "diagnostics": res.diagnostics or {},
        "breakdown": res.to_dict(),
    }


def refit_arm(
    kind: str,
    *,
    instance: int,
    N: int,
    k: int,
    n_sectors: int,
    de_iter: int,
    popsize: int,
    fitness: str,
    seed_root: int,
) -> dict:
    kind_id = {k: i + 1 for i, k in enumerate(ARMS)}.get(kind, 99)
    ss = np.random.SeedSequence(seed_root + 10007 * kind_id + instance)
    stream_spec, stream_opt = ss.spawn(2)
    rng_spec = np.random.default_rng(stream_spec)
    rng_opt = np.random.default_rng(stream_opt)

    gammas = make_seed(kind, k, rng_spec)
    g_last = float(gammas[-1])
    eval_count = {"n": 0, "best_F": 1e9, "best_at": 0, "best_kn": None, "best_row": None}

    def objective(v: np.ndarray) -> float:
        kn = _vec_to_knobs(v, g_last)
        try:
            row = _score(kn, gammas, N=N, n_sectors=n_sectors, fitness=fitness)
        except Exception as exc:  # noqa: BLE001
            eval_count["n"] += 1
            return 10.0
        eval_count["n"] += 1
        if row["F"] < eval_count["best_F"] - 1e-15:
            eval_count["best_F"] = row["F"]
            eval_count["best_at"] = eval_count["n"]
            eval_count["best_kn"] = kn
            eval_count["best_row"] = row
        return float(row["F"])

    # cold start: DE from independent opt stream via seed
    de = differential_evolution(
        objective,
        bounds=BOUNDS,
        maxiter=de_iter,
        popsize=popsize,
        mutation=(0.5, 1.2),
        recombination=0.7,
        seed=int(rng_opt.integers(0, 2**31 - 1)),
        polish=False,
        atol=0.0,
        tol=0.0,
        workers=1,
    )
    pre_polish_best = float(eval_count["best_F"])
    minimize(
        objective,
        de.x,
        method="L-BFGS-B",
        bounds=BOUNDS,
        options={"maxiter": 25, "ftol": 1e-10},
    )
    polish_gain = pre_polish_best - float(eval_count["best_F"])

    return {
        "kind": kind,
        "instance": instance,
        "best_F": float(eval_count["best_F"]),
        "best_R": float((eval_count["best_row"] or {}).get("R", 10.0)),
        "best_found_at_eval": int(eval_count["best_at"]),
        "n_evals": int(eval_count["n"]),
        "polish_gain": float(polish_gain),
        "occupancy": float((eval_count["best_row"] or {}).get("occupancy", 0.0)),
        "knobs": eval_count["best_kn"],
        "diagnostics": (eval_count["best_row"] or {}).get("diagnostics"),
        "fitness": fitness,
        "budget": {
            "de_iter": de_iter,
            "popsize": popsize,
            "approx_de_evals": de_iter * popsize * len(BOUNDS),
        },
        "g_last": g_last,
        "n_zeros": k,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Equal-budget multi-arm refit (fair fight)")
    p.add_argument("--arms", type=str, default=",".join(ARMS))
    p.add_argument("--instances", type=int, default=1)
    p.add_argument("-N", type=int, default=13)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--de-iter", type=int, default=3, help="small default for smoke")
    p.add_argument("--popsize", type=int, default=6)
    p.add_argument(
        "--fitness",
        choices=("informative", "legacy"),
        default="informative",
    )
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--json", type=Path, default=Path("fair_fight_result.json"))
    p.add_argument(
        "--jsonl",
        type=Path,
        default=Path("fair_fight_result.runs.jsonl"),
        help="append-only per-instance log for --resume",
    )
    p.add_argument("--resume", action="store_true")
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    done: set[tuple[str, int]] = set()
    if args.resume and args.jsonl.is_file():
        for line in args.jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            done.add((rec["kind"], int(rec["instance"])))

    runs = []
    with args.jsonl.open("a", encoding="utf-8") as logf:
        for kind in arms:
            for inst in range(args.instances):
                if (kind, inst) in done:
                    logger.info("skip %s#%d (resume)", kind, inst)
                    continue
                logger.info("refit %s instance %d …", kind, inst)
                row = refit_arm(
                    kind,
                    instance=inst,
                    N=args.N,
                    k=args.k,
                    n_sectors=args.sectors,
                    de_iter=args.de_iter,
                    popsize=args.popsize,
                    fitness=args.fitness,
                    seed_root=args.seed,
                )
                runs.append(row)
                logf.write(json.dumps(row) + "\n")
                logf.flush()
                logger.info(
                    "  %s#%d best_F=%.5f R=%.5f evals=%d best_at=%d",
                    kind,
                    inst,
                    row["best_F"],
                    row["best_R"],
                    row["n_evals"],
                    row["best_found_at_eval"],
                )

    # reload full jsonl for summary
    all_runs = []
    if args.jsonl.is_file():
        for line in args.jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                all_runs.append(json.loads(line))
    by = {}
    for r in all_runs:
        by.setdefault(r["kind"], []).append(r)
    summary = {}
    for kind, rows in by.items():
        fs = [r["best_F"] for r in rows]
        summary[kind] = {
            "n": len(rows),
            "best_F": float(min(fs)),
            "mean_F": float(np.mean(fs)),
            "median_F": float(np.median(fs)),
        }

    print("\n=== FAIR FIGHT (equal budget, cold start) ===")
    for kind in arms:
        if kind not in summary:
            continue
        s = summary[kind]
        print(
            f"  {kind:10s}  n={s['n']}  best_F={s['best_F']:.5f}  "
            f"mean_F={s['mean_F']:.5f}"
        )
    if "zeta" in summary and "arith" in summary:
        print(
            f"\n  arith_best / zeta_best = "
            f"{summary['arith']['best_F'] / max(summary['zeta']['best_F'], 1e-15):.3f}  "
            f"(<1 means arith wins)"
        )

    payload = {
        "summary": summary,
        "runs_this_invocation": runs,
        "n_runs_total": len(all_runs),
        "config": {
            "N": args.N,
            "k": args.k,
            "sectors": args.sectors,
            "de_iter": args.de_iter,
            "popsize": args.popsize,
            "fitness": args.fitness,
            "arms": arms,
            "warm_start": False,
            "atol": 0.0,
            "tol": 0.0,
        },
        "table_seed": float(ZETA_ZEROS_IMAG[0]),
        "ontology": "equal_budget_not_lambda_eq_gamma",
        "note": (
            "ζ preference only if ζ best_F beats arith and random-matrix arms "
            "at matched budget with informative residual + holdout transfer."
        ),
    }
    write_json(args.json, payload)
    print(f"wrote {args.json}  jsonl={args.jsonl}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
