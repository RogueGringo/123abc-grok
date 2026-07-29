#!/usr/bin/env python3
"""Winner protocol: projected moduli landscape + valley occupancy.

Implements the holographic reading:
  zeta zeros = higher-D scaffolding
  3D geometry = shadow / quasicrystal projection
  affine ax+b = signature of projection (not a cheat)
  test = do stable folds sit in valleys of the projected mold?
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.projection import run_projection_protocol


def plot_projection(payload: dict, path: Path) -> None:
    land = payload["moduli_landscape"]
    test = payload["derived_sector_valley_test"]
    valleys = land["valleys"]
    probes = test["probes"]

    # rebuild V curve from stored samples if we re-run landscape — use probes + valleys
    from realm.projection import build_moduli_landscape

    kn = payload.get("sealed_knobs") or {}
    landscape = build_moduli_landscape(
        Lambda=kn.get("Lambda"),
        omega_scale=float(kn.get("omega_scale", 1.0)),
        weight_power=float(kn.get("weight_power", 1.0)),
    )

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))

    # Landscape + valleys + conformations
    ax = axes[0, 0]
    ax.plot(landscape.sample_theta, landscape.sample_V, "b-", lw=2, label="V(θ) projected moduli")
    for v in valleys:
        ax.axvline(v["theta"], color="g", alpha=0.4, ls="--")
        ax.plot(v["theta"], v["S"], "g^", ms=10)
    for p in probes:
        col = "#00cc66" if p["in_valley"] else "#cc3333"
        ax.plot(p["theta"], p["V_at"], "o", color=col, ms=9, markeredgecolor="k")
    ax.set_xlabel("θ (config / holonomy)")
    ax.set_ylabel("V_Λ(θ)")
    ax.set_title("Projected mold: valleys = green △, conformations = ○")
    ax.grid(True, alpha=0.3)

    # Distances to valley
    ax = axes[0, 1]
    labs = [p["label"] for p in probes]
    dists = [p["distance_to_valley"] for p in probes]
    colors = ["#00cc66" if p["in_valley"] else "#cc3333" for p in probes]
    ax.bar(labs, dists, color=colors)
    ax.axhline(test["basin_radius"], color="k", ls="--", label="basin radius")
    ax.set_ylabel("dist → nearest valley")
    ax.set_title(f"Occupancy {test['occupancy_fraction']:.0%}  mean d={test['mean_distance_to_valley']:.3f}")
    ax.tick_params(axis="x", rotation=45)
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)

    # Affine projection signature
    ax = axes[1, 0]
    aff = test["affine_projection_signature"]
    idx = np.arange(1, len(probes) + 1)
    th_sorted = np.sort([p["theta"] for p in probes])
    pred = aff["a"] * idx + aff["b"]
    ax.plot(idx, th_sorted, "ko", label="physical θ (sorted)")
    ax.plot(idx, pred, "b-", lw=2, label=f"affine a={aff['a']:.3g} b={aff['b']:.3g}")
    ax.set_title("Affine = projection signature (not a cheat)")
    ax.set_xlabel("order index")
    ax.set_ylabel("θ")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.text(
        0.02,
        0.02,
        "ax+b is the shadow map of higher-D scaffolding",
        transform=ax.transAxes,
        fontsize=8,
        style="italic",
    )

    # Manifesto panel
    ax = axes[1, 1]
    ax.axis("off")
    c_occ = payload["summary"].get("coutsias_occupancy")
    lines = [
        "WINNER PROTOCOL",
        "ontology: holographic projection",
        "zeta zeros = scaffolding (not E-levels)",
        "3D folds = quasicrystal shadow",
        "affine ax+b = projection signature",
        "",
        f"lock∩key sealed: {payload.get('lock_key_sealed')}",
        f"R: {payload.get('lock_key_R')}",
        f"valley occupancy: {test['occupancy_fraction']:.0%}",
        f"coutsias occupancy: {c_occ}",
        "",
        test["verdict"][:120],
        "",
        "NOT tested: λ ≈ 14.13, 21.02, …",
        "TESTED: shapes fit the projected mold",
    ]
    ax.text(
        0.05,
        0.95,
        "\n".join(lines),
        transform=ax.transAxes,
        va="top",
        family="monospace",
        fontsize=9,
        color="#eee",
        bbox=dict(boxstyle="round", facecolor="#0f0f1a", edgecolor="#00ff88", alpha=0.95),
    )

    fig.suptitle(
        "PROJECTION PROTOCOL  ·  moduli landscape from zeta lattice  ·  valley occupancy",
        fontsize=12,
        fontweight="bold",
        color="#00ff88",
    )
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Holographic projection / valley mold test")
    p.add_argument("-N", type=int, default=11)
    p.add_argument("-k", type=int, default=12)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--no-seal", action="store_true", help="skip meet_lock knobs")
    p.add_argument("--json", type=Path, default=Path("projection_result.json"))
    p.add_argument("--plot", type=Path, default=Path("projection.png"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    payload = run_projection_protocol(
        N=args.N,
        n_zeros=args.k,
        n_sectors=args.sectors,
        use_sealed_knobs=not args.no_seal,
    )
    print(json.dumps(payload["summary"], indent=2))
    args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    plot_projection(payload, args.plot)
    print(f"wrote {args.json}", file=sys.stderr)
    print(f"wrote {args.plot}", file=sys.stderr)
    print(payload["derived_sector_valley_test"]["verdict"], file=sys.stderr)

    occ = payload["summary"]["occupancy_fraction"]
    return 0 if occ >= 0.5 else 2


if __name__ == "__main__":
    raise SystemExit(main())
