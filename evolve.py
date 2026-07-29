#!/usr/bin/env python3
"""Evolve: meet lock → project valleys → write generation log. Go."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.lock_key import meet_lock
from realm.projection import build_moduli_landscape, run_projection_protocol, test_valley_occupancy


def plot_evolve(meet, proj: dict, path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))

    ax = axes[0, 0]
    Rs = [h["R"] for h in meet.history]
    ax.semilogy(np.maximum(Rs, 1e-6), "c.-", ms=2)
    ax.axhline(meet.threshold, color="r", ls="--", label=f"threshold={meet.threshold}")
    ax.set_title(f"Evolution of R → {'LOCKED' if meet.locked else 'UNSEALED'}")
    ax.set_xlabel("Keymaker generation")
    ax.set_ylabel("R")
    ax.legend()
    ax.grid(True, alpha=0.3)

    ax = axes[0, 1]
    b = meet.residual
    ax.bar(
        ["stat", "corr", "cov", "return"],
        [b.shape_l1, b.corr_penalty, b.crit_coverage, b.return_map_err],
        color=["#00ff88", "#00aaff", "#ffaa00", "#ff4466"],
    )
    ax.set_title(f"Best R={b.total:.4f}")
    ax.grid(True, axis="y", alpha=0.3)

    ax = axes[1, 0]
    land = build_moduli_landscape(
        Lambda=meet.best_knobs.get("Lambda"),
        omega_scale=float(meet.best_knobs.get("omega_scale", 1.0)),
        weight_power=float(meet.best_knobs.get("weight_power", 1.0)),
    )
    # apply tier knobs by rebuilding action through Deriver field
    ax.plot(land.sample_theta, land.sample_V, "b-", lw=1.5)
    for v in land.valleys:
        ax.axvline(v["theta"], color="g", alpha=0.35, ls="--")
    for th in meet.key.thetas:
        ax.plot(th, float(land.V(th)), "mo", ms=8, markeredgecolor="k")
    ax.set_title("Evolved mold + key pins")
    ax.set_xlabel("θ")
    ax.set_ylabel("V")
    ax.grid(True, alpha=0.3)

    ax = axes[1, 1]
    ax.axis("off")
    s = proj.get("summary", {})
    lines = [
        "EVOLVE GENERATION",
        f"time: {datetime.now(timezone.utc).isoformat()}",
        f"lock: {'LOCKED' if meet.locked else 'UNSEALED'}  R={meet.residual.total:.4f}",
        f"search: {meet.search_method}",
        f"iters: {meet.iterations}",
        f"knobs: Λ={meet.best_knobs.get('Lambda', 0):.2f}",
        f"  ωs={meet.best_knobs.get('omega_scale', 0):.3f} "
        f"wp={meet.best_knobs.get('weight_power', 0):.3f}",
        f"  tier={meet.best_knobs.get('tier_split', 0):.2f} "
        f"boost={meet.best_knobs.get('low_boost', 0):.2f}",
        "",
        f"valley occupancy: {s.get('occupancy_fraction')}",
        f"coutsias occupancy: {s.get('coutsias_occupancy')}",
        f"affine a,b: {s.get('affine_a')}, {s.get('affine_b')}",
        "",
        "ontology: projection + Crit seal",
        "not: λ = actual γ_n",
    ]
    ax.text(
        0.05,
        0.95,
        "\n".join(str(x) for x in lines),
        transform=ax.transAxes,
        va="top",
        family="monospace",
        fontsize=9,
        color="#e0ffe8",
        bbox=dict(boxstyle="round", facecolor="#05140a", edgecolor="#00ff88"),
    )

    fig.suptitle("GO & EVOLVE  ·  Keymaker × projection mold", fontsize=13, fontweight="bold", color="#00ff88")
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="#020805")
    plt.close(fig)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Evolve lock–key + projection until sealed/molded")
    p.add_argument("-N", type=int, default=11)
    p.add_argument("-k", type=int, default=12)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--threshold", type=float, default=0.10)
    p.add_argument("--max-iter", type=int, default=56)
    p.add_argument("--json", type=Path, default=Path("evolve_result.json"))
    p.add_argument("--plot", type=Path, default=Path("evolve.png"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    logging.info("=== EVOLVE: meet_lock ===")
    meet = meet_lock(
        N=args.N,
        n_zeros=args.k,
        n_sectors=args.sectors,
        threshold=args.threshold,
        max_iter=args.max_iter,
    )

    logging.info("=== EVOLVE: projection on SAME sealed action/valleys ===")
    thetas = meet.key.thetas
    # Critical: mold must be the forged action, not a default rebuild
    landscape = build_moduli_landscape(
        field=meet.derivation.field,
        Lambda=meet.best_knobs.get("Lambda"),
        omega_scale=float(meet.best_knobs.get("omega_scale", 1.0)),
        weight_power=float(meet.best_knobs.get("weight_power", 1.0)),
        tier_split=float(meet.best_knobs.get("tier_split", 0.45)),
        low_boost=float(meet.best_knobs.get("low_boost", 1.0)),
        action=meet.derivation.action,
        critical=meet.derivation.critical,
    )
    test = test_valley_occupancy(
        thetas,
        landscape=landscape,
        labels=[f"key_{i+1}" for i in range(len(thetas))],
        spectral_gaps=meet.key.spectral_gaps,
    )
    proj = {
        "ontology": "holographic_projection_zeta_scaffolding",
        "sealed_knobs": meet.best_knobs,
        "lock_key_sealed": meet.locked,
        "lock_key_R": meet.residual.total,
        "moduli_landscape": landscape.to_dict(),
        "derived_sector_valley_test": test.to_dict(),
        "summary": {
            **test.summary(),
            "lock_key_sealed": meet.locked,
            "meet_R": meet.residual.total,
            "meet_aligned_occupancy": test.occupancy_fraction,
            "winner_criterion": (
                "keys sit in Crit valleys of the sealed projected landscape; "
                "affine is projection signature; not λ=γ"
            ),
        },
    }
    proj["meet_aligned_valley_test"] = test.to_dict()

    out = {
        "generation": datetime.now(timezone.utc).isoformat(),
        "meet": meet.summary(),
        "meet_knobs": meet.best_knobs,
        "projection_summary": proj["summary"],
        "valley_verdict": test.verdict,
        "evolved": {
            "locked": meet.locked,
            "R": meet.residual.total,
            "occupancy": test.occupancy_fraction,
            "status": (
                "EVOLVED_SEAL"
                if meet.locked and test.occupancy_fraction >= 0.5
                else "EVOLVING"
            ),
        },
    }
    print(json.dumps(out["evolved"], indent=2))
    print(json.dumps(out["meet"], indent=2))

    args.json.write_text(json.dumps(out, indent=2), encoding="utf-8")
    # full archives
    Path("lock_meet.json").write_text(json.dumps(meet.to_dict(), indent=2), encoding="utf-8")
    Path("projection_result.json").write_text(json.dumps(proj, indent=2), encoding="utf-8")
    plot_evolve(meet, proj, args.plot)

    print(f"wrote {args.json}", file=sys.stderr)
    print(f"wrote {args.plot}", file=sys.stderr)
    print(out["evolved"]["status"], file=sys.stderr)
    print(test.verdict, file=sys.stderr)

    return 0 if out["evolved"]["status"] == "EVOLVED_SEAL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
