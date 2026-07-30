#!/usr/bin/env python3
"""CLI: Sub-spec II Stages 6–8 window filtration / rigidity / persistence.

Does not modify dual-gate LengthPolicy. Never λ=γ.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from realm.validate.cross_window import (
    compare_arms_filtration,
    existence_arm_scan,
    score_rigidity_filtration,
)
from realm.validate.stage9_tournament import run_rigidity_tournament, save_tournament
from realm.validate.window_filtration import load_champion_knobs, score_window_filtration

logger = logging.getLogger("window_filtration")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Sub-spec II Stage 6 filtration / Stage 7 rigidity / Stage 8 persistence"
    )
    p.add_argument(
        "--stage",
        choices=("6", "7", "8", "7+8", "9lite", "9"),
        default="6",
        help="6=filtration, 7=rigidity, 8/7+8=persistence, 9lite=existence, 9=powered rigidity",
    )
    p.add_argument(
        "-M",
        "--n-instances",
        type=int,
        default=59,
        help="Stage 9 null spectra per stochastic arm (design ≥59)",
    )
    p.add_argument("--knobs", type=str, default="evolve_result.json")
    p.add_argument("-W", "--n-windows", type=int, default=7)
    p.add_argument("-k", "--n-zeros", type=int, default=14)
    p.add_argument("-N", type=int, default=13)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--arm-b", type=str, default="gue", help="null arm for stages 7+8")
    p.add_argument(
        "--component",
        type=str,
        default="density_return_l1",
        help="component key for advantage (Stage 8)",
    )
    p.add_argument("--json", type=str, default=None)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument(
        "--g5-span",
        action="store_true",
        help="Anchor omega_span to window-1 g[-1]/g[0] (G5 window-invariant ratio)",
    )
    p.add_argument("--omega-span", type=float, default=None, help="Explicit omega_span override")
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.v else logging.INFO)

    stage = args.stage
    dest = Path(
        args.json
        or {
            "6": "out/window_filtration_stage6.json",
            "7": "out/window_filtration_stage7.json",
            "8": "out/window_filtration_stage8.json",
            "7+8": "out/window_filtration_stage7_8.json",
            "9lite": "out/window_filtration_stage9lite.json",
            "9": "out/window_filtration_stage9.json",
        }[stage]
    )
    dest.parent.mkdir(parents=True, exist_ok=True)

    if stage == "6":
        kn = load_champion_knobs(args.knobs)
        out = score_window_filtration(
            kn,
            n_windows=int(args.n_windows),
            n_zeros=int(args.n_zeros),
            N=int(args.N),
            n_sectors=int(args.sectors),
            use_g5_span=bool(args.g5_span),
            omega_span=args.omega_span,
        )
        summary = {k: v for k, v in out.items() if k not in ("windows", "component_matrix")}
        summary["window_summary"] = [
            {
                "index": w["index"],
                "disjoint": w["disjoint"],
                "is_degenerate": w["is_degenerate"],
                "reasons": w["degeneracy"].get("reasons"),
                "omega_ratio": w.get("omega_ratio"),
                "corr_penalty": w["components"].get("corr_penalty"),
                "density_return_l1": w["components"].get("density_return_l1"),
                "stationarity": w["components"].get("stationarity"),
                "crit_coverage": w["components"].get("crit_coverage"),
            }
            for w in out["windows"]
        ]
        summary["component_matrix"] = out["component_matrix"]
        dest.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        g5 = out.get("g5") or {}
        logger.info(
            "Stage6 W=%s dof_ratio=%.3f pass_dof=%s guard_clear=%s/%s stage6_pass=%s "
            "g5_span=%s g5_pass=%s rel_spread=%s → %s",
            out["W"],
            out["dof_ratio"],
            out["pass_dof"],
            out["n_windows_guard_clear"],
            out["W"],
            out["stage6_pass"],
            out.get("omega_span"),
            g5.get("pass_within_5pct"),
            g5.get("rel_spread"),
            dest,
        )
        return 0 if out["pass_dof"] else 2

    if stage == "7":
        out = score_rigidity_filtration(
            n_windows=int(args.n_windows),
            n_zeros=int(args.n_zeros),
            arm="zeta",
            rng_seed=int(args.seed),
        )
        # strip heavy per-window raw profiles if any
        slim = {k: v for k, v in out.items() if k != "windows"}
        slim["window_carriers"] = [
            {"index": w["index"], "carrier": w["rigidity"]["carrier"]} for w in out["windows"]
        ]
        dest.write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")
        logger.info(
            "Stage7 arm=zeta W=%s carrier_mean=%.6g carrier_std=%.6g → %s",
            out["W"],
            out["carrier_mean"],
            out["carrier_std"],
            dest,
        )
        return 0

    if stage == "9lite":
        kn = load_champion_knobs(args.knobs)
        out = existence_arm_scan(
            kn,
            arms=("zeta", "arith", "gue", "poisson"),
            n_windows=int(args.n_windows),
            n_zeros=int(args.n_zeros),
            N=int(args.N),
            n_sectors=int(args.sectors),
            rng_seed=int(args.seed),
        )
        dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        logger.info(
            "Stage9-lite dens_rank=%s arith_beats_zeta=%s any_stage8_or=%s → %s",
            out["density_return_rank_lower_better"],
            out["arith_beats_zeta_existence"],
            out["any_stage8_pass"],
            dest,
        )
        return 0

    if stage == "9":
        out = run_rigidity_tournament(
            M=int(args.n_instances),
            n_windows=int(args.n_windows),
            n_zeros=int(args.n_zeros),
            base_seed=int(args.seed),
            progress=lambda m: logger.info("%s", m),
        )
        save_tournament(out, dest)
        s = out["summary"]
        logger.info(
            "Stage9 M=%s gue_sig=%s poisson_sig=%s gue_s8=%.3f poisson_s8=%.3f elapsed=%.1fs → %s",
            out["M"],
            s.get("zeta_beats_gue_bonferroni"),
            s.get("zeta_beats_poisson_bonferroni"),
            s.get("gue_stage8_fraction") or 0.0,
            s.get("poisson_stage8_fraction") or 0.0,
            s.get("elapsed_s") or 0.0,
            dest,
        )
        return 0

    # stages 8 and 7+8
    kn = load_champion_knobs(args.knobs)
    out = compare_arms_filtration(
        kn,
        arm_a="zeta",
        arm_b=str(args.arm_b),
        n_windows=int(args.n_windows),
        n_zeros=int(args.n_zeros),
        N=int(args.N),
        n_sectors=int(args.sectors),
        component_key=str(args.component),
        rng_seed=int(args.seed),
        # Stages 7–8 default to G5 span (cross-window work requires it)
        use_g5_span=True if args.omega_span is None else False,
        omega_span=args.omega_span,
    )
    dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    cp = out["component_persistence"]
    rp = out["rigidity_persistence"]
    logger.info(
        "Stage7+8 ζ vs %s W=%s component lifespan=%s/%s pass=%s | rigidity lifespan=%s/%s pass=%s → %s",
        args.arm_b,
        out["W"],
        cp["max_lifespan"],
        cp["threshold_ceil_W_over_2"],
        cp["stage8_pass"],
        rp["max_lifespan"],
        rp["threshold_ceil_W_over_2"],
        rp["stage8_pass"],
        dest,
    )
    # exit 0 always for measurement; stage8_pass is in JSON
    return 0


if __name__ == "__main__":
    sys.exit(main())
