#!/usr/bin/env python3
"""Multi-generation evolution: seal lock + fill the mold.

Fitness (lower is better):
  F = R + α (1 - occupancy) + β max(0, n_target_sectors - n_keys)/n_target
        + γ (1 - n_valleys/n_target)_+

Warm-starts each generation from the previous best knobs.
Stops on EVOLVED_SEAL: locked ∧ occupancy ≥ occ_target ∧ n_keys ≥ n_min_keys.
"""

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
from scipy.optimize import differential_evolution, minimize

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.derive import Deriver
from realm.lock_key import (
    Keymaker,
    build_key,
    build_lock,
    residual,
)
from realm.projection import build_moduli_landscape, test_valley_occupancy

logger = logging.getLogger("evolve")


def evaluate_knobs(
    km: Keymaker,
    g_last: float,
    vec: np.ndarray,
    history: list,
    best: list,
    n_target: int,
    alpha: float = 0.45,
    beta: float = 0.25,
    gamma: float = 0.15,
) -> float:
    """Joint fitness: lock residual + mold vacancy + sector starvation."""
    kn = {
        "Lambda": float(vec[0]) * g_last,
        "omega_scale": float(vec[1]),
        "weight_power": float(vec[2]),
        "tier_split": float(vec[3]),
        "low_boost": float(vec[4]),
    }
    try:
        der = km.forge(**kn)
    except Exception as exc:  # noqa: BLE001
        logger.warning("forge fail: %s", exc)
        return 10.0

    lock = build_lock(der)
    key = build_key(der)
    res = residual(lock, key, action=der.action)

    landscape = build_moduli_landscape(
        field=der.field,
        Lambda=kn["Lambda"],
        omega_scale=kn["omega_scale"],
        weight_power=kn["weight_power"],
        tier_split=kn["tier_split"],
        low_boost=kn["low_boost"],
        action=der.action,
        critical=der.critical,
    )
    test = test_valley_occupancy(
        key.thetas,
        landscape=landscape,
        labels=[f"k{i+1}" for i in range(len(key.thetas))],
        spectral_gaps=key.spectral_gaps,
    )
    n_keys = len(key.thetas)
    n_valleys = len(landscape.valleys)
    occ = test.occupancy_fraction

    F = (
        res.total
        + alpha * (1.0 - occ)
        + beta * max(0, n_target - n_keys) / max(n_target, 1)
        + gamma * max(0.0, 1.0 - n_valleys / max(n_target, 1))
    )

    entry = {
        **kn,
        "R": res.total,
        "F": F,
        "occupancy": occ,
        "n_keys": n_keys,
        "n_valleys": n_valleys,
        "mean_dist": test.mean_distance_to_valley,
        "breakdown": res.to_dict(),
        "verdict": test.verdict,
    }
    history.append(entry)

    if not best or F < best[0]["F"]:
        best.clear()
        best.append(
            {
                "F": F,
                "knobs": kn,
                "der": der,
                "res": res,
                "lock": lock,
                "key": key,
                "test": test,
                "landscape": landscape,
                "entry": entry,
            }
        )

    logger.info(
        "F=%.4f R=%.4f occ=%.0f%% keys=%d valleys=%d | Λ=%.1f ωs=%.2f",
        F,
        res.total,
        100 * occ,
        n_keys,
        n_valleys,
        kn["Lambda"],
        kn["omega_scale"],
    )
    return F


