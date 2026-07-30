#!/usr/bin/env python3
"""Held-out ζ window transfer — pre-registered protocol.

Fit/report split (Finding 1):
  train  : γ₁–γ₁₄  (champion knobs were optimized here)
  hold_a : γ₁₅–γ₂₈
  hold_b : γ₂₉–γ₄₂

Frozen knobs from evolve_result.json. No refit. Scores real mpmath zeros
(not mean-gap extrapolation). Reports legacy + informative residual for
each window, vs scramble/gue/poisson/arith controls on the same window span.

If ζ preference is real under the residual, train margin should survive
on hold_a. Finding 1: it does not under legacy R.
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

from realm.validate.harness import score_configuration
from realm.validate.report import load_knobs, write_json
from realm.validate.seeds import make_seed
from realm.validate.zeros import verify_seed_table, zeros_window

logger = logging.getLogger("transfer")

WINDOWS = {
    "train_g1_14": (1, 14),
    "hold_g15_28": (15, 14),
    "hold_g29_42": (29, 14),
}
CONTROLS = ("scramble", "gue", "poisson", "arith")


def _rescale_knobs_for_window(knobs: dict, train_g: np.ndarray, win_g: np.ndarray) -> dict:
    """Preserve dimensionless Λ / g_last ratio (principled transfer)."""
    kn = dict(knobs)
    g_train = float(train_g[-1])
    g_win = float(win_g[-1])
    if g_train > 0 and kn.get("Lambda") is not None:
        ratio = float(kn["Lambda"]) / g_train
        kn["Lambda"] = ratio * g_win
    return kn


def _score_window(
    label: str,
    gammas: np.ndarray,
    knobs: dict,
    *,
    N: int,
    n_sectors: int,
    rng: np.random.Generator,
    fitness: str,
) -> dict:
    n_zeros = int(gammas.size)
    base = score_configuration(
        kind="zeta",
        knobs=knobs,
        N=N,
        n_zeros=n_zeros,
        n_sectors=n_sectors,
        rng_seed=0,
        gammas=gammas,
        fitness=fitness,
    )
    base["window"] = label
    controls = {}
    for kind in CONTROLS:
        # controls share the same span as the window's real zeros
        # build synthetic seeds on that span via make_seed then affine-map
        synth = make_seed(kind, n_zeros, rng)
        # re-anchor to window endpoints for fair span match
        g0, g1 = float(gammas[0]), float(gammas[-1])
        s0, s1 = float(synth[0]), float(synth[-1])
        if abs(s1 - s0) < 1e-15:
            mapped = gammas.copy()
        else:
            mapped = g0 + (synth - s0) * (g1 - g0) / (s1 - s0)
        sc = score_configuration(
            kind=kind,
            knobs=knobs,
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sectors,
            rng_seed=int(rng.integers(0, 2**31 - 1)),
            gammas=mapped,
            fitness=fitness,
        )
        controls[kind] = {
            "R": sc["R"],
            "R_legacy": sc["R_legacy"],
            "R_informative": sc["R_informative"],
            "occupancy": sc["occupancy"],
            "F": sc["F"],
        }
    best_null_leg = min(c["R_legacy"] for c in controls.values())
    best_null_inf = min(c["R_informative"] for c in controls.values())
    return {
        "window": label,
        "n_zeros": n_zeros,
        "gamma_range": [float(gammas[0]), float(gammas[-1])],
        "zeta": {
            "R": base["R"],
            "R_legacy": base["R_legacy"],
            "R_informative": base["R_informative"],
            "occupancy": base["occupancy"],
            "F": base["F"],
            "diagnostics": base.get("diagnostics"),
        },
        "controls": controls,
        "advantage_legacy": (
            best_null_leg / max(base["R_legacy"], 1e-15)
            if base["R_legacy"] > 0
            else float("inf")
        ),
        "advantage_informative": (
            best_null_inf / max(base["R_informative"], 1e-15)
            if base["R_informative"] > 0
            else float("inf")
        ),
        "best_null_legacy": best_null_leg,
        "best_null_informative": best_null_inf,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Held-out ζ window transfer protocol")
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("-N", type=int, default=13)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument(
        "--fitness",
        choices=("informative", "legacy"),
        default="informative",
        help="primary fitness column (both always reported)",
    )
    p.add_argument("--json", type=Path, default=Path("transfer_result.json"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    vrf = verify_seed_table()
    logger.info("seed table vs mpmath: %s", vrf)
    if not vrf["ok"]:
        print("seed table mismatch vs mpmath", vrf, file=sys.stderr)
        return 3

    knobs = load_knobs(args.knobs)
    train_g = zeros_window(*WINDOWS["train_g1_14"])
    rng = np.random.default_rng(42)
    rows = []
    for label, (start, count) in WINDOWS.items():
        g = zeros_window(start, count)
        kn = _rescale_knobs_for_window(knobs, train_g, g)
        row = _score_window(
            label,
            g,
            kn,
            N=args.N,
            n_sectors=args.sectors,
            rng=rng,
            fitness=args.fitness,
        )
        rows.append(row)
        logger.info(
            "%s  Rζ_leg=%.4f  best_null_leg=%.4f  adv_leg=%.2f×  "
            "Rζ_info=%.4f  adv_info=%.2f×  occ=%.0f%%",
            label,
            row["zeta"]["R_legacy"],
            row["best_null_legacy"],
            row["advantage_legacy"],
            row["zeta"]["R_informative"],
            row["advantage_informative"],
            100 * row["zeta"]["occupancy"],
        )

    print("\n=== TRANSFER (frozen knobs, real zeros) ===")
    print(f"  seed_table_verified={vrf['ok']}  max_err={vrf['max_abs_err']:.2e}")
    for row in rows:
        print(
            f"  {row['window']:14s}  Rζ_leg={row['zeta']['R_legacy']:.4f}  "
            f"null_leg={row['best_null_legacy']:.4f}  adv_leg={row['advantage_legacy']:.2f}×  "
            f"Rζ_info={row['zeta']['R_informative']:.4f}  "
            f"adv_info={row['advantage_informative']:.2f}×  "
            f"occ={row['zeta']['occupancy']:.0%}"
        )
    train_adv = rows[0]["advantage_legacy"]
    hold_adv = rows[1]["advantage_legacy"]
    print(
        f"\n  headline: train legacy advantage {train_adv:.1f}× → "
        f"hold_g15_28 {hold_adv:.2f}×  "
        f"({'TRANSFER FAILS' if hold_adv < 1.2 else 'holds'})"
    )

    payload = {
        "protocol": "pre_registered_window_transfer",
        "windows": WINDOWS,
        "knob_transfer": "preserve_Lambda_over_g_last",
        "seed_table_verify": vrf,
        "rows": rows,
        "knobs_train": knobs,
        "zeta_preference_on_holdout": hold_adv >= 1.2,
        "ontology": "not_lambda_eq_gamma",
        "note": (
            "Train margin without holdout survival is seating, not ζ structure. "
            "Legacy R is known-degenerate; informative R is density-return only."
        ),
    }
    write_json(args.json, payload)
    print(f"wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
