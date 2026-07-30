#!/usr/bin/env python3
"""CLI: Sub-spec II Stage 6 window filtration on champion (or custom) knobs.

Does not modify dual-gate LengthPolicy. Never λ=γ.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from realm.validate.window_filtration import load_champion_knobs, score_window_filtration

logger = logging.getLogger("window_filtration")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Stage 6 multi-window independent-baseline filtration")
    p.add_argument("--knobs", type=str, default="evolve_result.json")
    p.add_argument("-W", "--n-windows", type=int, default=7)
    p.add_argument("-k", "--n-zeros", type=int, default=14)
    p.add_argument("-N", type=int, default=13)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--json", type=str, default="out/window_filtration_stage6.json")
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.v else logging.INFO)

    kn = load_champion_knobs(args.knobs)
    out = score_window_filtration(
        kn,
        n_windows=int(args.n_windows),
        n_zeros=int(args.n_zeros),
        N=int(args.N),
        n_sectors=int(args.sectors),
    )
    summary = {
        k: v
        for k, v in out.items()
        if k not in ("windows", "component_matrix")
    }
    summary["window_summary"] = [
        {
            "index": w["index"],
            "disjoint": w["disjoint"],
            "is_degenerate": w["is_degenerate"],
            "reasons": w["degeneracy"].get("reasons"),
            "corr_penalty": w["components"].get("corr_penalty"),
            "density_return_l1": w["components"].get("density_return_l1"),
            "stationarity": w["components"].get("stationarity"),
            "crit_coverage": w["components"].get("crit_coverage"),
        }
        for w in out["windows"]
    ]
    summary["component_matrix"] = out["component_matrix"]

    dest = Path(args.json)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "Stage6 W=%s dof_ratio=%.3f pass_dof=%s guard_clear=%s/%s stage6_pass=%s → %s",
        out["W"],
        out["dof_ratio"],
        out["pass_dof"],
        out["n_windows_guard_clear"],
        out["W"],
        out["stage6_pass"],
        dest,
    )
    return 0 if out["pass_dof"] else 2


if __name__ == "__main__":
    sys.exit(main())