def run_generation(
    gen: int,
    km: Keymaker,
    g_last: float,
    bounds: list,
    warm: np.ndarray | None,
    n_target: int,
    maxiter_de: int,
) -> dict:
    history: list = []
    best: list = []

    def obj(v):
        return evaluate_knobs(km, g_last, v, history, best, n_target)

    # DE global
    de = differential_evolution(
        obj,
        bounds=bounds,
        maxiter=maxiter_de,
        popsize=10,
        mutation=(0.4, 1.3),
        recombination=0.75,
        seed=7 + gen * 17,
        polish=False,
        workers=1,
        init="sobol",
    )
    x_best = np.array(de.x, dtype=float)
    if warm is not None:
        # polish warm start
        minimize(obj, warm, method="L-BFGS-B", bounds=bounds, options={"maxiter": 15})
    minimize(obj, x_best, method="L-BFGS-B", bounds=bounds, options={"maxiter": 20})

    # local jitter around best
    rng = np.random.default_rng(100 + gen)
    if best:
        center = np.array(
            [
                best[0]["knobs"]["Lambda"] / g_last,
                best[0]["knobs"]["omega_scale"],
                best[0]["knobs"]["weight_power"],
                best[0]["knobs"]["tier_split"],
                best[0]["knobs"]["low_boost"],
            ]
        )
        for _ in range(6):
            jitter = center + rng.normal(0, 0.12, size=5)
            for i, (lo, hi) in enumerate(bounds):
                jitter[i] = np.clip(jitter[i], lo, hi)
            minimize(obj, jitter, method="L-BFGS-B", bounds=bounds, options={"maxiter": 10})

    return {"history": history, "best": best[0] if best else None}


