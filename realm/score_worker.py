"""Picklable fitness scorer for multi-process evolve (Windows spawn-safe)."""

from __future__ import annotations

from typing import Any

import numpy as np

from realm.lock_key import Keymaker, build_key, build_lock, residual
from realm.projection import build_moduli_landscape, test_valley_occupancy

# Set once per worker process via initializer
_CFG: dict[str, Any] = {}


def init_worker(cfg: dict[str, Any], blas_threads: int = 1) -> None:
    global _CFG
    from realm.hw import apply_blas_thread_env

    apply_blas_thread_env(blas_threads)
    _CFG = dict(cfg)


def vec_to_knobs(vec: np.ndarray | list[float], g_last: float) -> dict[str, float]:
    v = np.asarray(vec, dtype=float).ravel()
    return {
        "Lambda": float(v[0]) * g_last,
        "omega_scale": float(v[1]),
        "weight_power": float(v[2]),
        "tier_split": float(v[3]),
        "low_boost": float(v[4]),
        "w1_mult": float(v[5]) if v.size > 5 else 1.0,
        "w2_mult": float(v[6]) if v.size > 6 else 1.0,
        "w3_mult": float(v[7]) if v.size > 7 else 1.0,
    }


def score_vec(
    vec: np.ndarray | list[float],
    *,
    N: int,
    n_zeros: int,
    n_sectors: int,
    g_last: float,
    n_target: int,
    alpha: float = 0.45,
    beta: float = 0.25,
    gamma: float = 0.15,
) -> dict[str, Any]:
    """Full fitness evaluation — returns JSON-safe entry (+ F). No live objects."""
    kn = vec_to_knobs(vec, g_last)
    try:
        der = Keymaker(N=N, n_zeros=n_zeros, n_sectors=n_sectors).forge(**kn)
    except Exception as exc:  # noqa: BLE001
        return {
            "F": 10.0,
            "R": 10.0,
            "error": str(exc),
            "knobs": kn,
            "occupancy": 0.0,
            "n_keys": 0,
            "n_valleys": 0,
            "mean_dist": 1.0,
            "breakdown": {},
            "verdict": f"forge fail: {exc}",
            "thetas": [],
            "spectral_gaps": [],
        }

    lock = build_lock(der)
    key = build_key(der)
    res = residual(lock, key, action=der.action)
    landscape = build_moduli_landscape(
        field=der.field,
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
    occ = float(test.occupancy_fraction)
    F = (
        float(res.total)
        + alpha * (1.0 - occ)
        + beta * max(0, n_target - n_keys) / max(n_target, 1)
        + gamma * max(0.0, 1.0 - n_valleys / max(n_target, 1))
    )
    return {
        "F": F,
        "R": float(res.total),
        "knobs": kn,
        "occupancy": occ,
        "n_keys": n_keys,
        "n_valleys": n_valleys,
        "mean_dist": float(test.mean_distance_to_valley),
        "breakdown": res.to_dict(),
        "verdict": test.verdict,
        "thetas": key.thetas.tolist(),
        "spectral_gaps": key.spectral_gaps.tolist(),
    }


def score_vec_worker(vec: np.ndarray | list[float]) -> dict[str, Any]:
    """Worker entry: uses process-local _CFG from init_worker."""
    return score_vec(
        vec,
        N=int(_CFG["N"]),
        n_zeros=int(_CFG["n_zeros"]),
        n_sectors=int(_CFG["n_sectors"]),
        g_last=float(_CFG["g_last"]),
        n_target=int(_CFG["n_target"]),
        alpha=float(_CFG.get("alpha", 0.45)),
        beta=float(_CFG.get("beta", 0.25)),
        gamma=float(_CFG.get("gamma", 0.15)),
    )


def de_objective(vec: np.ndarray) -> float:
    """SciPy DE objective (picklable; needs init_worker first)."""
    return float(score_vec_worker(vec)["F"])
