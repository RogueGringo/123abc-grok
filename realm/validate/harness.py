"""Score forge + residual + mold for a seed kind (validation ladder)."""

from __future__ import annotations

from typing import Any

import numpy as np

from realm.lock_key import Keymaker, build_key, build_lock, residual
from realm.projection import build_moduli_landscape, test_valley_occupancy
from realm.validate.seeds import make_seed


def score_configuration(
    *,
    kind: str,
    knobs: dict[str, Any],
    N: int = 13,
    n_zeros: int = 14,
    n_sectors: int = 6,
    rng_seed: int = 0,
    alpha: float = 0.45,
    beta: float = 0.25,
    gamma: float = 0.15,
) -> dict[str, Any]:
    """JSON-safe fitness for null battery / sec scale. Never scores λ=γ."""
    rng = np.random.default_rng(int(rng_seed))
    gammas = make_seed(kind, n_zeros, rng)
    kn = {
        "Lambda": knobs.get("Lambda"),
        "omega_scale": float(knobs.get("omega_scale", 1.0)),
        "weight_power": float(knobs.get("weight_power", 1.0)),
        "tier_split": float(knobs.get("tier_split", 0.45)),
        "low_boost": float(knobs.get("low_boost", 1.0)),
        "w1_mult": float(knobs.get("w1_mult", 1.0)),
        "w2_mult": float(knobs.get("w2_mult", 1.0)),
        "w3_mult": float(knobs.get("w3_mult", 1.0)),
        "gammas": gammas,
    }
    try:
        der = Keymaker(N=N, n_zeros=n_zeros, n_sectors=n_sectors).forge(**kn)
    except Exception as exc:  # noqa: BLE001
        return {
            "kind": kind,
            "rng_seed": rng_seed,
            "F": 10.0,
            "R": 10.0,
            "occupancy": 0.0,
            "n_keys": 0,
            "n_valleys": 0,
            "mean_dist": 1.0,
            "breakdown": {},
            "diagnostics": {},
            "verdict": f"forge fail: {exc}",
            "error": str(exc),
            "thetas": [],
            "spectral_gaps": [],
        }

    lock = build_lock(der)
    key = build_key(der)
    res = residual(lock, key, action=der.action)
    land = build_moduli_landscape(
        field=der.field, action=der.action, critical=der.critical
    )
    test = test_valley_occupancy(
        key.thetas,
        landscape=land,
        labels=[f"k{i+1}" for i in range(len(key.thetas))],
        spectral_gaps=key.spectral_gaps,
    )
    n_keys = len(key.thetas)
    n_valleys = len(land.valleys)
    occ = float(test.occupancy_fraction)
    F = (
        float(res.total)
        + alpha * (1.0 - occ)
        + beta * max(0, n_sectors - n_keys) / max(n_sectors, 1)
        + gamma * max(0.0, 1.0 - n_valleys / max(n_sectors, 1))
    )
    return {
        "kind": kind,
        "rng_seed": rng_seed,
        "F": F,
        "R": float(res.total),
        "occupancy": occ,
        "n_keys": n_keys,
        "n_valleys": n_valleys,
        "mean_dist": float(test.mean_distance_to_valley),
        "breakdown": res.to_dict(),
        "diagnostics": res.diagnostics or {},
        "verdict": test.verdict,
        "thetas": key.thetas.tolist(),
        "spectral_gaps": key.spectral_gaps.tolist(),
        "ontology": "projection_mold_plus_crit_seal_not_lambda_eq_gamma",
    }


def _worker_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Picklable process-pool entry."""
    return score_configuration(**payload)