def plot_evolve(gen_log: list, path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    Fs = [g["best"]["F"] for g in gen_log if g.get("best")]
    Rs = [g["best"]["entry"]["R"] for g in gen_log if g.get("best")]
    occs = [g["best"]["entry"]["occupancy"] for g in gen_log if g.get("best")]

    ax = axes[0, 0]
    ax.plot(Fs, "c-o", label="F")
    ax.plot(Rs, "m--s", label="R")
    ax.set_xlabel("generation")
    ax.legend()
    ax.set_title("Fitness evolution")
    ax.grid(True, alpha=0.3)

    ax = axes[0, 1]
    ax.plot([100 * o for o in occs], "g-o")
    ax.axhline(80, color="r", ls="--", label="80% target")
    ax.set_ylabel("occupancy %")
    ax.set_title("Mold occupancy by generation")
    ax.legend()
    ax.grid(True, alpha=0.3)

    b = gen_log[-1]["best"]
    ax = axes[1, 0]
    land = b["landscape"]
    ax.plot(land.sample_theta, land.sample_V, "b-", lw=1.5)
    for v in land.valleys:
        ax.axvline(v["theta"], color="g", alpha=0.4, ls="--")
    for th in b["key"].thetas:
        ax.plot(th, float(land.V(th)), "mo", ms=9, markeredgecolor="k")
    ax.set_title(f"Gen {len(gen_log)} mold · {len(land.valleys)} valleys · {len(b['key'].thetas)} keys")
    ax.grid(True, alpha=0.3)

    ax = axes[1, 1]
    ax.axis("off")
    e = b["entry"]
    kn = b["knobs"]
    status = gen_log[-1].get("status", "?")
    lines = [
        f"GENERATION {len(gen_log)}  {status}",
        f"F={b['F']:.4f}  R={e['R']:.4f}",
        f"occupancy={e['occupancy']:.0%}  keys={e['n_keys']} valleys={e['n_valleys']}",
        f"mean_dist={e['mean_dist']:.4f}",
        "",
        f"Λ={kn['Lambda']:.2f}  ωs={kn['omega_scale']:.3f}",
        f"wp={kn['weight_power']:.3f}  tier={kn['tier_split']:.2f}",
        f"boost={kn['low_boost']:.2f}",
        "",
        e["verdict"][:100],
        "",
        "ontology: projection mold + Crit seal",
        "not λ = actual γ",
    ]
    ax.text(
        0.05,
        0.95,
        "\n".join(lines),
        transform=ax.transAxes,
        va="top",
        family="monospace",
        fontsize=9,
        color="#e0ffe8",
        bbox=dict(boxstyle="round", facecolor="#05140a", edgecolor="#00ff88"),
    )
    fig.suptitle("GO & EVOLVE  ·  multi-generation Keymaker × mold", color="#00ff88", fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="#020805")
    plt.close(fig)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("-N", type=int, default=11)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--generations", type=int, default=4)
    p.add_argument("--de-iter", type=int, default=6)
    p.add_argument("--r-target", type=float, default=0.08)
    p.add_argument("--occ-target", type=float, default=0.80)
    p.add_argument("--json", type=Path, default=Path("evolve_result.json"))
    p.add_argument("--plot", type=Path, default=Path("evolve.png"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    km = Keymaker(N=args.N, n_zeros=args.k, n_sectors=args.sectors)
    probe = km.forge()
    g_last = float(probe.field.gammas[-1])
    bounds = [
        (0.35, 4.5),
        (0.35, 2.9),
        (0.35, 2.9),
        (0.12, 0.80),
        (0.5, 3.8),
    ]

    # warm start from previous evolve if present
    warm = None
    prev = Path("evolve_result.json")
    if prev.is_file():
        try:
            old = json.loads(prev.read_text(encoding="utf-8"))
            kn = old.get("meet_knobs") or old.get("best_knobs") or {}
            if kn.get("Lambda"):
                warm = np.array(
                    [
                        kn["Lambda"] / g_last,
                        kn.get("omega_scale", 1.0),
                        kn.get("weight_power", 1.0),
                        kn.get("tier_split", 0.45),
                        kn.get("low_boost", 1.0),
                    ],
                    dtype=float,
                )
                logger.info("Warm start from previous generation knobs")
        except Exception:
            pass

    gen_log = []
    for g in range(1, args.generations + 1):
        logger.info("======== GENERATION %d / %d ========", g, args.generations)
        out = run_generation(
            g, km, g_last, bounds, warm, args.sectors, args.de_iter
        )
        b = out["best"]
        if b is None:
            logger.error("Generation %d produced no best", g)
            continue
        e = b["entry"]
        sealed = e["R"] <= args.r_target and e["occupancy"] >= args.occ_target and e["n_keys"] >= max(3, args.sectors // 2)
        status = "EVOLVED_SEAL" if sealed else "EVOLVING"
        out["status"] = status
        gen_log.append(out)
        warm = np.array(
            [
                b["knobs"]["Lambda"] / g_last,
                b["knobs"]["omega_scale"],
                b["knobs"]["weight_power"],
                b["knobs"]["tier_split"],
                b["knobs"]["low_boost"],
            ]
        )
        logger.info(
            "Gen %d %s F=%.4f R=%.4f occ=%.0f%% keys=%d valleys=%d",
            g,
            status,
            b["F"],
            e["R"],
            100 * e["occupancy"],
            e["n_keys"],
            e["n_valleys"],
        )
        if sealed:
            logger.info("Early stop: targets met")
            break

    final = gen_log[-1]["best"]
    payload = {
        "generation_time": datetime.now(timezone.utc).isoformat(),
        "n_generations": len(gen_log),
        "status": gen_log[-1]["status"],
        "best_knobs": final["knobs"],
        "meet_knobs": final["knobs"],
        "F": final["F"],
        "R": final["entry"]["R"],
        "occupancy": final["entry"]["occupancy"],
        "n_keys": final["entry"]["n_keys"],
        "n_valleys": final["entry"]["n_valleys"],
        "verdict": final["entry"]["verdict"],
        "breakdown": final["entry"]["breakdown"],
        "thetas": final["key"].thetas.tolist(),
        "spectral_gaps": final["key"].spectral_gaps.tolist(),
        "targets": {"R": args.r_target, "occupancy": args.occ_target},
        "history_tail": [g["best"]["entry"] for g in gen_log if g.get("best")],
        "ontology": "projection_mold_plus_crit_seal",
    }
    print(json.dumps({k: payload[k] for k in ("status", "R", "occupancy", "n_keys", "n_valleys", "F", "best_knobs", "verdict")}, indent=2))

    args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    plot_evolve(gen_log, args.plot)
    # also dump sealed der summary
    Path("lock_meet.json").write_text(
        json.dumps(
            {
                "locked": final["entry"]["R"] <= args.r_target,
                "R": final["entry"]["R"],
                "knobs": final["knobs"],
                "breakdown": final["entry"]["breakdown"],
                "thetas": final["key"].thetas.tolist(),
                "search_method": "multi_gen_DE_LBFGS_fitness",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {args.json}", file=sys.stderr)
    print(f"wrote {args.plot}", file=sys.stderr)
    print(payload["status"], file=sys.stderr)
    return 0 if payload["status"] == "EVOLVED_SEAL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
