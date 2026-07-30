"""Master Lock meets the Keymaker — fixed-point consistency of the derivation.

Error R is the gradient: each component points at a concrete fix
(stationarity, coverage, corr(S,λ), pin align / density-scaled return map).

Keymaker knobs (global search):
  Λ, ω-scale, weight_power, tier_split, low_boost, w1/w2/w3_mult

Never tests λ = γ identity — only structural lock–key agreement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import basinhopping, differential_evolution, minimize

from realm.derive import DerivationResult, Deriver, SpectralAction, mean_spacing_density

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
        return 1.0
    c = float(np.corrcoef(x[:m], y[:m])[0, 1])
    if not np.isfinite(c):
        return 1.0
    return float(1.0 - abs(c))


def _circular_dist(a: float, b: float) -> float:
    d = abs(a - b) % (2 * np.pi)
    return float(min(d, 2 * np.pi - d))


@dataclass
class LockState:
    seed_gaps: np.ndarray
    gap_phases: np.ndarray
    minima_theta: np.ndarray
    omega: np.ndarray
    Lambda: float
    gammas: np.ndarray

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed_gaps": self.seed_gaps.tolist(),
            "gap_phases": self.gap_phases.tolist(),
            "minima_theta": self.minima_theta.tolist(),
            "omega": self.omega.tolist(),
            "Lambda": self.Lambda,
            "gammas": self.gammas.tolist(),
            "role": "master_lock",
        }


@dataclass
class KeyState:
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
    shape_l1: float  # stationarity
    corr_penalty: float
    crit_coverage: float
    return_map_err: float
    total: float
    weights: dict[str, float]
    diagnostics: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "stationarity": self.shape_l1,
            "corr_penalty": self.corr_penalty,
            "crit_coverage": self.crit_coverage,
            "return_map_err": self.return_map_err,
            "total": self.total,
            "weights": self.weights,
        }
        if self.diagnostics:
            d["diagnostics"] = self.diagnostics
        return d


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
        gammas=result.field.gammas.copy(),
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


def _quantile_align(a: np.ndarray, b: np.ndarray, n: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """Mean-normalize and sample matching quantiles (scale-free shape compare)."""
    a = _norm_gaps(np.asarray(a, float).ravel())
    b = _norm_gaps(np.asarray(b, float).ravel())
    if a.size == 0 or b.size == 0:
        return np.zeros(0), np.zeros(0)
    n = int(max(3, min(n, a.size + 2, b.size + 2)))
    q = np.linspace(0.05, 0.95, n)
    return np.quantile(a, q), np.quantile(b, q)


def _cum_ladder(x: np.ndarray, n: int = 8) -> np.ndarray:
    """Unit cumulative ladder of mean-normalized spacings."""
    x = _norm_gaps(np.asarray(x, float).ravel())
    if x.size == 0:
        return np.zeros(0)
    c = np.cumsum(x)
    c = c / (c[-1] + 1e-15)
    grid = np.linspace(0.0, 1.0, n)
    return np.interp(grid, np.linspace(0.0, 1.0, c.size), c)


def return_map_phases_density(
    key: KeyState,
    lock: LockState,
) -> tuple[np.ndarray, np.ndarray]:
    """Density-scaled return: sheaf λ-spacings vs seed gaps (both unfolded).

    Not λ=γ identity — only shape agreement of successive spacing measures
    after Riemann–von Mangoldt density scaling. Quantile-aligned for unequal
    sequence lengths (sectors vs zeros).
    """
    g = np.sort(key.spectral_gaps)
    if g.size < 2 or lock.gammas.size < 2:
        return np.zeros(0), np.zeros(0)

    dlam = np.diff(g)
    # Density-scale λ-spacings at rank-matched ordinates
    ranks = np.linspace(0, 1, len(dlam) + 2)[1:-1]
    T = np.interp(ranks, np.linspace(0, 1, lock.gammas.size), lock.gammas)
    rho = np.array([mean_spacing_density(float(t)) for t in T], dtype=float)
    rho = np.clip(rho, 0.05 * np.mean(rho), None)
    phases = dlam / (rho + 1e-15)

    sg = lock.seed_gaps
    if sg.size == 0:
        return _norm_gaps(phases), np.zeros(0)
    T2 = 0.5 * (lock.gammas[:-1] + lock.gammas[1:])
    m = min(sg.size, T2.size)
    rho2 = np.array([mean_spacing_density(float(t)) for t in T2[:m]], dtype=float)
    rho2 = np.clip(rho2, 0.05 * np.mean(rho2), None)
    ref = sg[:m] / (rho2 + 1e-15)
    return phases, ref


def _soft_ecdf_l1(a: np.ndarray, b: np.ndarray, n_grid: int = 48) -> float:
    """Smoothed CDF L1 on shared support (softer than hard quantiles for L-BFGS)."""
    a = _norm_gaps(np.asarray(a, float).ravel())
    b = _norm_gaps(np.asarray(b, float).ravel())
    if a.size == 0 or b.size == 0:
        return 1.0
    lo = float(min(a.min(), b.min()))
    hi = float(max(a.max(), b.max()))
    if hi - lo < 1e-15:
        return 0.0
    grid = np.linspace(lo, hi, n_grid)
    # Linear-interpolated ECDF (piecewise-linear → smoother than pure step)
    sa, sb = np.sort(a), np.sort(b)
    ca = np.linspace(0.0, 1.0, sa.size)
    cb = np.linspace(0.0, 1.0, sb.size)
    ea = np.interp(grid, sa, ca, left=0.0, right=1.0)
    eb = np.interp(grid, sb, cb, left=0.0, right=1.0)
    return float(np.mean(np.abs(ea - eb)))


def density_return_error(key: KeyState, lock: LockState) -> float:
    """Composite density-return residual in [0, 2].

    Blends soft-ECDF L1, quantile Wasserstein-L1, cumulative-ladder L1, and
    fluctuation RMS — all scale-free. Soft ECDF gives L-BFGS a smoother
    gradient than pure sorted quantiles; not λ ≈ γ.
    """
    phases, ref = return_map_phases_density(key, lock)
    if phases.size == 0 or ref.size == 0:
        return 1.0
    soft = _soft_ecdf_l1(phases, ref)
    qa, qb = _quantile_align(phases, ref, n=max(5, min(phases.size, ref.size, 10)))
    if qa.size == 0:
        return float(np.clip(soft, 0.0, 2.0))
    w1 = float(np.mean(np.abs(qa - qb)))
    n = qa.size
    ca = _cum_ladder(phases, n=n)
    cb = _cum_ladder(ref, n=n)
    cum = float(np.mean(np.abs(ca - cb))) if ca.size and cb.size else 1.0
    fa = float(np.std(_norm_gaps(phases)))
    fb = float(np.std(_norm_gaps(ref)))
    fluc = abs(fa - fb) / (fa + fb + 1e-15)
    return float(
        np.clip(0.30 * soft + 0.25 * w1 + 0.30 * cum + 0.15 * fluc, 0.0, 2.0)
    )


def theta_ladder_l1(key: KeyState, lock: LockState) -> float:
    """Shape L1 between sorted key θ spacings and sorted lock-minima spacings.

    Returns NaN when a ladder has fewer than two entries, because the comparison
    is then *undefined* — there are no spacings to compare. It previously returned
    0.0 there, i.e. a perfect score for absence of evidence, which is the same
    defect Axiom 6.1 rules out and which silently masked under-determined
    configurations. NaN propagates so callers must handle or exclude it.

    Unaffected in the published configuration: with n_sectors=6 and a same-block
    lock, both ladders always carry 6 entries, so this branch never fired there.
    """
    kt = np.sort(key.thetas)
    lt = np.sort(lock.minima_theta)
    if kt.size < 2 or lt.size < 2:
        return float("nan")
    return _shape_l1(np.diff(kt), np.diff(lt))


def residual(
    lock: LockState,
    key: KeyState,
    action: SpectralAction | None = None,
    weights: dict[str, float] | None = None,
) -> ResidualBreakdown:
    w = weights or {
        "shape": 0.30,  # stationarity
        "corr": 0.25,
        "coverage": 0.25,
        "return": 0.20,
    }

    # 1) stationarity
    if action is not None and key.thetas.size:
        dS = np.array([float(action.dS(t)) for t in key.thetas], dtype=float)
        probe = np.linspace(0.1, 2 * np.pi - 0.1, 64)
        scale = float(np.mean(np.abs(action.dS(probe)))) + 1e-15
        stationarity = min(float(np.mean(np.abs(dS)) / scale), 2.0) / 2.0
    else:
        stationarity = 1.0

    # 2) corr
    corr_pen = _corr_term(key.S_at, key.spectral_gaps)

    # 3) coverage
    if lock.minima_theta.size == 0 or key.thetas.size == 0:
        coverage = 1.0
    else:
        dists = [min(_circular_dist(m, t) for t in key.thetas) for m in lock.minima_theta]
        coverage = float(np.mean(dists) / np.pi)

    # 4) pin align + density-scaled return (average of both)
    if lock.minima_theta.size == 0 or key.thetas.size == 0:
        pin = 1.0
    else:
        d1 = [min(_circular_dist(t, m) for m in lock.minima_theta) for t in key.thetas]
        d2 = [min(_circular_dist(m, t) for t in key.thetas) for m in lock.minima_theta]
        pin = float((np.mean(d1) + np.mean(d2)) / 2.0 / np.pi)

    dens_ret = density_return_error(key, lock)
    ladder = theta_ladder_l1(key, lock)
    # Return error: pin seating + θ-ladder vs valley ladder + density map
    return_err = 0.4 * pin + 0.35 * ladder + 0.25 * dens_ret

    total = (
        w["shape"] * stationarity
        + w["corr"] * corr_pen
        + w["coverage"] * coverage
        + w["return"] * return_err
    )
    return ResidualBreakdown(
        shape_l1=stationarity,
        corr_penalty=corr_pen,
        crit_coverage=coverage,
        return_map_err=return_err,
        total=float(total),
        weights=w,
        diagnostics={
            "pin_align": pin,
            "theta_ladder_l1": ladder,
            "density_return_l1": dens_ret,
            "corr_S_lambda": 1.0 - corr_pen,
        },
    )


@dataclass
class MeetResult:
    locked: bool
    threshold: float
    residual: ResidualBreakdown
    best_knobs: dict[str, float]
    history: list[dict[str, Any]]
    derivation: DerivationResult
    lock: LockState
    key: KeyState
    iterations: int
    search_method: str = "hybrid"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ontology": "master_lock_meets_keymaker",
            "locked": self.locked,
            "threshold": self.threshold,
            "residual": self.residual.to_dict(),
            "best_knobs": self.best_knobs,
            "iterations": self.iterations,
            "search_method": self.search_method,
            "history": self.history,
            "lock": self.lock.to_dict(),
            "key": self.key.to_dict(),
            "derivation_summary": self.derivation.summary(),
            "verdict": (
                "LOCKED — key opens the master lock"
                if self.locked
                else "UNSEALED — residual above threshold; Keymaker continues"
            ),
            "error_as_gradient": (
                "R components are optimization gradients: stationarity→Crit seating, "
                "corr→S–λ coupling, coverage/return→pin geometry + density-scaled map"
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
            "search_method": self.search_method,
            "n_sectors": len(self.derivation.sectors),
            "thetas": self.key.thetas.tolist(),
            "spectral_gaps": self.key.spectral_gaps.tolist(),
        }


@dataclass
class Keymaker:
    N: int = 11
    d: int = 2
    n_zeros: int = 12
    n_sectors: int = 6

    def forge(self, **knobs) -> DerivationResult:
        gammas = knobs.get("gammas")
        if gammas is not None:
            gammas = np.asarray(gammas, dtype=float).ravel()
        return Deriver(
            N=self.N,
            d=self.d,
            n_zeros=self.n_zeros,
            n_sectors=self.n_sectors,
            Lambda=knobs.get("Lambda"),
            omega_scale=float(knobs.get("omega_scale", 1.0)),
            weight_power=float(knobs.get("weight_power", 1.0)),
            tier_split=float(knobs.get("tier_split", 0.45)),
            low_boost=float(knobs.get("low_boost", 1.0)),
            w1_mult=float(knobs.get("w1_mult", 1.0)),
            w2_mult=float(knobs.get("w2_mult", 1.0)),
            w3_mult=float(knobs.get("w3_mult", 1.0)),
            gammas=gammas,
            omega_span=(
                float(knobs["omega_span"])
                if knobs.get("omega_span") is not None
                else None
            ),
        ).run()


@dataclass
class MasterLockProtocol:
    """Global Keymaker search until R ≤ threshold (or budget ends)."""

    N: int = 11
    n_zeros: int = 12
    n_sectors: int = 6
    threshold: float = 0.18
    max_iter: int = 40
    # knob vector: [Λ_scale, ω_scale, weight_power, tier_split, low_boost, w1, w2, w3]
    bounds: tuple = (
        (0.4, 4.5),   # Λ / g[-1]
        (0.4, 2.8),   # omega_scale
        (0.4, 2.8),   # weight_power
        (0.15, 0.75), # tier_split
        (0.6, 3.5),   # low_boost
        (0.8, 1.2),   # w1_mult
        (0.8, 1.2),   # w2_mult
        (0.8, 1.2),   # w3_mult
    )

    def meet(self) -> MeetResult:
        km = Keymaker(N=self.N, n_zeros=self.n_zeros, n_sectors=self.n_sectors)
        probe = km.forge()
        g_last = float(probe.field.gammas[-1])

        history: list[dict[str, Any]] = []
        best: tuple | None = None

        def knobs_from_vec(v: np.ndarray) -> dict[str, float]:
            return {
                "Lambda": float(v[0]) * g_last,
                "omega_scale": float(v[1]),
                "weight_power": float(v[2]),
                "tier_split": float(v[3]),
                "low_boost": float(v[4]),
                "w1_mult": float(v[5]) if len(v) > 5 else 1.0,
                "w2_mult": float(v[6]) if len(v) > 6 else 1.0,
                "w3_mult": float(v[7]) if len(v) > 7 else 1.0,
            }

        def evaluate(v: np.ndarray) -> float:
            kn = knobs_from_vec(v)
            try:
                der = km.forge(**kn)
            except Exception as exc:  # noqa: BLE001
                logger.warning("forge failed: %s", exc)
                return 10.0
            lock = build_lock(der)
            key = build_key(der)
            res = residual(lock, key, action=der.action)
            nonlocal best
            if best is None or res.total < best[0]:
                best = (res.total, kn, der, res, lock, key)
            history.append({**kn, "R": res.total, "breakdown": res.to_dict()})
            logger.info(
                "Keymaker Λ=%.1f ωs=%.3f wp=%.3f tier=%.2f boost=%.2f "
                "w=(%.2f,%.2f,%.2f) → R=%.4f "
                "(stat=%.3f corr=%.3f cov=%.3f ret=%.3f)",
                kn["Lambda"],
                kn["omega_scale"],
                kn["weight_power"],
                kn["tier_split"],
                kn["low_boost"],
                kn.get("w1_mult", 1.0),
                kn.get("w2_mult", 1.0),
                kn.get("w3_mult", 1.0),
                res.total,
                res.shape_l1,
                res.corr_penalty,
                res.crit_coverage,
                res.return_map_err,
            )
            return res.total

        # --- Phase 1: Differential Evolution (global) ---
        logger.info("Keymaker phase 1: differential evolution (global basin)")
        de = differential_evolution(
            evaluate,
            bounds=list(self.bounds),
            maxiter=max(4, self.max_iter // 8),
            popsize=8,
            mutation=(0.5, 1.2),
            recombination=0.7,
            seed=7,
            polish=False,
            atol=1e-4,
            workers=1,
        )
        logger.info("DE best R=%.4f at %s", float(de.fun), de.x)

        # --- Phase 2: Basin-hopping from DE winner ---
        logger.info("Keymaker phase 2: basin-hopping polish")

        class _Bounds:
            def __init__(self, bounds):
                self.xmin = np.array([b[0] for b in bounds])
                self.xmax = np.array([b[1] for b in bounds])

            def __call__(self, **kwargs):
                x = kwargs["x_new"]
                return bool(np.all(x >= self.xmin) and np.all(x <= self.xmax))

        x0 = np.array(de.x, dtype=float)
        basinhopping(
            evaluate,
            x0,
            niter=max(6, self.max_iter // 5),
            minimizer_kwargs={
                "method": "L-BFGS-B",
                "bounds": list(self.bounds),
                "options": {"maxiter": 8, "ftol": 1e-6},
            },
            accept_test=_Bounds(self.bounds),
            seed=11,
            stepsize=0.25,
        )

        # --- Phase 3: dense local multi-start if still unsealed ---
        if best is None or best[0] > self.threshold:
            logger.info("Keymaker phase 3: multi-start L-BFGS around best")
            centers = [np.array(de.x)]
            if best is not None:
                kn = best[1]
                centers.append(
                    np.array(
                        [
                            kn["Lambda"] / g_last,
                            kn["omega_scale"],
                            kn["weight_power"],
                            kn["tier_split"],
                            kn["low_boost"],
                            kn.get("w1_mult", 1.0),
                            kn.get("w2_mult", 1.0),
                            kn.get("w3_mult", 1.0),
                        ]
                    )
                )
            rng = np.random.default_rng(3)
            for _ in range(4):
                centers.append(
                    np.array([rng.uniform(a, b) for a, b in self.bounds])
                )
            for c in centers:
                minimize(
                    evaluate,
                    c,
                    method="L-BFGS-B",
                    bounds=list(self.bounds),
                    options={"maxiter": 12, "ftol": 1e-7},
                )

        assert best is not None
        R, knobs, der, res, lock, key = best
        locked = R <= self.threshold
        logger.info(
            "MEET: R=%.4f threshold=%.4f → %s (iters=%d)",
            R,
            self.threshold,
            "LOCKED" if locked else "UNSEALED",
            len(history),
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
            search_method="DE+basin_hopping+LBFGS",
        )


def meet_lock(
    N: int = 11,
    threshold: float = 0.18,
    max_iter: int = 40,
    **kwargs,
) -> MeetResult:
    return MasterLockProtocol(N=N, threshold=threshold, max_iter=max_iter, **kwargs).meet()
