#!/usr/bin/env python3
"""Held-out ordinate transfer — do the champion knobs generalize off their window?

`evolve.py` fit the eight knobs against ζ ordinates γ_1..γ_14. If the resulting
F = 0.0045 reflects real structure in the ζ spectrum, freezing those knobs and
scoring a *disjoint* window of genuine ζ ordinates should retain a clear margin
over nulls. If instead F = 0.0045 is the signature of an 8-parameter fit sitting
on the exact window it was tuned on, the margin collapses off-window.

No refitting happens here, which makes this cheap and independent of optimizer
budget questions.

The DE bounds in `evolve.py:506` are **dimensionless** — `v[0]` is the ratio
`Lambda / g_last`, not an absolute scale. So the principled transfer preserves
the dimensionless vector and recomputes `Lambda = v[0] * g_last(window)`. The raw
(unrescaled Lambda) variant is reported alongside it, since which one is "the"
transfer is itself a modelling choice worth exposing rather than hiding.

Real ordinates come from `realm.validate.zeros`, which computes and verifies them
with mpmath — never the mean-gap extrapolation in `seeds.py:41`.
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

from realm.validate.adversarial import (
    DETERMINISTIC,
    KINDS,
    arm_seed_id,
    make_adversarial_seed,
)
from realm.validate.refit import knobs_to_vec, score_gammas, vec_to_knobs
from realm.validate.report import load_knobs, write_json
from realm.validate.zeros import window

logger = logging.getLogger("transfer")

PLAUSIBLE = ("scramble", "goe", "poisson")


def score_window(
    *,
    vec_train: np.ndarray,
    g_last_train: float,
    win: np.ndarray,
    kinds: list[str],
    reps: int,
    N: int,
    n_sectors: int,
    master_seed: int,
    variant: str,
) -> dict:
    """Score every kind on one window with frozen knobs under one transfer variant."""
    g_last = float(win[-1])
    if variant == "rescaled":
        vec = vec_train.copy()  # dimensionless: Lambda tracks this window's g_last
    elif variant == "raw":
        vec = vec_train.copy()
        vec[0] = vec_train[0] * g_last_train / g_last  # keep Lambda absolute
    else:
        raise ValueError(variant)

    out: dict[str, dict] = {}
    for kind in kinds:
        fs, rs, occs = [], [], []
        n = 1 if kind in DETERMINISTIC else reps
        for rep in range(n):
            # arm_seed_id, not hash(kind) - str hashing is per-process randomized.
            rng = np.random.default_rng([master_seed, arm_seed_id(kind), rep])
            g = make_adversarial_seed(kind, int(win.size), rng, base=win)
            sc = score_gammas(vec, gammas=g, N=N, n_sectors=n_sectors)
            fs.append(float(sc["F"]))
            rs.append(float(sc["R"]))
            occs.append(float(sc["occupancy"]))
        out[kind] = {
            "F_mean": float(np.mean(fs)),
            "F_best": float(np.min(fs)),
            "R_mean": float(np.mean(rs)),
            "occupancy_mean": float(np.mean(occs)),
            "n": len(fs),
            "deterministic": kind in DETERMINISTIC,
        }
    return {
        "variant": variant,
        "g_last": g_last,
        "span": float(win[-1] - win[0]),
        "Lambda_used": float(vec[0] * g_last),
        "by_kind": out,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Held-out zeta ordinate transfer test")
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("-N", type=int, default=13)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument(
        "--windows",
        default="1,15,29",
        help="comma list of 1-indexed window starts (disjoint); 1 is the trained window",
    )
    p.add_argument("--reps", type=int, default=25, help="draws per stochastic kind")
    p.add_argument("--master-seed", type=int, default=20260730)
    p.add_argument("--json", type=Path, default=Path("transfer_result.json"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    try:
        knobs = load_knobs(args.knobs)
    except Exception as exc:  # noqa: BLE001
        print(f"could not load knobs: {exc}", file=sys.stderr)
        return 3

    starts = [int(s) for s in args.windows.split(",") if s.strip()]
    train_start = starts[0]
    train_win = window(train_start, args.k)
    g_last_train = float(train_win[-1])
    vec_train = knobs_to_vec(knobs, g_last_train)
    logger.info(
        "trained window g_%d..g_%d  g_last=%.4f  v[0]=Lambda/g_last=%.5f",
        train_start,
        train_start + args.k - 1,
        g_last_train,
        float(vec_train[0]),
    )

    kinds = list(KINDS)
    blocks = []
    for start in starts:
        win = window(start, args.k)
        for variant in ("rescaled", "raw"):
            blk = score_window(
                vec_train=vec_train,
                g_last_train=g_last_train,
                win=win,
                kinds=kinds,
                reps=args.reps,
                N=args.N,
                n_sectors=args.sectors,
                master_seed=args.master_seed,
                variant=variant,
            )
            blk["window_start"] = start
            blk["window_end"] = start + args.k - 1
            blk["is_trained_window"] = start == train_start
            blocks.append(blk)

    print("\n=== HELD-OUT ORDINATE TRANSFER (frozen knobs, no refit) ===")
    print(f"  knobs fit on g_{train_start}..g_{train_start + args.k - 1}")
    rows = []
    for blk in blocks:
        z = blk["by_kind"]["zeta"]["F_mean"]
        pla = {k: blk["by_kind"][k]["F_mean"] for k in PLAUSIBLE if k in blk["by_kind"]}
        min_pla = min(pla.values()) if pla else float("nan")
        ratio = min_pla / z if z > 0 else float("inf")
        tag = "TRAINED" if blk["is_trained_window"] else "held-out"
        rows.append(
            {
                "window": f"g_{blk['window_start']}..{blk['window_end']}",
                "variant": blk["variant"],
                "trained": blk["is_trained_window"],
                "F_zeta": z,
                "min_F_plausible_null": min_pla,
                "advantage_ratio": ratio,
            }
        )
        print(
            f"  {tag:8s} g_{blk['window_start']:>2d}..{blk['window_end']:<2d} "
            f"{blk['variant']:9s}  F_zeta={z:9.6f}  min_null={min_pla:9.6f}  "
            f"advantage={ratio:7.2f}x"
        )

    trained = [r for r in rows if r["trained"]]
    heldout = [r for r in rows if not r["trained"]]
    base_ratio = max((r["advantage_ratio"] for r in trained), default=float("nan"))
    held_ratio = max((r["advantage_ratio"] for r in heldout), default=float("nan"))

    print(
        f"\n  best advantage on trained window : {base_ratio:.2f}x"
        f"\n  best advantage on held-out windows: {held_ratio:.2f}x"
    )
    survives = held_ratio >= 0.5 * base_ratio and held_ratio > 2.0
    if heldout:
        if survives:
            print("  -> advantage SURVIVES transfer to unseen ordinates")
        else:
            print("  -> advantage COLLAPSES off the trained window (tuned-point artifact)")

    payload = {
        "rows": rows,
        "blocks": blocks,
        "trained_window_start": train_start,
        "best_advantage_trained": base_ratio,
        "best_advantage_heldout": held_ratio,
        "survives_transfer": bool(survives) if heldout else None,
        "knobs": knobs,
        "v_train_dimensionless": vec_train.tolist(),
        "config": {
            "N": args.N,
            "k": args.k,
            "n_sectors": args.sectors,
            "windows": starts,
            "reps": args.reps,
            "master_seed": args.master_seed,
        },
        "notes": {
            "zeros_source": "mpmath.zetazero, verified (see realm/validate/zeros.py)",
            "transfer_variants": {
                "rescaled": "preserve dimensionless v[0]; Lambda = v[0]*g_last(window)",
                "raw": "preserve absolute Lambda from the trained window",
            },
        },
        "ontology": "frozen_knob_transfer_not_lambda_eq_gamma",
    }
    write_json(args.json, payload)
    print(f"wrote {args.json}", file=sys.stderr)
    return 0 if (not heldout or survives) else 2


if __name__ == "__main__":
    raise SystemExit(main())
