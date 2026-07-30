#!/usr/bin/env python3
"""Master Lock meets the Keymaker — refine until consistency residual seals."""

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

from realm.lock_key import meet_lock


def plot_meet(result, path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))

    # residual history
    ax = axes[0, 0]
    Rs = [h["R"] for h in result.history]
    ax.plot(Rs, "c.-", lw=1.5)
    ax.axhline(result.threshold, color="r", ls="--", label=f"threshold={result.threshold}")
    ax.set_xlabel("Keymaker attempt")
    ax.set_ylabel("lock–key residual R")
    ax.set_title("Refinement trajectory")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # breakdown bars
    ax = axes[0, 1]
    b = result.residual
    names = ["stationarity", "corr", "coverage", "pin_align"]
    vals = [b.shape_l1, b.corr_penalty, b.crit_coverage, b.return_map_err]
    ax.bar(names, vals, color=["#e94560", "#0f3460", "#16213e", "#533483"])
    ax.set_ylim(0, max(1.0, max(vals) * 1.2))
    ax.set_title(f"Best R={b.total:.4f}  locked={result.locked}")
    ax.grid(True, axis="y", alpha=0.3)

    # lock minima vs key thetas
    ax = axes[1, 0]
    lock_m = result.lock.minima_theta
    key_t = result.key.thetas
    ax.scatter(lock_m, np.zeros_like(lock_m), c="k", s=100, marker="|", label="lock minima θ*")
    ax.scatter(key_t, np.ones_like(key_t) * 0.1, c="m", s=80, marker="o", label="key thetas")
    for t in lock_m:
        ax.axvline(t, color="k", alpha=0.2, ls=":")
    ax.set_yticks([0, 0.1])
    ax.set_yticklabels(["LOCK", "KEY"])
    ax.set_xlabel("θ")
    ax.set_title("Lock cylinder vs Key pins")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # S vs gap at meeting
    ax = axes[1, 1]
    ax.scatter(result.key.S_at, result.key.spectral_gaps, c="orange", s=90, edgecolors="k")
    for i, th in enumerate(result.key.thetas):
        ax.annotate(f"{th:.2f}", (result.key.S_at[i], result.key.spectral_gaps[i]), fontsize=7)
    ax.set_xlabel("S_Λ(θ) on key")
    ax.set_ylabel("λ_gap of key geometry")
    status = "LOCKED" if result.locked else "UNSEALED"
    kn = result.best_knobs
    ax.set_title(
        f"{status} · Λ={kn.get('Lambda', 0):.1f} ωs={kn.get('omega_scale', 0):.2f} "
        f"boost={kn.get('low_boost', 1):.2f}"
    )
    ax.grid(True, alpha=0.3)

    color = "#00ff88" if result.locked else "#e94560"
    method = getattr(result, "search_method", "search")
    fig.suptitle(
        f"MASTER LOCK MEETS KEYMAKER  ·  {status}  ·  R={result.residual.total:.4f}  ·  {method}",
        fontsize=12,
        fontweight="bold",
        color=color,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Refine Keymaker until lock opens")
    p.add_argument("-N", type=int, default=11)
    p.add_argument("-k", type=int, default=12)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--threshold", type=float, default=0.12)
    p.add_argument("--max-iter", type=int, default=48)
    p.add_argument("--json", type=Path, default=Path("lock_meet.json"))
    p.add_argument("--plot", type=Path, default=Path("lock_meet.png"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    result = meet_lock(
        N=args.N,
        n_zeros=args.k,
        n_sectors=args.sectors,
        threshold=args.threshold,
        max_iter=args.max_iter,
    )
    summary = result.summary()
    print(json.dumps(summary, indent=2))

    # Full dump without huge laplacian matrices
    payload = result.to_dict()
    # strip heavy eigens from nested derivation if present
    args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    plot_meet(result, args.plot)
    print(f"wrote {args.json}", file=sys.stderr)
    print(f"wrote {args.plot}", file=sys.stderr)
    print(summary["verdict"], file=sys.stderr)
    return 0 if result.locked else 2


if __name__ == "__main__":
    raise SystemExit(main())
