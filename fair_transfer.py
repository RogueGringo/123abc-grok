#!/usr/bin/env python3
"""Fair per-arm transfer — refit INSIDE the transfer loop.

Formulation B ("train knobs on the first window, gate on a held-out window") has a
latent confound if the held-out evaluation uses ζ-fitted knobs for every arm: that
is the original `null_battery.py` error moved inside the transfer gate. Scored with
ζ's knobs, a constant-gap progression looks terrible (density_return 0.348 vs ζ's
0.157); given its own cold-start knobs it reaches 0.041.

So the fair version fits **each arm on its own train window** and evaluates **each
arm on its own held-out window**:

    for arm in arms:
        knobs = cold_start_refit(arm.spectrum(train_window))   # own budget, no warm start
        heldout_score = score(knobs, arm.spectrum(heldout_window))   # no refit

Because `score_gammas` derives `Lambda = v[0] * g_last(spectrum)` from the
dimensionless vector, passing the fitted vector against a different window performs
the scale-free transfer automatically — the convention Finding 1 showed agrees with
the absolute-Lambda variant to three decimals.

This measures existing residual terms only. It does not alter the fitness path.
Reported per arm: trained level, held-out level, and the degradation ratio, for both
total F/R and the `density_return` term that any rectified residual would lean on.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.hw import apply_blas_thread_env, recommend_workers
from realm.validate.adversarial import KINDS, arm_seed_id, make_adversarial_seed
from realm.validate.refit import refit, score_gammas
from realm.validate.report import write_json
from realm.validate.zeros import window

logger = logging.getLogger("fair_transfer")

DEFAULT_ARMS = ("zeta", "arith", "scramble", "goe", "poisson")


def _exact_rank_p(a: list[float], b: list[float]) -> tuple[int, float]:
    """Exact one-sided rank-sum p: P(ranksum(a) <= observed) under exchangeability.

    Enumerated rather than approximated because n is tiny; the normal approximation
    is meaningless at n=3 and would understate the p-value.
    """
    import itertools

    pooled = sorted(a + b)
    n = len(a)
    rank = {}
    for i, x in enumerate(pooled):
        rank.setdefault(x, i + 1)
    obs = sum(rank[x] for x in a)
    hits = total = 0
    for combo in itertools.combinations(range(len(pooled)), n):
        total += 1
        if sum(i + 1 for i in combo) <= obs:
            hits += 1
    return obs, hits / total if total else 1.0


def transfer_job(payload: dict) -> dict:
    """Cold-start fit on the train window, then score the held-out window."""
    from realm.hw import apply_blas_thread_env as _blas

    _blas(1)

    kind = str(payload["kind"])
    inst = int(payload["instance"])
    k = int(payload["k"])
    train_base = np.asarray(payload["train_base"], dtype=float)
    held_base = np.asarray(payload["held_base"], dtype=float)

    # arm_seed_id, not hash(kind) - str hashing is per-process randomized.
    ss = np.random.SeedSequence([int(payload["master_seed"]), arm_seed_id(kind), inst])
    spec_ss, opt_ss = ss.spawn(2)
    # Same spectrum stream for both windows so the arm's character is held fixed;
    # only the window it is span-matched to changes.
    train_spec = make_adversarial_seed(
        kind, k, np.random.default_rng(spec_ss), base=train_base
    )
    held_spec = make_adversarial_seed(
        kind, k, np.random.default_rng(spec_ss), base=held_base
    )
    de_seed = int(np.random.default_rng(opt_ss).integers(0, 2**31 - 1))

    fit = refit(
        train_spec,
        N=int(payload["N"]),
        n_sectors=int(payload["n_sectors"]),
        popsize=int(payload["popsize"]),
        maxiter=int(payload["maxiter"]),
        polish_iter=int(payload["polish_iter"]),
        de_seed=de_seed,
        label=f"{kind}#{inst}",
    )
    vec = np.asarray(fit["best_vec"], dtype=float)
    held = score_gammas(
        vec,
        gammas=held_spec,
        N=int(payload["N"]),
        n_sectors=int(payload["n_sectors"]),
    )

    d_tr = fit.get("diagnostics") or {}
    d_ho = held.get("diagnostics") or {}
    dens_tr = float(d_tr.get("density_return_l1", float("nan")))
    dens_ho = float(d_ho.get("density_return_l1", float("nan")))
    return {
        "kind": kind,
        "instance": inst,
        "label": f"{kind}#{inst}",
        "trained": {
            "F": float(fit["F"]),
            "R": float(fit["R"]),
            "dens": dens_tr,
            "occupancy": float(fit["occupancy"]),
            "corr": float(d_tr.get("corr_S_lambda", float("nan"))),
        },
        "heldout": {
            "F": float(held["F"]),
            "R": float(held["R"]),
            "dens": dens_ho,
            "occupancy": float(held["occupancy"]),
            "corr": float(d_ho.get("corr_S_lambda", float("nan"))),
        },
        "degradation": {
            "F": float(held["F"]) / max(float(fit["F"]), 1e-15),
            "dens": dens_ho / max(dens_tr, 1e-15),
        },
        "best_vec": fit["best_vec"],
        "convergence": fit["convergence"],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Fair per-arm transfer: refit inside the loop")
    p.add_argument("--arms", default=",".join(DEFAULT_ARMS))
    p.add_argument("--instances", type=int, default=3)
    p.add_argument("-N", type=int, default=13)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--train-start", type=int, default=1)
    p.add_argument("--heldout-start", type=int, default=15)
    p.add_argument("--popsize", type=int, default=15)
    p.add_argument("--maxiter", type=int, default=100)
    p.add_argument("--polish-iter", type=int, default=200)
    p.add_argument("--master-seed", type=int, default=20260730)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--json", type=Path, default=Path("fair_transfer_result.json"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    arms = [s.strip() for s in args.arms.split(",") if s.strip()]
    bad = [a for a in arms if a not in KINDS]
    if bad:
        print(f"unknown arms: {bad}", file=sys.stderr)
        return 3

    train_base = window(args.train_start, args.k)
    held_base = window(args.heldout_start, args.k)
    logger.info(
        "train g_%d..%d (g_last=%.3f)  ->  heldout g_%d..%d (g_last=%.3f)",
        args.train_start,
        args.train_start + args.k - 1,
        float(train_base[-1]),
        args.heldout_start,
        args.heldout_start + args.k - 1,
        float(held_base[-1]),
    )

    profile = recommend_workers(args.workers)
    apply_blas_thread_env(profile.blas_threads)
    workers = min(profile.workers, max(1, args.workers))

    jobs = [
        {
            "kind": kind,
            "instance": inst,
            "k": args.k,
            "N": args.N,
            "n_sectors": args.sectors,
            "train_base": train_base.tolist(),
            "held_base": held_base.tolist(),
            "popsize": args.popsize,
            "maxiter": args.maxiter,
            "polish_iter": args.polish_iter,
            "master_seed": args.master_seed,
        }
        for kind in arms
        for inst in range(args.instances)
    ]
    logger.info("%d jobs, %d workers", len(jobs), workers)

    ckpt = args.json.with_suffix(".runs.jsonl")
    if ckpt.is_file():
        ckpt.unlink()

    results = []
    done = 0
    if workers <= 1:
        for j in jobs:
            r = transfer_job(j)
            results.append(r)
            with ckpt.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(r) + "\n")
            done += 1
            logger.info("[%d/%d] %s", done, len(jobs), r["label"])
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(transfer_job, j) for j in jobs]
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                with ckpt.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(r) + "\n")
                done += 1
                logger.info(
                    "[%d/%d] %s trained_dens=%.6f heldout_dens=%.6f",
                    done,
                    len(jobs),
                    r["label"],
                    r["trained"]["dens"],
                    r["heldout"]["dens"],
                )

    summary = {}
    for kind in arms:
        rows = [r for r in results if r["kind"] == kind]
        if not rows:
            continue
        summary[kind] = {
            "n": len(rows),
            "trained_dens_best": min(r["trained"]["dens"] for r in rows),
            "heldout_dens_best": min(r["heldout"]["dens"] for r in rows),
            "heldout_dens_median": statistics.median(r["heldout"]["dens"] for r in rows),
            "trained_F_best": min(r["trained"]["F"] for r in rows),
            "heldout_F_best": min(r["heldout"]["F"] for r in rows),
            "dens_degradation_median": statistics.median(
                r["degradation"]["dens"] for r in rows
            ),
        }

    print("\n=== FAIR PER-ARM TRANSFER (cold-start refit inside the loop) ===")
    print(
        f"  train g_{args.train_start}..{args.train_start + args.k - 1}"
        f"  ->  heldout g_{args.heldout_start}..{args.heldout_start + args.k - 1}"
    )
    print(
        f"\n  {'arm':12s} {'trained_dens':>13s} {'heldout_dens':>13s} "
        f"{'degrade':>9s} {'heldout_F':>11s}"
    )
    for kind in arms:
        s = summary.get(kind)
        if not s:
            continue
        print(
            f"  {kind:12s} {s['trained_dens_best']:13.6f} {s['heldout_dens_best']:13.6f} "
            f"{s['dens_degradation_median']:9.2f}x {s['heldout_F_best']:11.6f}"
        )

    z = summary.get("zeta")
    verdict = {}
    if z:
        # A min-vs-min comparison is a flag, not a test: it ignores overlap and gives
        # more instances more chances at a low draw. Use an exact rank-sum instead,
        # and state the attainable floor so a null result is not read as evidence.
        z_vals = sorted(r["heldout"]["dens"] for r in results if r["kind"] == "zeta")
        print(f"\n  zeta held-out density_return: {[round(v, 6) for v in z_vals]}")
        tests = {}
        for kind in arms:
            if kind == "zeta":
                continue
            v = sorted(r["heldout"]["dens"] for r in results if r["kind"] == kind)
            if len(v) != len(z_vals) or not v:
                tests[kind] = {"p": None, "note": f"unequal n ({len(v)} vs {len(z_vals)})"}
                continue
            obs, p = _exact_rank_p(z_vals, v)
            tests[kind] = {
                "p_one_sided": p,
                "ranksum_zeta": obs,
                "disjoint": max(z_vals) < min(v),
                "zeta_better": p <= 0.05 and max(z_vals) < min(v),
            }
            rel = "disjoint" if max(z_vals) < min(v) else "OVERLAP"
            print(
                f"    vs {kind:10s} p={p:.3f}  {rel:8s}  {[round(x, 4) for x in v]}"
            )
        n = len(z_vals)
        from math import comb

        floor = 1.0 / comb(2 * n, n) if n else 1.0
        n_cmp = sum(1 for t in tests.values() if t.get("p_one_sided") is not None)
        print(
            f"\n  attainable p floor at n={n} vs {n}: {floor:.3f}"
            f"  (Bonferroni x{n_cmp}: {min(1.0, floor * n_cmp):.3f})"
        )
        sep = [k for k, t in tests.items() if t.get("zeta_better")]
        ind = [k for k, t in tests.items() if t.get("p_one_sided") == 0.5]
        if sep:
            print(f"  zeta separates from: {sep} (at the floor, NOT significant after correction)")
        if ind:
            print(f"  zeta indistinguishable from: {ind}")
        verdict = {
            "status": "HELDOUT_SEPARATES_DEGENERATE_CONTROLS_ONLY" if sep and ind else
                      ("HELDOUT_GATE_PREFERS_ZETA" if sep else "HELDOUT_GATE_DOES_NOT_PREFER_ZETA"),
            "tests": tests,
            "attainable_p_floor": floor,
            "bonferroni_floor": min(1.0, floor * max(n_cmp, 1)),
            "significant_after_correction": False,
            "note": (
                "Separation from degenerate controls does not establish zeta preference; "
                "the random-matrix arms are the relevant comparison and they overlap."
            ),
        }

    write_json(
        args.json,
        {
            "verdict": verdict,
            "summary": summary,
            "config": {
                "arms": arms,
                "instances": args.instances,
                "N": args.N,
                "k": args.k,
                "n_sectors": args.sectors,
                "train_start": args.train_start,
                "heldout_start": args.heldout_start,
                "popsize": args.popsize,
                "maxiter": args.maxiter,
                "evals_per_instance": args.popsize * 8 * (args.maxiter + 1),
                "master_seed": args.master_seed,
            },
            "fairness": {
                "refit_inside_transfer_loop": True,
                "each_arm_fits_own_train_window": True,
                "each_arm_scored_own_heldout_window": True,
                "warm_start": False,
                "transfer_convention": "dimensionless v[0]; Lambda = v[0]*g_last(window)",
            },
            "runs": results,
            "ontology": "fair_transfer_not_lambda_eq_gamma",
        },
    )
    print(f"wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
