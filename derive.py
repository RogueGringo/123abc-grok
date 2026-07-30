#!/usr/bin/env python3
"""CLI: continue deriving geometry off the zeta spectral action."""

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

from realm.derive import Deriver, derive


def plot_derivation(result, path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))

    # S(θ)
    ax = axes[0, 0]
    th = np.linspace(0, 2 * np.pi, 600)
    ax.plot(th, result.action.S(th), "b-", lw=2, label="S_Λ(θ)")
    for c in result.critical:
        col = {"minimum": "g", "maximum": "r", "inflection": "gray"}.get(c["kind"], "orange")
        ax.axvline(c["theta"], color=col, alpha=0.5, ls="--")
        ax.plot(c["theta"], c["S"], "o", color=col)
    ax.set_title("D2–D3 Spectral action & critical holonomies")
    ax.set_xlabel("θ (U(1) holonomy)")
    ax.set_ylabel("S_Λ(θ)")
    ax.grid(True, alpha=0.3)

    # geometries xy
    ax = axes[0, 1]
    colors = plt.cm.viridis(np.linspace(0.1, 0.9, max(len(result.sectors), 1)))
    for i, s in enumerate(result.sectors):
        p = s.positions
        ax.plot(p[:, 0], p[:, 1], "o-", ms=3, color=colors[i], label=f"θ={s.twist:.2f}")
    ax.set_aspect("equal")
    ax.set_title("D4 Multi-mode C_N from θ*")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # spectra
    ax = axes[1, 0]
    for i, sp in enumerate(result.spectra):
        ax.plot(sp.eigenvalues, "o-", ms=2, color=colors[i % len(colors)], label=f"S{sp.sector_id}")
    ax.set_title("D5 Sheaf spectra of derived geometry (≠ γ_n)")
    ax.set_xlabel("k")
    ax.set_ylabel("λ_k")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # S vs gap
    ax = axes[1, 1]
    S_at = [float(result.action.S(s.twist)) for s in result.sectors]
    gaps = [s.spectral_gap for s in result.spectra]
    ax.scatter(S_at, gaps, c=range(len(gaps)), cmap="viridis", s=80, edgecolors="k")
    for i, s in enumerate(result.sectors):
        ax.annotate(f"{s.twist:.2f}", (S_at[i], gaps[i]), fontsize=7)
    ax.set_xlabel("S_Λ(θ*)")
    ax.set_ylabel("λ_gap of L_F(θ*)")
    d6 = next(st for st in result.steps if st.id == "D6")
    corr = d6.payload.get("corr_S_vs_gap", float("nan"))
    ax.set_title(f"D6 corr(S, λ_gap)={corr:.3f} — structure not identity")
    ax.grid(True, alpha=0.3)

    fig.suptitle(
        "DERIVATION  ·  γ-seed → S(θ) → Crit → geometry → sheaf  (off zetas, not actual zeros)",
        fontsize=12,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Derive geometry off the zeta spectral action")
    p.add_argument("-N", type=int, default=11)
    p.add_argument("-k", type=int, default=12, help="number of zeta zeros in the seed")
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--json", type=Path, default=Path("derivation_result.json"))
    p.add_argument("--plot", type=Path, default=Path("derivation.png"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    result = derive(N=args.N, n_zeros=args.k, n_sectors=args.sectors)
    summary = result.summary()
    print(json.dumps(summary, indent=2))

    args.json.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    plot_derivation(result, args.plot)
    print(f"wrote {args.json}", file=sys.stderr)
    print(f"wrote {args.plot}", file=sys.stderr)

    # print ladder
    print("\nDERIVATION LADDER", file=sys.stderr)
    for st in result.steps:
        print(f"  {st.id}  {st.title}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
