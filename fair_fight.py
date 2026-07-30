#!/usr/bin/env python3
"""Equal-budget refit across spectra — the fair fight, and the falsifiability probe.

The published null battery scored every null with ζ-fitted knobs, so it compared a
fit at its own optimum against unfit controls. Here every arm gets its own
identical tuning budget from a neutral start.

Two questions, in the order they must be asked:

1. **Falsifiability.** Can the forge drive F near zero for a deliberately
   structureless spectrum (`arith` = constant gap)? If yes, the framework fits
   anything and every downstream result is vacuous. This is checked FIRST because
   a positive answer makes question 2 pointless.
2. **Fair fight.** With equal budgets, is ζ still an outlier against plausible
   nulls (scramble / GOE / Poisson)?

Exit codes: 0 ζ remains a distinguishable outlier, 2 it does not, 3 I/O failure.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.hw import apply_blas_thread_env, recommend_workers
from realm.validate.adversarial import DETERMINISTIC, KINDS
from realm.validate.refit import refit_job
from realm.validate.report import write_json
from realm.validate.zeros import window

logger = logging.getLogger("fair_fight")

# Deliberately structureless / wrong-object spectra. If any of these matches ζ
# under an equal budget, the machinery has no discriminating power.
ADVERSARIAL = ("arith", "geometric", "primes", "reversed", "outlier", "sorted_uniform")
# Statistically plausible nulls — the meaningful comparison if the framework survives.
PLAUSIBLE = ("scramble", "goe", "poisson")


def _ckpt_path(json_path: Path) -> Path:
    """Sidecar holding one completed refit per line."""
    return json_path.with_suffix(".runs.jsonl")


def load_checkpoint(json_path: Path) -> tuple[list[dict], set[tuple[str, int]]]:
    """Completed runs from a prior (possibly interrupted) invocation.

    A full sweep can outlast a harness timeout, so every result is flushed as it
    lands and `--resume` skips the (kind, instance) pairs already on disk.
    """
    path = _ckpt_path(json_path)
    runs: list[dict] = []
    done: set[tuple[str, int]] = set()
    if not path.is_file():
        return runs, done
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue  # tolerate a torn final line from a hard kill
        key = (str(r.get("kind")), int(r.get("instance", -1)))
        if key in done:
            continue
        done.add(key)
        runs.append(r)
    return runs, done


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Equal-budget refit: falsifiability + fair fight")
    p.add_argument("--kinds", default=",".join(KINDS), help="comma list of spectrum kinds")
    p.add_argument("--instances", type=int, default=3, help="independent instances per arm")
    p.add_argument("-N", type=int, default=13)
    p.add_argument("-k", type=int, default=14, help="ordinates per spectrum")
    p.add_argument("--window-start", type=int, default=1, help="1-indexed first real zeta ordinate")
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--popsize", type=int, default=15, help="DE population multiplier")
    p.add_argument("--maxiter", type=int, default=120, help="DE generations (no early exit)")
    p.add_argument("--polish-iter", type=int, default=200)
    p.add_argument("--master-seed", type=int, default=20260730)
    p.add_argument("--workers", type=int, default=-1)
    p.add_argument("--json", type=Path, default=Path("fair_fight_result.json"))
    p.add_argument(
        "--resume",
        action="store_true",
        help="reuse completed runs from the .runs.jsonl checkpoint instead of redoing them",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    kinds = [s.strip() for s in args.kinds.split(",") if s.strip()]
    unknown = [k for k in kinds if k not in KINDS]
    if unknown:
        print(f"unknown kinds: {unknown}; known: {list(KINDS)}", file=sys.stderr)
        return 3

    try:
        base = window(args.window_start, args.k)
    except Exception as exc:  # noqa: BLE001
        print(f"could not build zeta window: {exc}", file=sys.stderr)
        return 3
    logger.info(
        "zeta window g_%d..g_%d  span=%.4f  g_last=%.4f",
        args.window_start,
        args.window_start + args.k - 1,
        float(base[-1] - base[0]),
        float(base[-1]),
    )

    profile = recommend_workers(None if args.workers < 0 else args.workers)
    apply_blas_thread_env(profile.blas_threads)
    workers = profile.workers
    logger.info("Compute: %s", profile.notes)

    evals = args.popsize * 8 * (args.maxiter + 1)

    results, already = load_checkpoint(args.json)
    if args.resume and already:
        logger.info("resuming: %d completed runs loaded from checkpoint", len(already))
    elif already:
        logger.info("ignoring %d checkpointed runs (pass --resume to reuse)", len(already))
        results, already = [], set()

    jobs = []
    for kind in kinds:
        # A deterministic spectrum has no draw to average over; instances differ
        # only by optimizer path, which is still worth sampling.
        for inst in range(args.instances):
            if (kind, inst) in already:
                continue
            jobs.append(
                {
                    "kind": kind,
                    "instance": inst,
                    "base": base.tolist(),
                    "k": args.k,
                    "N": args.N,
                    "n_sectors": args.sectors,
                    "popsize": args.popsize,
                    "maxiter": args.maxiter,
                    "polish_iter": args.polish_iter,
                    "master_seed": args.master_seed,
                }
            )
    logger.info(
        "%d jobs to run (%d kinds x %d instances, %d already done), ~%d evals each, %d workers",
        len(jobs),
        len(kinds),
        args.instances,
        len(already),
        evals,
        workers,
    )

    ckpt = _ckpt_path(args.json)
    if not args.resume and ckpt.is_file():
        ckpt.unlink()

    def checkpoint(r: dict) -> None:
        """Flush immediately: a full sweep can outlive the caller's timeout."""
        with ckpt.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r) + "\n")

    done = 0
    total = len(jobs)
    if workers <= 1:
        for j in jobs:
            r = refit_job(j)
            results.append(r)
            checkpoint(r)
            done += 1
            logger.info("[%d/%d] %s F=%.6f R=%.6f", done, total, r["label"], r["F"], r["R"])
    elif total:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(refit_job, j) for j in jobs]
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                checkpoint(r)
                done += 1
                logger.info(
                    "[%d/%d] %s F=%.6f R=%.6f occ=%.0f%% best@%.0f%% polish=%.2e",
                    done,
                    total,
                    r["label"],
                    r["F"],
                    r["R"],
                    100 * r["occupancy"],
                    100 * r["convergence"]["best_at_budget_fraction"],
                    r["convergence"]["polish_gain"],
                )

    by_kind: dict[str, list] = {k: [] for k in kinds}
    for r in results:
        # A checkpoint may hold kinds outside this invocation's --kinds selection.
        by_kind.setdefault(r["kind"], []).append(r)

    summary = {}
    for kind, rows in by_kind.items():
        if not rows:
            continue
        fs = sorted(float(r["F"]) for r in rows)
        rs = sorted(float(r["R"]) for r in rows)
        summary[kind] = {
            "n": len(rows),
            "F_best": fs[0],
            "F_median": statistics.median(fs),
            "F_worst": fs[-1],
            "F_stdev": statistics.stdev(fs) if len(fs) > 1 else 0.0,
            "R_best": rs[0],
            "R_median": statistics.median(rs),
            "occupancy_best": max(float(r["occupancy"]) for r in rows),
            "deterministic": kind in DETERMINISTIC,
            "max_best_at_budget_fraction": max(
                float(r["convergence"]["best_at_budget_fraction"]) for r in rows
            ),
            "max_polish_gain": max(float(r["convergence"]["polish_gain"]) for r in rows),
        }

    f_zeta = summary.get("zeta", {}).get("F_best")

    print("\n=== EQUAL-BUDGET REFIT ===")
    print(f"  budget: popsize={args.popsize} maxiter={args.maxiter} ~{evals} evals/instance")
    print(f"  zeta window: g_{args.window_start}..g_{args.window_start + args.k - 1}")
    print(f"\n  {'kind':16s} {'F_best':>10s} {'F_med':>10s} {'R_best':>10s} {'occ':>6s} {'best@':>7s}  class")
    for kind in kinds:
        s = summary.get(kind)
        if not s:
            continue
        cls = (
            "CONTROL"
            if kind == "zeta"
            else "adversarial"
            if kind in ADVERSARIAL
            else "plausible-null"
        )
        print(
            f"  {kind:16s} {s['F_best']:10.6f} {s['F_median']:10.6f} {s['R_best']:10.6f} "
            f"{s['occupancy_best']:6.0%} {s['max_best_at_budget_fraction']:6.0%}  {cls}"
        )

    verdict: dict = {}
    if f_zeta is None:
        print("\nno zeta control arm run - cannot judge", file=sys.stderr)
        verdict = {"status": "NO_CONTROL"}
        rc = 3
    else:
        adv = {k: summary[k]["F_best"] for k in ADVERSARIAL if k in summary}
        pla = {k: summary[k]["F_best"] for k in PLAUSIBLE if k in summary}
        # Falsifiability first: an adversarial spectrum matching ζ voids everything.
        adv_matching = {k: v for k, v in adv.items() if v <= 2.0 * f_zeta}
        pla_matching = {k: v for k, v in pla.items() if v <= 2.0 * f_zeta}

        print(f"\n  F_best(zeta) = {f_zeta:.6f}")
        if adv:
            worst_adv = min(adv.values())
            print(f"  best adversarial = {worst_adv:.6f}  ({min(adv, key=adv.get)})  ratio {worst_adv / max(f_zeta, 1e-12):.2f}x")
        if pla:
            worst_pla = min(pla.values())
            print(f"  best plausible null = {worst_pla:.6f}  ({min(pla, key=pla.get)})  ratio {worst_pla / max(f_zeta, 1e-12):.2f}x")

        if adv_matching:
            print(
                f"\n  ** FRAMEWORK FITS ANYTHING ** structureless spectra reached ζ-comparable F: "
                f"{ {k: round(v, 6) for k, v in adv_matching.items()} }"
            )
            print("  The 32x null-battery margin is a tuning artifact. Downstream results are vacuous.")
            verdict = {"status": "UNFALSIFIABLE", "adversarial_matching": adv_matching}
            rc = 2
        elif pla_matching:
            print(
                f"\n  ζ is NOT an outlier once nulls are given equal budget: "
                f"{ {k: round(v, 6) for k, v in pla_matching.items()} }"
            )
            verdict = {"status": "ZETA_NOT_PREFERRED", "plausible_matching": pla_matching}
            rc = 2
        else:
            print("\n  zeta remains a distinguishable outlier under equal budget.")
            verdict = {"status": "ZETA_PREFERRED"}
            rc = 0

    payload = {
        "verdict": verdict,
        "summary": summary,
        "f_zeta_best": f_zeta,
        "classes": {"adversarial": list(ADVERSARIAL), "plausible": list(PLAUSIBLE)},
        "config": {
            "N": args.N,
            "k": args.k,
            "window_start": args.window_start,
            "n_sectors": args.sectors,
            "instances": args.instances,
            "popsize": args.popsize,
            "maxiter": args.maxiter,
            "polish_iter": args.polish_iter,
            "evals_per_instance": evals,
            "master_seed": args.master_seed,
            "workers": workers,
        },
        "zeta_window": base.tolist(),
        # Measured, not asserted. A hardcoded `identical_budget: True` is a claim the
        # file cannot support; these come from the runs themselves.
        "fairness": {
            "warm_start": False,
            "early_stop_disabled": True,
            "n_eval_min": min((r["convergence"]["n_eval"] for r in results), default=0),
            "n_eval_max": max((r["convergence"]["n_eval"] for r in results), default=0),
            "n_eval_by_kind": {
                k: sorted({r["convergence"]["n_eval"] for r in v})
                for k, v in by_kind.items()
                if v
            },
            "budget_identical_measured": (
                len({r["convergence"]["n_eval"] for r in results}) <= 1 if results else None
            ),
            "arm_seed_source": "KINDS.index(kind), not per-process randomized hash(str)",
        },
        "statistic_caveats": {
            "F_best_is_min_over_instances": (
                "F_best takes a min over instances for EVERY arm, so an arm with more "
                "instances gets more chances at a low draw. Comparisons across arms with "
                "unequal instance counts are not calibrated."
            ),
            "verdict_band_is_data_dependent": (
                "The 2.0*f_zeta band scales with f_zeta itself, so its absolute width "
                "changes with the result it is judging. Treat the verdict as a flag, not "
                "a test."
            ),
            "zeta_has_no_sampling_variance": (
                "seeds/adversarial return zeta's spectrum deterministically, so zeta "
                "instances vary only by optimizer path. Optimizer restarts are not "
                "replicates of the data; only windows are. No p-value over zeta "
                "instances is calibrated."
            ),
            "attainable_p_floor": (
                "A Monte-Carlo p-value is (1 + #{T_null <= T_zeta})/(M + 1), so the "
                "smallest attainable value is 1/(M+1). Report M alongside any claim."
            ),
        },
        "runs": results,
        "ontology": "equal_budget_refit_not_lambda_eq_gamma",
    }
    write_json(args.json, payload)
    print(f"wrote {args.json}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
