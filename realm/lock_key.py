"""Master Lock meets the Keymaker — fixed-point consistency of the derivation.

Roles
-----
Master Lock
    The zeta field structure that must be *opened*: gap-phase shape, spectral
    action landscape S_Λ, and the set Crit(S) of preferred holonomies.

Keymaker
    The derivation engine that forges geometric keys: θ* → multi-mode C_N →
    sheaf L_F → λ_gap, and returns them as a DerivationResult.

Meeting
    A key opens the lock when the lock–key residual R is below threshold.
    R measures *structural* agreement only (never λ = γ identity):

      R = w1 · shape_L1(induced_gaps, seed_gaps)
        + w2 · (1 - |corr(S(θ*), λ_gap)|)_+
        + w3 · crit_coverage  (how well θ* cover lock minima)
        + w4 · return_map_err (key → reconstructed phases → lock)

The Keymaker refines knobs (Λ, ω-scale, weight power) until R is minimized
and meets the lock, or until the iteration budget is exhausted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import minimize

from realm.derive import DerivationResult, Deriver, SpectralAction, critical_holonomies

logger = logging.getLogger(__name__)


def _norm_gaps(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float).ravel()
    if x.size == 0:
        return x
    return x / (np.mean(x) + 1e-15)


def _shape_l1(a: np.ndarray, b: np.ndarray) -> float:
    a, b = _norm_gaps(a), _norm_gaps(b)
    m = min(a.size, b.size)
    if m == 0:
        return 1.0
    return float(np.mean(np.abs(a[:m] - b[:m])))


def _corr_term(x: np.ndarray, y: np.ndarray) -> float:
    x, y = np.asarray(x, float).ravel(), np.asarray(y, float).ravel()
    m = min(x.size, y.size)
    if m < 2 or np.std(x[:m]) < 1e-15 or np.std(y[:m]) < 1e-15:
        return 1.0  # worst
    c = float(np.corrcoef(x[:m], y[:m])[0, 1])
    if not np.isfinite(c):
        return 1.0
    return float(1.0 - abs(c))  # 0 = perfect |corr|


def _circular_dist(a: float, b: float) -> float:
    d = abs(a - b) % (2 * np.pi)
    return float(min(d, 2 * np.pi - d))


@dataclass
class LockState:
    """Master Lock: what the zeta field requires of any valid key."""

    seed_gaps: np.ndarray
    gap_phases: np.ndarray
    minima_theta: np.ndarray
    omega: np.ndarray
    Lambda: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed_gaps": self.seed_gaps.tolist(),
            "gap_phases": self.gap_phases.tolist(),
            "minima_theta": self.minima_theta.tolist(),
            "omega": self.omega.tolist(),
            "Lambda": self.Lambda,
            "role": "master_lock",
        }


@dataclass
class KeyState:
    """Key forged by the Keymaker from a derivation result."""

    thetas: np.ndarray
    spectral_gaps: np.ndarray
    S_at: np.ndarray
    induced_gaps: np.ndarray

    def to_dict(self) -> dict[str, Any]:
        return {
            "thetas": self.thetas.tolist(),
            "spectral_gaps": self.spectral_gaps.tolist(),
            "S_at": self.S_at.tolist(),
            "induced_gaps": self.induced_gaps.tolist(),
            "role": "key",
        }


@dataclass
class ResidualBreakdown:
    shape_l1: float
    corr_penalty: float
    crit_coverage: float
    return_map_err: float
    total: float
    weights: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "shape_l1": self.shape_l1,
            "corr_penalty": self.corr_penalty,
            "crit_coverage": self.crit_coverage,
            "return_map_err": self.return_map_err,
            "total": self.total,
            "weights": self.weights,
        }


def build_lock(result: DerivationResult) -> LockState:
    mins = [c["theta"] for c in result.critical if c["kind"] == "minimum"]
    if not mins:
        mins = [c["theta"] for c in result.critical]
    return LockState(
        seed_gaps=result.field.gaps.copy(),
        gap_phases=result.field.gap_phases(),
        minima_theta=np.array(mins, dtype=float),
        omega=result.action.omega.copy(),
        Lambda=result.action.cutoff_Lambda,
    )


def build_key(result: DerivationResult) -> KeyState:
    gaps = np.array([s.spectral_gap for s in result.spectra], dtype=float)
    thetas = np.array([s.twist for s in result.sectors], dtype=float)
    S_at = np.array([float(result.action.S(t)) for t in thetas], dtype=float)
    ind = np.diff(np.sort(gaps)) if gaps.size >= 2 else np.array([])
    return KeyState(
        thetas=thetas,
        spectral_gaps=gaps,
        S_at=S_at,
        induced_gaps=ind,
    )


def return_map_phases(key: KeyState) -> np.ndarray:
    """Key → reconstructed phases: sort λ_gap → map to (0,2π) like gap_phases.

    This is the key trying the lock cylinder — not claiming λ=γ.
    """
    g = np.sort(key.spectral_gaps)
    if g.size < 2:
        return np.zeros(0)
    d = np.diff(g)
    return (d / (np.mean(d) + 1e-15)) * (np.pi / 2.0)


def residual(
    lock: LockState,
    key: KeyState,
    action: SpectralAction | None = None,
    weights: dict[str, float] | None = None,
) -> ResidualBreakdown:
    """Lock–key residual: Crit(S) consistency — not λ≈γ shape matching.

    Components
    ----------
    stationarity  mean |S'(θ_key)| normalized  (keys must sit on Crit)
    coverage      lock minima each have a nearby key pin
    corr          1-|corr(S(θ),λ_gap)|         (action–geometry coupling)
    pin_align     key thetas align to lock minima set (symmetric Hausdorff/π)
    """
    w = weights or {
        "shape": 0.30,  # stationarity (reuses shape_l1 field in breakdown)
        "corr": 0.25,
        "coverage": 0.25,
        "return": 0.20,  # pin alignment
    }

    # 1) stationarity: keys should be critical points of the lock's action
    if action is not None and key.thetas.size:
        dS = np.array([float(action.dS(t)) for t in key.thetas], dtype=float)
        # normalize by typical scale of dS on [0,2π)
        probe = np.linspace(0.1, 2 * np.pi - 0.1, 64)
        scale = float(np.mean(np.abs(action.dS(probe)))) + 1e-15
        stationarity = float(np.mean(np.abs(dS)) / scale)
        stationarity = min(stationarity, 2.0) / 2.0  # cap to [0,1]
    else:
        stationarity = 1.0

    # 2) |corr(S, λ)| high is good
    corr_pen = _corr_term(key.S_at, key.spectral_gaps)

    # 3) coverage: each lock minimum has a nearby key theta
    if lock.minima_theta.size == 0 or key.thetas.size == 0:
        coverage = 1.0
    else:
        dists = []
        for m in lock.minima_theta:
            dists.append(min(_circular_dist(m, t) for t in key.thetas))
        coverage = float(np.mean(dists) / np.pi)

    # 4) pin alignment: Hausdorff-ish distance between key set and lock minima
    if lock.minima_theta.size == 0 or key.thetas.size == 0:
        pin = 1.0
    else:
        d1 = [min(_circular_dist(t, m) for m in lock.minima_theta) for t in key.thetas]
        d2 = [min(_circular_dist(m, t) for t in key.thetas) for m in lock.minima_theta]
        pin = float((np.mean(d1) + np.mean(d2)) / 2.0 / np.pi)

    total = (
        w["shape"] * stationarity
        + w["corr"] * corr_pen
        + w["coverage"] * coverage
        + w["return"] * pin
    )
    return ResidualBreakdown(
        shape_l1=stationarity,
        corr_penalty=corr_pen,
        crit_coverage=coverage,
        return_map_err=pin,
        total=float(total),
        weights=w,
    )


@dataclass
class MeetResult:
    """Outcome of the lock–keymaker meeting."""

    locked: bool
    threshold: float
    residual: ResidualBreakdown
    best_knobs: dict[str, float]
    history: list[dict[str, Any]]
    derivation: DerivationResult
    lock: LockState
    key: KeyState
    iterations: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ontology": "master_lock_meets_keymaker",
            "locked": self.locked,
            "threshold": self.threshold,
            "residual": self.residual.to_dict(),
            "best_knobs": self.best_knobs,
            "iterations": self.iterations,
            "history": self.history,
            "lock": self.lock.to_dict(),
            "key": self.key.to_dict(),
            "derivation_summary": self.derivation.summary(),
            "verdict": (
                "LOCKED — key opens the master lock"
                if self.locked
                else "UNSEALED — residual above threshold; Keymaker continues"
            ),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "verdict": self.to_dict()["verdict"],
            "locked": self.locked,
            "R": self.residual.total,
            "threshold": self.threshold,
            "breakdown": self.residual.to_dict(),
            "knobs": self.best_knobs,
            "iterations": self.iterations,
            "n_sectors": len(self.derivation.sectors),
            "thetas": self.key.thetas.tolist(),
            "spectral_gaps": self.key.spectral_gaps.tolist(),
        }


@dataclass
class Keymaker:
    """Forges keys by running the derivation with tunable knobs."""

    N: int = 11
    d: int = 2
    n_zeros: int = 12
    n_sectors: int = 6

    def forge(
        self,
        Lambda: float | None = None,
        omega_scale: float = 1.0,
        weight_power: float = 1.0,
    ) -> DerivationResult:
        return Deriver(
            N=self.N,
            d=self.d,
            n_zeros=self.n_zeros,
            n_sectors=self.n_sectors,
            Lambda=Lambda,
            omega_scale=omega_scale,
            weight_power=weight_power,
        ).run()


@dataclass
class MasterLockProtocol:
    """Iterate Keymaker knobs until the key opens the lock (or budget ends)."""

    N: int = 11
    n_zeros: int = 12
    n_sectors: int = 6
    threshold: float = 0.22
    max_iter: int = 24
    # search bounds for knobs
    Lambda_scale_bounds: tuple[float, float] = (0.5, 4.0)  # × g[-1]
    omega_scale_bounds: tuple[float, float] = (0.5, 2.5)
    weight_power_bounds: tuple[float, float] = (0.5, 2.5)

    def meet(self) -> MeetResult:
        km = Keymaker(N=self.N, n_zeros=self.n_zeros, n_sectors=self.n_sectors)
        field_probe = km.forge()  # initial
        g_last = float(field_probe.field.gammas[-1])

        history: list[dict[str, Any]] = []
        best: tuple[float, dict[str, float], DerivationResult, ResidualBreakdown, LockState, KeyState] | None = None

        def evaluate(knobs: np.ndarray) -> float:
            lam_scale, om_s, wpow = [float(x) for x in knobs]
            Lambda = lam_scale * g_last
            try:
                der = km.forge(Lambda=Lambda, omega_scale=om_s, weight_power=wpow)
            except Exception as exc:  # noqa: BLE001
                logger.warning("forge failed: %s", exc)
                return 10.0
            lock = build_lock(der)
            key = build_key(der)
            res = residual(lock, key, action=der.action)
            nonlocal best
            if best is None or res.total < best[0]:
                best = (res.total, {"Lambda": Lambda, "omega_scale": om_s, "weight_power": wpow}, der, res, lock, key)
            history.append(
                {
                    "Lambda": Lambda,
                    "omega_scale": om_s,
                    "weight_power": wpow,
                    "R": res.total,
                    "breakdown": res.to_dict(),
                }
            )
            logger.info(
                "Keymaker try Λ=%.2f ωs=%.3f wp=%.3f → R=%.4f (stat=%.3f corr=%.3f cov=%.3f pin=%.3f)",
                Lambda,
                om_s,
                wpow,
                res.total,
                res.shape_l1,
                res.corr_penalty,
                res.crit_coverage,
                res.return_map_err,
            )
            return res.total

        # Multi-start local refinement of knobs
        starts = [
            np.array([2.0, 1.0, 1.0]),
            np.array([1.0, 1.2, 0.8]),
            np.array([3.0, 0.8, 1.5]),
            np.array([1.5, 1.5, 1.2]),
            np.array([2.5, 1.0, 0.7]),
        ]
        bounds = [
            self.Lambda_scale_bounds,
            self.omega_scale_bounds,
            self.weight_power_bounds,
        ]
        n_eval = 0
        for s0 in starts:
            if n_eval >= self.max_iter:
                break
            minimize(
                evaluate,
                s0,
                method="L-BFGS-B",
                bounds=bounds,
                options={"maxiter": max(3, self.max_iter // len(starts)), "ftol": 1e-5},
            )
            n_eval = len(history)

        # Dense grid fallback if still unsealed
        if best is None or best[0] > self.threshold:
            for lam_s in np.linspace(*self.Lambda_scale_bounds, 4):
                for om in np.linspace(*self.omega_scale_bounds, 3):
                    for wp in np.linspace(*self.weight_power_bounds, 3):
                        if len(history) >= self.max_iter * 2:
                            break
                        evaluate(np.array([lam_s, om, wp]))

        assert best is not None
        R, knobs, der, res, lock, key = best
        locked = R <= self.threshold
        logger.info(
            "MEET: R=%.4f threshold=%.4f → %s",
            R,
            self.threshold,
            "LOCKED" if locked else "UNSEALED",
        )
        return MeetResult(
            locked=locked,
            threshold=self.threshold,
            residual=res,
            best_knobs=knobs,
            history=history,
            derivation=der,
            lock=lock,
            key=key,
            iterations=len(history),
        )


def meet_lock(
    N: int = 11,
    threshold: float = 0.22,
    max_iter: int = 24,
    **kwargs,
) -> MeetResult:
    """One-liner: run until master lock meets keymaker (or budget ends)."""
    return MasterLockProtocol(N=N, threshold=threshold, max_iter=max_iter, **kwargs).meet()
