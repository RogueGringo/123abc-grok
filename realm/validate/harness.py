"""Score forge + residual + mold for a seed kind (validation ladder)."""

from __future__ import annotations

from typing import Any

import numpy as np

from realm.lock_key import Keymaker, build_key, build_lock, residual
from realm.projection import build_moduli_landscape, test_valley_occupancy
from realm.validate.seeds import make_seed

# 8 free knobs in Keymaker / evolve vector — report next to n_sectors
N_KNOBS = 8


def score_configuration(
    *,
    kind: str | None = None,
    knobs: dict[str, Any],
    N: int = 13,
    n_zeros: int = 14,
    n_sectors: int = 6,
    rng_seed: int = 0,
    alpha: float = 0.45,
    beta: float = 0.25,
    gamma: float = 0.15,
    gammas: np.ndarray | None = None,
    fitness: str = "informative",
) -> dict[str, Any]:
    """JSON-safe fitness for null battery / sec scale / transfer.

    Never scores λ=γ. Default residual fitness is **informative** (density-return
    only). Pass fitness=\"legacy\" to reproduce the pre-falsification seating score.
    """
    rng = np.random.default_rng(int(rng_seed))
    if gammas is not None:
        g = np.asarray(gammas, dtype=float).ravel()
        g = np.sort(g[g > 0])
        if g.size < 2:
            raise ValueError("gammas need at least 2 positive ordinates")
        seed_kind = kind or "injected"
    else:
        if kind is None:
            kind = "zeta"
        g = make_seed(kind, n_zeros, rng)
        seed_kind = kind

    kn = {
        "Lambda": knobs.get("Lambda"),
        "omega_scale": float(knobs.get("omega_scale", 1.0)),
        "weight_power": float(knobs.get("weight_power", 1.0)),
        "tier_split": float(knobs.get("tier_split", 0.45)),
        "low_boost": float(knobs.get("low_boost", 1.0)),
        "w1_mult": float(knobs.get("w1_mult", 1.0)),
        "w2_mult": float(knobs.get("w2_mult", 1.0)),
        "w3_mult": float(knobs.get("w3_mult", 1.0)),
        "gammas": g,
    }
    try:
        der = Keymaker(N=N, n_zeros=max(n_zeros, int(g.size)), n_sectors=n_sectors).forge(
            **kn
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "kind": seed_kind,
            "rng_seed": rng_seed,
            "F": 10.0,
            "R": 10.0,
            "R_legacy": 10.0,
            "R_informative": 10.0,
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
            "fitness_mode": fitness,
            "dof": {"n_knobs": N_KNOBS, "n_sectors": n_sectors, "n_zeros": int(g.size)},
        }

    lock = build_lock(der)
    key = build_key(der)
    res = residual(lock, key, action=der.action, fitness=fitness)
    # always compute the other mode for paired reporting
    res_leg = residual(lock, key, action=der.action, fitness="legacy")
    res_inf = residual(lock, key, action=der.action, fitness="informative")
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
    diag = dict(res.diagnostics or {})
    return {
        "kind": seed_kind,
        "rng_seed": rng_seed,
        "F": F,
        "R": float(res.total),
        "R_legacy": float(res_leg.total),
        "R_informative": float(res_inf.total),
        "occupancy": occ,
        "n_keys": n_keys,
        "n_valleys": n_valleys,
        "mean_dist": float(test.mean_distance_to_valley),
        "breakdown": res.to_dict(),
        "diagnostics": diag,
        "verdict": test.verdict,
        "thetas": key.thetas.tolist(),
        "spectral_gaps": key.spectral_gaps.tolist(),
        "fitness_mode": fitness,
        "dof": {
            "n_knobs": N_KNOBS,
            "n_sectors": n_sectors,
            "n_zeros": int(g.size),
            "note": "8 knobs vs 6 sectors is under-constrained for corr terms",
        },
        "ontology": "projection_mold_plus_crit_seal_not_lambda_eq_gamma",
        "instrument_note": (
            "informative R = density_return only; legacy R is retracted as "
            "ζ-preference evidence (Crit seating degeneracy)"
        ),
    }


def _worker_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Picklable process-pool entry."""
    return score_configuration(**payload)
