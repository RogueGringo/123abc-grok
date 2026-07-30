#!/usr/bin/env python3
"""Multi-generation evolution: seal lock + fill the mold.

Fitness (lower is better):
  F = R + α (1 - occupancy) + β max(0, n_target_sectors - n_keys)/n_target
        + γ (1 - n_valleys/n_target)_+

Warm-starts each generation from the previous best knobs.
Stops on EVOLVED_SEAL: locked ∧ occupancy ≥ occ_target ∧ n_keys ≥ n_min_keys.

Parallelism: ProcessPoolExecutor / scipy DE workers on ARM multi-core.
BLAS single-threaded inside workers (see realm.hw).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import differential_evolution, minimize

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.hw import apply_blas_thread_env, recommend_workers
from realm.lock_key import Keymaker
from realm.score_worker import (
    de_objective,
    init_worker,
    score_vec,
    score_vec_worker,
    vec_to_knobs,
)

logger = logging.getLogger("evolve")


def _knobs_to_vec(knobs: dict, g_last: float) -> np.ndarray:
    return np.array(
        [
            knobs["Lambda"] / g_last,
            knobs.get("omega_scale", 1.0),
            knobs.get("weight_power", 1.0),
            knobs.get("tier_split", 0.45),
            knobs.get("low_boost", 1.0),
            knobs.get("w1_mult", 1.0),
            knobs.get("w2_mult", 1.0),
            knobs.get("w3_mult", 1.0),
        ],
        dtype=float,
    )


def _clip_bounds(x: np.ndarray, bounds: list) -> np.ndarray:
    out = np.array(x, dtype=float, copy=True)
    for i, (lo, hi) in enumerate(bounds):
        out[i] = float(np.clip(out[i], lo, hi))
    return out


def _de_init_population(
    bounds: list,
    warm: np.ndarray | None,
    n_pop: int,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)
    pop = lo + rng.random((n_pop, len(bounds))) * (hi - lo)
    if warm is not None:
        w = _clip_bounds(warm, bounds)
        pop[0] = w
        n_cloud = min(n_pop - 1, max(4, n_pop // 3))
        for i in range(n_cloud):
            scale = 0.04 * (1 + i % 4)
            pop[1 + i] = _clip_bounds(
                w + rng.normal(0, scale, size=len(bounds)), bounds
            )
    return pop


def _hydrate_best(entry: dict, cfg: dict) -> dict:
    """Re-forge live objects for the elite (plot + residual objects)."""
    from realm.lock_key import build_key, build_lock, residual
    from realm.projection import build_moduli_landscape, test_valley_occupancy

    kn = entry["knobs"] if "knobs" in entry else {
        k: entry[k]
        for k in (
            "Lambda",
            "omega_scale",
            "weight_power",
            "tier_split",
            "low_boost",
            "w1_mult",
            "w2_mult",
            "w3_mult",
        )
        if k in entry
    }
    # normalize entry shape
    if "knobs" not in entry:
        kn = {
            "Lambda": entry["Lambda"],
            "omega_scale": entry["omega_scale"],
            "weight_power": entry["weight_power"],
            "tier_split": entry["tier_split"],
            "low_boost": entry["low_boost"],
            "w1_mult": entry.get("w1_mult", 1.0),
            "w2_mult": entry.get("w2_mult", 1.0),
            "w3_mult": entry.get("w3_mult", 1.0),
        }
    else:
        kn = entry["knobs"]

    der = Keymaker(
        N=cfg["N"], n_zeros=cfg["n_zeros"], n_sectors=cfg["n_sectors"]
    ).forge(**kn)
    lock = build_lock(der)
    key = build_key(der)
    res = residual(lock, key, action=der.action)
    landscape = build_moduli_landscape(
        field=der.field, action=der.action, critical=der.critical
    )
    test = test_valley_occupancy(
        key.thetas,
        landscape=landscape,
        labels=[f"k{i+1}" for i in range(len(key.thetas))],
        spectral_gaps=key.spectral_gaps,
    )
    full_entry = {
        **kn,
        "R": res.total,
        "F": entry.get("F", res.total),
        "occupancy": test.occupancy_fraction,
        "n_keys": len(key.thetas),
        "n_valleys": len(landscape.valleys),
        "mean_dist": test.mean_distance_to_valley,
        "breakdown": res.to_dict(),
        "verdict": test.verdict,
    }
    return {
        "F": full_entry["F"],
        "knobs": kn,
        "der": der,
        "res": res,
        "lock": lock,
        "key": key,
        "test": test,
        "landscape": landscape,
        "entry": full_entry,
    }


def _consider(best: list, scored: dict) -> None:
    """Update elite from a score_vec result dict."""
    if scored.get("F", 10.0) >= 9.0:
        return
    entry = {
        **scored["knobs"],
        "R": scored["R"],
        "F": scored["F"],
        "occupancy": scored["occupancy"],
        "n_keys": scored["n_keys"],
        "n_valleys": scored["n_valleys"],
        "mean_dist": scored["mean_dist"],
        "breakdown": scored["breakdown"],
        "verdict": scored["verdict"],
    }
    if not best or scored["F"] < best[0]["F"] - 1e-15:
        best.clear()
        best.append(
            {
                "F": scored["F"],
                "knobs": scored["knobs"],
                "entry": entry,
                "scored": scored,
            }
        )
        logger.info(
            "F=%.4f R=%.4f occ=%.0f%% keys=%d valleys=%d | Λ=%.1f ωs=%.2f w=(%.2f,%.2f,%.2f)",
            scored["F"],
            scored["R"],
            100 * scored["occupancy"],
            scored["n_keys"],
            scored["n_valleys"],
            scored["knobs"]["Lambda"],
            scored["knobs"]["omega_scale"],
            scored["knobs"].get("w1_mult", 1.0),
            scored["knobs"].get("w2_mult", 1.0),
            scored["knobs"].get("w3_mult", 1.0),
        )


def _map_scores(
    vecs: list[np.ndarray],
    cfg: dict,
    workers: int,
    blas_threads: int,
) -> list[dict]:
    """Score many vectors; parallel if workers > 1."""
    if not vecs:
        return []
    if workers <= 1:
        return [
            score_vec(
                v,
                N=cfg["N"],
                n_zeros=cfg["n_zeros"],
                n_sectors=cfg["n_sectors"],
                g_last=cfg["g_last"],
                n_target=cfg["n_target"],
            )
            for v in vecs
        ]

    results: list[dict | None] = [None] * len(vecs)
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=init_worker,
        initargs=(cfg, blas_threads),
    ) as ex:
        futs = {ex.submit(score_vec_worker, np.asarray(v, float)): i for i, v in enumerate(vecs)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("worker fail: %s", exc)
                results[i] = {"F": 10.0, "R": 10.0, "knobs": {}, "occupancy": 0.0,
                              "n_keys": 0, "n_valleys": 0, "mean_dist": 1.0,
                              "breakdown": {}, "verdict": str(exc),
                              "thetas": [], "spectral_gaps": []}
    return [r for r in results if r is not None]


def run_generation(
    gen: int,
    cfg: dict,
    bounds: list,
    warm: np.ndarray | None,
    maxiter_de: int,
    workers: int,
    blas_threads: int,
) -> dict:
    history: list = []
    best: list = []
    g_last = float(cfg["g_last"])
    n_dim = len(bounds)
    n_target = int(cfg["n_target"])

    def obj_serial(v: np.ndarray) -> float:
        scored = score_vec(
            v,
            N=cfg["N"],
            n_zeros=cfg["n_zeros"],
            n_sectors=cfg["n_sectors"],
            g_last=g_last,
            n_target=n_target,
        )
        history.append({**scored["knobs"], "R": scored["R"], "F": scored["F"],
                        "occupancy": scored["occupancy"], "n_keys": scored["n_keys"],
                        "n_valleys": scored["n_valleys"]})
        _consider(best, scored)
        return float(scored["F"])

    de_popsize = max(4, min(8, 40 // max(n_dim, 1)))
    n_init = de_popsize * n_dim
    init = _de_init_population(bounds, warm, n_init, seed=7 + gen * 17)

    # --- Phase 1: parallel DE (deferred updating required for workers>1) ---
    logger.info(
        "Gen %d DE: popsize=%d n_init=%d workers=%d maxiter=%d",
        gen,
        de_popsize,
        n_init,
        workers,
        maxiter_de,
    )
    de_kwargs = dict(
        bounds=bounds,
        maxiter=maxiter_de,
        popsize=de_popsize,
        mutation=(0.35, 1.25),
        recombination=0.80,
        seed=7 + gen * 17,
        polish=False,
        init=init,
    )
    if workers > 1:
        # SciPy's int workers=N spins a bare Pool (no initializer).
        # Use our initialized Pool.map so de_objective sees cfg.
        with Pool(
            processes=workers,
            initializer=init_worker,
            initargs=(cfg, blas_threads),
        ) as pool:
            de = differential_evolution(
                de_objective,
                workers=pool.map,
                updating="deferred",
                **de_kwargs,
            )
        scored = score_vec(
            de.x,
            N=cfg["N"],
            n_zeros=cfg["n_zeros"],
            n_sectors=cfg["n_sectors"],
            g_last=g_last,
            n_target=n_target,
        )
        history.append(
            {
                **scored["knobs"],
                "R": scored["R"],
                "F": scored["F"],
                "occupancy": scored["occupancy"],
            }
        )
        _consider(best, scored)
    else:
        de = differential_evolution(obj_serial, workers=1, **de_kwargs)

    x_best = np.asarray(de.x, dtype=float)

    # --- Phase 2: L-BFGS polish (serial — needs sequential state) ---
    if warm is not None:
        minimize(obj_serial, warm, method="L-BFGS-B", bounds=bounds, options={"maxiter": 25})
    minimize(obj_serial, x_best, method="L-BFGS-B", bounds=bounds, options={"maxiter": 30})

    # --- Phase 3: parallel jitter cloud, then polish top seeds ---
    rng = np.random.default_rng(100 + gen)
    center = (
        _knobs_to_vec(best[0]["knobs"], g_last)
        if best
        else (warm if warm is not None else x_best)
    )
    cloud: list[np.ndarray] = []
    for sigma in (0.02, 0.05, 0.10, 0.18):
        for _ in range(8):
            cloud.append(_clip_bounds(center + rng.normal(0, sigma, size=n_dim), bounds))
    # IR-axis micro steps
    for axis in range(n_dim):
        deltas = (-0.06, -0.02, 0.02, 0.06) if axis < 5 else (-0.12, -0.05, 0.05, 0.12)
        for delta in deltas:
            step = center.copy()
            step[axis] += delta
            cloud.append(_clip_bounds(step, bounds))

    logger.info("Gen %d parallel cloud: %d candidates × %d workers", gen, len(cloud), workers)
    cloud_scores = _map_scores(cloud, cfg, workers, blas_threads)
    for sc in cloud_scores:
        history.append({**sc.get("knobs", {}), "R": sc.get("R"), "F": sc.get("F")})
        _consider(best, sc)

    # Local polish on top-K cloud points
    ranked = sorted(cloud_scores, key=lambda s: s.get("F", 99.0))[:6]
    for sc in ranked:
        if not sc.get("knobs"):
            continue
        seed = _knobs_to_vec(sc["knobs"], g_last)
        minimize(obj_serial, seed, method="L-BFGS-B", bounds=bounds, options={"maxiter": 18})

    if not best:
        return {"history": history, "best": None}

    # Hydrate live objects for plot
    hydrated = _hydrate_best(best[0]["entry"], cfg)
    hydrated["F"] = best[0]["F"]
    hydrated["entry"]["F"] = best[0]["F"]
    return {"history": history, "best": hydrated}


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
    ax.set_title(
        f"Gen {len(gen_log)} mold · {len(land.valleys)} valleys · {len(b['key'].thetas)} keys"
    )
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
        f"w1={kn.get('w1_mult', 1):.3f} w2={kn.get('w2_mult', 1):.3f} w3={kn.get('w3_mult', 1):.3f}",
        "",
        e["verdict"][:100],
        "",
        "multi-core ARM evolve",
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
    fig.suptitle(
        "GO & EVOLVE  ·  multi-core Keymaker × mold",
        color="#00ff88",
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="#020805")
    plt.close(fig)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("-N", type=int, default=13)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--generations", type=int, default=4)
    p.add_argument("--de-iter", type=int, default=6)
    p.add_argument("--r-target", type=float, default=0.08)
    p.add_argument("--occ-target", type=float, default=0.80)
    p.add_argument(
        "--workers",
        type=int,
        default=-1,
        help="Process workers (-1=auto from CPU/RAM, 0/1=serial)",
    )
    p.add_argument("--json", type=Path, default=Path("evolve_result.json"))
    p.add_argument("--plot", type=Path, default=Path("evolve.png"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    profile = recommend_workers(None if args.workers < 0 else args.workers)
    apply_blas_thread_env(profile.blas_threads)
    workers = profile.workers
    logger.info("Compute: %s", profile.notes)
    logger.info(
        "DirectML/GPU path not used for forge (NumPy/SciPy); CPU process pool only"
    )

    km = Keymaker(N=args.N, n_zeros=args.k, n_sectors=args.sectors)
    probe = km.forge()
    g_last = float(probe.field.gammas[-1])
    cfg = {
        "N": args.N,
        "n_zeros": args.k,
        "n_sectors": args.sectors,
        "g_last": g_last,
        "n_target": args.sectors,
    }
    bounds = [
        (0.35, 4.5),
        (0.35, 2.9),
        (0.35, 2.9),
        (0.12, 0.80),
        (0.5, 3.8),
        (0.80, 1.20),
        (0.80, 1.20),
        (0.80, 1.20),
    ]

    warm = None
    prev = Path("evolve_result.json")
    if prev.is_file():
        try:
            old = json.loads(prev.read_text(encoding="utf-8"))
            kn = old.get("meet_knobs") or old.get("best_knobs") or {}
            if kn.get("Lambda"):
                warm = _knobs_to_vec(kn, g_last)
                logger.info(
                    "Warm start R=%.4f knobs Λ=%.2f ωs=%.3f w=(%.2f,%.2f,%.2f)",
                    float(old.get("R", -1)),
                    kn["Lambda"],
                    kn.get("omega_scale", 1.0),
                    kn.get("w1_mult", 1.0),
                    kn.get("w2_mult", 1.0),
                    kn.get("w3_mult", 1.0),
                )
        except Exception:
            pass

    gen_log = []
    global_best: dict | None = None
    for g in range(1, args.generations + 1):
        logger.info("======== GENERATION %d / %d ========", g, args.generations)
        out = run_generation(
            g,
            cfg,
            bounds,
            warm,
            args.de_iter,
            workers,
            profile.blas_threads,
        )
        b = out["best"]
        if b is None:
            logger.error("Generation %d produced no best", g)
            continue
        e = b["entry"]
        sealed = (
            e["R"] <= args.r_target
            and e["occupancy"] >= args.occ_target
            and e["n_keys"] >= max(3, args.sectors // 2)
        )
        status = "EVOLVED_SEAL" if sealed else "EVOLVING"
        out["status"] = status
        gen_log.append(out)

        if global_best is None:
            global_best = b
        else:
            gb_e = global_best["entry"]
            better = (b["F"] < global_best["F"] - 1e-12) or (
                abs(b["F"] - global_best["F"]) < 1e-12 and e["R"] < gb_e["R"]
            )
            if better:
                global_best = b

        warm = _knobs_to_vec(global_best["knobs"], g_last)
        logger.info(
            "Gen %d %s F=%.4f R=%.4f occ=%.0f%% keys=%d valleys=%d | elite F=%.4f R=%.4f",
            g,
            status,
            b["F"],
            e["R"],
            100 * e["occupancy"],
            e["n_keys"],
            e["n_valleys"],
            global_best["F"],
            global_best["entry"]["R"],
        )
        elite_e = global_best["entry"]
        elite_sealed = (
            elite_e["R"] <= args.r_target
            and elite_e["occupancy"] >= args.occ_target
            and elite_e["n_keys"] >= max(3, args.sectors // 2)
        )
        if elite_sealed and g >= 2 and sealed and g > 2:
            logger.info("Early stop: elite sealed after polish gens")
            break

    if not gen_log or global_best is None:
        logger.error("No generations completed")
        return 2

    final = global_best
    elite_e = final["entry"]
    elite_sealed = (
        elite_e["R"] <= args.r_target
        and elite_e["occupancy"] >= args.occ_target
        and elite_e["n_keys"] >= max(3, args.sectors // 2)
    )
    final_status = "EVOLVED_SEAL" if elite_sealed else "EVOLVING"
    gen_log[-1]["status"] = final_status
    gen_log[-1]["best"] = final

    payload = {
        "generation_time": datetime.now(timezone.utc).isoformat(),
        "n_generations": len(gen_log),
        "status": final_status,
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
        "search": "parallel_8D_IR_micro_DE_LBFGS",
        "config": {"N": args.N, "n_zeros": args.k, "n_sectors": args.sectors},
        "compute": {
            "workers": workers,
            "cpu_count": profile.cpu_count,
            "ram_avail_gb": profile.ram_avail_gb,
            "notes": profile.notes,
        },
    }
    print(
        json.dumps(
            {
                k: payload[k]
                for k in (
                    "status",
                    "R",
                    "occupancy",
                    "n_keys",
                    "n_valleys",
                    "F",
                    "best_knobs",
                    "compute",
                    "verdict",
                )
            },
            indent=2,
        )
    )

    args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    plot_evolve(gen_log, args.plot)
    Path("lock_meet.json").write_text(
        json.dumps(
            {
                "locked": elite_e["R"] <= args.r_target,
                "R": elite_e["R"],
                "knobs": final["knobs"],
                "breakdown": elite_e["breakdown"],
                "thetas": final["key"].thetas.tolist(),
                "search_method": "parallel_8D_IR_micro_DE_LBFGS",
                "occupancy": elite_e["occupancy"],
                "n_keys": elite_e["n_keys"],
                "n_valleys": elite_e["n_valleys"],
                "compute": payload["compute"],
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
