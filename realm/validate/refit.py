"""Per-arm knob refitting — the fair fight.

`null_battery.py` scores every null with knobs that were optimized against ζ
(`realm/score_worker.py:53` forges with no `gammas`, so DE saw the real ζ field).
An 8-parameter fit evaluated at its own optimum will beat unfit controls whether
or not ζ carries structure. This module gives every arm its own identical tuning
budget so the comparison means something.

Fairness guarantees, each load-bearing:

* **No warm start.** `evolve.py:517` seeds the optimizer from `evolve_result.json`
  (ζ-fitted). Here every arm starts from the same neutral init distribution.
* **Identical eval count.** `tol=0, atol=0` disables DE's early convergence exit,
  so every arm consumes exactly the same number of objective evaluations. Without
  this, an arm that converges early gets a smaller effective budget.
* **Decoupled randomness.** The spectrum draw and the optimizer path are drawn
  from independently spawned streams, so an arm's spectrum cannot correlate with
  its search trajectory.
* **Convergence evidence.** Each run reports where in the budget its best was
  found and how much the final polish moved it, so a high F can be read as "no
  good optimum exists" rather than "the search ran out of road".
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from scipy.optimize import differential_evolution, minimize

from realm.lock_key import Keymaker, build_key, build_lock, residual
from realm.projection import build_moduli_landscape, test_valley_occupancy
from realm.validate.adversarial import DETERMINISTIC, arm_seed_id, make_adversarial_seed

# Identical to evolve.py:506 so refits are comparable to the original fit.
# All eight coordinates are dimensionless; v[0] is the Lambda/g_last ratio.
BOUNDS: tuple[tuple[float, float], ...] = (
    (0.35, 4.5),
    (0.35, 2.9),
    (0.35, 2.9),
    (0.12, 0.80),
    (0.5, 3.8),
    (0.80, 1.20),
    (0.80, 1.20),
    (0.80, 1.20),
)
N_DIM = len(BOUNDS)

FAIL_F = 10.0


def vec_to_knobs(vec: np.ndarray, g_last: float) -> dict[str, float]:
    """Dimensionless vector -> knob dict. Mirrors score_worker.vec_to_knobs."""
    v = np.asarray(vec, dtype=float).ravel()
    return {
        "Lambda": float(v[0]) * float(g_last),
        "omega_scale": float(v[1]),
        "weight_power": float(v[2]),
        "tier_split": float(v[3]),
        "low_boost": float(v[4]),
        "w1_mult": float(v[5]),
        "w2_mult": float(v[6]),
        "w3_mult": float(v[7]),
    }


def knobs_to_vec(knobs: dict[str, Any], g_last: float) -> np.ndarray:
    return np.array(
        [
            float(knobs["Lambda"]) / float(g_last),
            float(knobs.get("omega_scale", 1.0)),
            float(knobs.get("weight_power", 1.0)),
            float(knobs.get("tier_split", 0.45)),
            float(knobs.get("low_boost", 1.0)),
            float(knobs.get("w1_mult", 1.0)),
            float(knobs.get("w2_mult", 1.0)),
            float(knobs.get("w3_mult", 1.0)),
        ],
        dtype=float,
    )


def score_gammas(
    vec: np.ndarray,
    *,
    gammas: np.ndarray,
    N: int = 13,
    n_sectors: int = 6,
    alpha: float = 0.45,
    beta: float = 0.25,
    gamma: float = 0.15,
) -> dict[str, Any]:
    """F for a dimensionless knob vector on an explicit spectrum.

    Same objective as `score_worker.score_vec` / `harness.score_configuration`,
    but the spectrum is passed in rather than selected by `kind`, so held-out
    windows and adversarial seeds go through an identical code path.
    """
    g = np.asarray(gammas, dtype=float).ravel()
    n_zeros = int(g.size)
    kn = vec_to_knobs(vec, float(g[-1]))
    try:
        der = Keymaker(N=N, n_zeros=n_zeros, n_sectors=n_sectors).forge(**kn, gammas=g)
        lock = build_lock(der)
        key = build_key(der)
        res = residual(lock, key, action=der.action)
        land = build_moduli_landscape(
            field=der.field, action=der.action, critical=der.critical
        )
        test = test_valley_occupancy(
            key.thetas,
            landscape=land,
            labels=[f"k{i + 1}" for i in range(len(key.thetas))],
            spectral_gaps=key.spectral_gaps,
        )
    except Exception as exc:  # noqa: BLE001 - infeasible knobs are a normal DE outcome
        return {
            "F": FAIL_F,
            "R": FAIL_F,
            "knobs": kn,
            "occupancy": 0.0,
            "n_keys": 0,
            "n_valleys": 0,
            "mean_dist": 1.0,
            "breakdown": {},
            "diagnostics": {},
            "error": str(exc),
        }

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
        "F": float(F),
        "R": float(res.total),
        "knobs": kn,
        "occupancy": occ,
        "n_keys": n_keys,
        "n_valleys": n_valleys,
        "mean_dist": float(test.mean_distance_to_valley),
        "breakdown": res.to_dict(),
        "diagnostics": res.diagnostics or {},
    }


def refit(
    gammas: np.ndarray,
    *,
    N: int = 13,
    n_sectors: int = 6,
    popsize: int = 15,
    maxiter: int = 120,
    polish_iter: int = 200,
    de_seed: int = 0,
    label: str = "",
) -> dict[str, Any]:
    """Fit the 8 knobs to one spectrum from a neutral start. Returns best + evidence."""
    g = np.asarray(gammas, dtype=float).ravel()
    g_last = float(g[-1])

    trace: list[float] = []
    best = {"F": np.inf}
    n_eval = 0
    best_at = -1

    def objective(v: np.ndarray) -> float:
        nonlocal n_eval, best, best_at
        n_eval += 1
        out = score_gammas(v, gammas=g, N=N, n_sectors=n_sectors)
        f = float(out["F"])
        if f < best["F"]:
            best = {**out, "vec": np.asarray(v, dtype=float).copy()}
            best_at = n_eval
        trace.append(best["F"])
        return f

    t0 = time.time()
    # tol=0/atol=0: never exit early, so every arm burns an identical budget.
    de = differential_evolution(
        objective,
        bounds=list(BOUNDS),
        maxiter=int(maxiter),
        popsize=int(popsize),
        mutation=(0.35, 1.25),
        recombination=0.80,
        seed=int(de_seed),
        polish=False,
        init="latinhypercube",
        tol=0.0,
        atol=0.0,
        updating="immediate",
    )
    f_pre_polish = float(best["F"])
    evals_de = n_eval

    # Deterministic L-BFGS polish from the DE optimum.
    minimize(
        objective,
        np.asarray(de.x, dtype=float),
        method="L-BFGS-B",
        bounds=list(BOUNDS),
        options={"maxiter": int(polish_iter)},
    )
    elapsed = time.time() - t0

    f_best = float(best["F"])
    return {
        "label": label,
        "F": f_best,
        "R": float(best.get("R", FAIL_F)),
        "occupancy": float(best.get("occupancy", 0.0)),
        "n_keys": int(best.get("n_keys", 0)),
        "n_valleys": int(best.get("n_valleys", 0)),
        "mean_dist": float(best.get("mean_dist", 1.0)),
        "knobs": best.get("knobs", {}),
        "best_vec": best["vec"].tolist() if "vec" in best else [],
        "breakdown": best.get("breakdown", {}),
        "diagnostics": best.get("diagnostics", {}),
        "gammas": g.tolist(),
        "g_last": g_last,
        "de_seed": int(de_seed),
        "convergence": {
            "n_eval": n_eval,
            "evals_de": evals_de,
            "best_found_at_eval": best_at,
            # ~1.0 means the best arrived at the very end: budget likely binding.
            "best_at_budget_fraction": (best_at / n_eval) if n_eval else 0.0,
            "F_pre_polish": f_pre_polish,
            "polish_gain": f_pre_polish - f_best,
            "de_nit": int(getattr(de, "nit", -1)),
            "trace_subsampled": [float(x) for x in trace[:: max(1, len(trace) // 200)]],
            "seconds": elapsed,
        },
        "budget": {
            "popsize": int(popsize),
            "maxiter": int(maxiter),
            "polish_iter": int(polish_iter),
            "n_dim": N_DIM,
            "warm_start": False,
            "early_stop_disabled": True,
        },
        "config": {"N": N, "n_zeros": int(g.size), "n_sectors": n_sectors},
    }


def refit_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Picklable process-pool entry: build the spectrum, then refit it.

    payload: kind, instance, base (list), N, n_sectors, popsize, maxiter,
             polish_iter, master_seed
    """
    from realm.hw import apply_blas_thread_env

    apply_blas_thread_env(1)

    kind = str(payload["kind"])
    inst = int(payload["instance"])
    base = np.asarray(payload["base"], dtype=float)
    k = int(payload.get("k", base.size))

    # Independent streams: the spectrum draw must not correlate with the search path.
    # arm_seed_id, not hash(kind) - str hashing is per-process randomized.
    ss = np.random.SeedSequence([int(payload.get("master_seed", 0)), arm_seed_id(kind), inst])
    spec_ss, opt_ss = ss.spawn(2)
    rng = np.random.default_rng(spec_ss)
    de_seed = int(np.random.default_rng(opt_ss).integers(0, 2**31 - 1))

    gammas = make_adversarial_seed(kind, k, rng, base=base)
    out = refit(
        gammas,
        N=int(payload.get("N", 13)),
        n_sectors=int(payload.get("n_sectors", 6)),
        popsize=int(payload.get("popsize", 15)),
        maxiter=int(payload.get("maxiter", 120)),
        polish_iter=int(payload.get("polish_iter", 200)),
        de_seed=de_seed,
        label=f"{kind}#{inst}",
    )
    out["kind"] = kind
    out["instance"] = inst
    out["deterministic_spectrum"] = kind in DETERMINISTIC
    return out
