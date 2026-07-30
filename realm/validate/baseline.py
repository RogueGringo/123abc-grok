"""Independent lock baseline — Axiom 6.1, the Topological Verification Principle.

Axiom 6.1 states verification as `d(T, T0) < eps` against a **known-good baseline**
T0. The published residual is the degenerate case `T0 = T`:

* `derive.py` draws the sector pool from the critical minima of the spectral action,
* `build_key` reads `key.thetas` from those sector twists,
* `build_lock` reads `lock.minima_theta` from the same critical minima,

so whenever the action yields at least `n_sectors` minima the lock and key are the
same array (measured: bit-identical at <1e-12 for n_sectors=6). Every residual term
that compares them is then identically zero, for any seed spectrum.

The repair forges the baseline from a **disjoint ordinate block** under the *same*
knobs, and evaluates stationarity against the baseline action. That converts four
tautologies into real questions:

| term | tautology under T0 = T | question under an independent T0 |
|---|---|---|
| stationarity | keys are critical points of their own action | do block-A sectors sit at critical points of block-B's action? |
| crit_coverage | minima are a subset of keys | does block-A's key set cover block-B's minima? |
| pin_align | the sets coincide | how far are block-A keys from block-B minima? |
| theta_ladder | the sets coincide | do the two spacing ladders agree in shape? |

Whether they *do* revive is an empirical question this module measures rather than
assumes — see `revival_report`. Terms that stay pinned at zero are to be deleted
from fitness, not rescued.

Per Axiom 9.3 (parameter importance inversion) this module returns a **component
vector** and deliberately offers no static-weight scalar: the observed importance
of `corr_penalty` swings from 87-96% of the null gap under frozen knobs to ~1e-6
after refit, so any fixed blend is mis-weighted in one regime or the other.

Ontology is preserved: geometry is derived off the zeta field, and no sheaf
eigenvalue is ever scored against an ordinate.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from realm.lock_key import (
    Keymaker,
    LockState,
    build_key,
    build_lock,
    residual,
)
from realm.projection import build_moduli_landscape
from realm.projection import test_valley_occupancy as valley_occupancy
from realm.validate.guard import measure_degeneracy

# The four terms that are zero by construction under T0 = T.
DEAD_TERMS = ("stationarity", "crit_coverage", "pin_align", "theta_ladder_l1")

# A term revives if it is not numerically indistinguishable from a structural zero.
REVIVAL_FLOOR = 1e-6

KNOB_KEYS = (
    "Lambda",
    "omega_scale",
    "weight_power",
    "tier_split",
    "low_boost",
    "w1_mult",
    "w2_mult",
    "w3_mult",
)


def _clean_knobs(knobs: dict[str, Any]) -> dict[str, float]:
    """Knob subset the Keymaker accepts, without any injected gammas."""
    out: dict[str, float] = {}
    for k in KNOB_KEYS:
        if k in knobs and knobs[k] is not None:
            out[k] = float(knobs[k])
    return out


def _forge(knobs: dict[str, float], gammas: np.ndarray, N: int, n_sectors: int):
    return Keymaker(N=N, n_zeros=int(gammas.size), n_sectors=n_sectors).forge(
        **knobs, gammas=gammas
    )


def score_with_independent_baseline(
    *,
    knobs: dict[str, Any],
    key_gammas: np.ndarray,
    lock_gammas: np.ndarray,
    N: int = 13,
    n_sectors: int = 6,
) -> dict[str, Any]:
    """Score a key derived from one ordinate block against a baseline from another.

    `key_gammas` and `lock_gammas` must be the same length so the two derivations
    are structurally comparable; they should be **disjoint** for the baseline to be
    independent, but that is measured rather than trusted (the returned
    `degeneracy` block reports the coincidence that actually occurred).

    Returns a component vector plus the degeneracy signature. No static-weight
    scalar is returned, by design — see Axiom 9.3 in the module docstring.
    """
    kg = np.asarray(key_gammas, dtype=float).ravel()
    lg = np.asarray(lock_gammas, dtype=float).ravel()
    if kg.size != lg.size:
        raise ValueError(
            f"key and lock blocks must be the same length, got {kg.size} and {lg.size}"
        )
    if kg.size < 2:
        raise ValueError("need at least 2 ordinates per block")

    kn = _clean_knobs(knobs)

    # Two independent derivations under identical knobs.
    der_key = _forge(kn, kg, N, n_sectors)
    der_lock = _forge(kn, lg, N, n_sectors)

    key = build_key(der_key)
    # Baseline lock: minima and landscape from the DISJOINT block's action.
    lock_ref = build_lock(der_lock)
    lock = LockState(
        seed_gaps=lock_ref.seed_gaps,
        gap_phases=lock_ref.gap_phases,
        minima_theta=lock_ref.minima_theta,
        omega=lock_ref.omega,
        Lambda=lock_ref.Lambda,
        gammas=lock_ref.gammas,
    )

    # Stationarity is evaluated against the BASELINE action. Passing the key's own
    # action would restore the tautology (dS = 0 at its own critical points).
    res = residual(lock, key, action=der_lock.action)

    land = build_moduli_landscape(
        field=der_lock.field, action=der_lock.action, critical=der_lock.critical
    )
    occ = valley_occupancy(
        key.thetas,
        landscape=land,
        labels=[f"k{i + 1}" for i in range(len(key.thetas))],
        spectral_gaps=key.spectral_gaps,
    )

    diag = res.diagnostics or {}
    components = {
        "stationarity": float(res.shape_l1),
        "crit_coverage": float(res.crit_coverage),
        "pin_align": float(diag.get("pin_align", float("nan"))),
        "theta_ladder_l1": float(diag.get("theta_ladder_l1", float("nan"))),
        "corr_penalty": float(res.corr_penalty),
        "density_return_l1": float(diag.get("density_return_l1", float("nan"))),
        "occupancy": float(occ.occupancy_fraction),
        "n_keys": int(len(key.thetas)),
        "n_valleys": int(len(land.valleys)),
    }

    sig = measure_degeneracy(
        key_thetas=key.thetas,
        lock_minima=lock.minima_theta,
        stationarity=components["stationarity"],
        crit_coverage=components["crit_coverage"],
        occupancy=components["occupancy"],
    )

    return {
        "components": components,
        "degeneracy": sig.to_dict(),
        "baseline": {
            "independent_block": True,
            "key_block": [float(kg[0]), float(kg[-1])],
            "lock_block": [float(lg[0]), float(lg[-1])],
            "disjoint": bool(kg[-1] < lg[0] or lg[-1] < kg[0]),
            "stationarity_against": "baseline_action",
            "axiom": "6.1 topological_verification_principle",
        },
        "config": {"N": N, "n_sectors": n_sectors, "k": int(kg.size)},
        "ontology": "independent_baseline_not_lambda_eq_gamma",
    }


def revival_report(
    component_rows: list[dict[str, Any]], *, floor: float = REVIVAL_FLOOR
) -> dict[str, Any]:
    """Did the dead terms revive? This decides which survive into fitness.

    Stage 1's criterion: non-zero variance and 5th percentile above `floor`. A term
    failing it is structurally dead even with an independent baseline and must be
    demoted to a diagnostic permanently.
    """
    report: dict[str, Any] = {}
    for term in DEAD_TERMS:
        vals = np.array(
            [float(r.get(term, np.nan)) for r in component_rows], dtype=float
        )
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            report[term] = {
                "n": 0,
                "variance": 0.0,
                "p5": 0.0,
                "median": 0.0,
                "revived": False,
                "note": "no finite observations",
            }
            continue
        var = float(np.var(vals))
        p5 = float(np.percentile(vals, 5))
        report[term] = {
            "n": int(vals.size),
            "variance": var,
            "p5": p5,
            "median": float(np.median(vals)),
            "min": float(np.min(vals)),
            "max": float(np.max(vals)),
            "revived": bool(var > 0.0 and p5 > floor),
        }
    report["_criterion"] = {
        "rule": "variance > 0 and p5 > floor",
        "floor": float(floor),
        "axiom": "6.1",
        "on_failure": "demote term to diagnostic; remove from fitness permanently",
    }
    return report
