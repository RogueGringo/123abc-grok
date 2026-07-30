"""Continue the derivation: zeta field → spectral action → critical holonomies → geometry.

Ontology (locked):
  Geometry is *derived off* the zeta field. The actual γ_n are seeds / weights,
  never identified with sheaf eigenvalues.

Derivation ladder
-----------------
  D0  ZetaField seed {γ_n}
  D1  Unfolded heights & mean density (Weyl / Riemann–von Mangoldt)
  D2  Spectral action S(θ) on U(1) holonomy of the cycle
  D3  Critical monodromies θ* ∈ Crit(S)  → discrete sectors
  D4  Geometric realization: multi-mode embedding C_N ⊂ R³
  D5  Sheaf Laplacian L_F(θ*) and its spectrum (geometry's own spectrum)
  D6  Structural readout (not λ=γ claims)

Spectral action (finite model of Connes-style spectral action on S¹):

  S_Λ(θ) = Σ_{n=1}^{K} w_n ( 1 - cos(ω_n θ) )

where ω_n = γ_n / γ_1 (dimensionless frequencies off the zeros) and
w_n = exp(-γ_n / Λ) is a heat-kernel cutoff. Critical points satisfy

  S'(θ) = Σ_n w_n ω_n sin(ω_n θ) = 0.

Each θ* is a holonomy the field *prefers* — geometry off the zetas.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import brentq

from realm.sheaf_backend import sharp_laplacian
from realm.types import Spectrum
from realm.zeta_field import ZETA_ZEROS_IMAG, ZetaField
from realm.zeta_geometry import InducedSector, embed_cycle_from_twist

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# D1 — unfolding
# ---------------------------------------------------------------------------

def mean_spacing_density(T: float) -> float:
    """Local mean density of ordinates: (1/2π) log(T/2π) (Riemann–von Mangoldt)."""
    T = max(float(T), 2.0 * np.pi + 1e-6)
    return float(np.log(T / (2.0 * np.pi)) / (2.0 * np.pi))


def unfold_zeros(gammas: np.ndarray) -> np.ndarray:
    """Approximate unfolded heights t_n = ∫^γ mean density.

    Uses the integrated density N(T) ≈ (T/2π) log(T/2π) - T/2π.
    """
    g = np.asarray(gammas, dtype=float)
    # N(T) = (T/2π) log(T/2π e) = (T/2π)(log(T/2π) - 1)
    def N(T):
        T = np.maximum(T, 2 * np.pi * np.e)
        return (T / (2 * np.pi)) * (np.log(T / (2 * np.pi)) - 1.0)

    return N(g) - N(g[0])  # start at 0


# ---------------------------------------------------------------------------
# D2 — spectral action on holonomy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SpectralAction:
    """S_Λ(θ) = Σ w_n (1 - cos(ω_n θ)) on U(1) holonomy angle θ."""

    omega: np.ndarray  # dimensionless frequencies from γ
    weights: np.ndarray  # heat weights
    cutoff_Lambda: float

    @classmethod
    def from_field(
        cls,
        field: ZetaField,
        Lambda: float | None = None,
        omega_scale: float = 1.0,
        weight_power: float = 1.0,
        tier_split: float = 0.45,
        low_boost: float = 1.0,
        w1_mult: float = 1.0,
        w2_mult: float = 1.0,
        w3_mult: float = 1.0,
    ) -> "SpectralAction":
        """Build action; knobs tune cutoff, frequencies, and multi-scale weights.

        Multi-scale (tiered) weighting
        ------------------------------
        Lower-order zeros (first tier_split fraction by index) receive an extra
        factor ``low_boost``, so the spectral action can emphasize the IR
        scaffolding that dominates projected 3D geometry while still keeping
        UV zeros in the sum. Then apply heat kernel and power reshape.

        IR micro-tuning (w1_mult, w2_mult, w3_mult)
        -------------------------------------------
        Scalar multipliers on the first three zeta modes (bounded ~0.8–1.2 in
        search). Local control of lowest-frequency Fourier content — shifts
        Crit(θ) angular placement enough to sculpt λ-gap quantiles without
        breaking the global lock–key seating.
        """
        g = field.gammas
        Lambda = float(Lambda if Lambda is not None else 2.0 * g[-1])
        omega = (g / (g[0] + 1e-15)) * float(omega_scale)
        weights = np.exp(-g / Lambda) ** float(weight_power)
        # Tiered IR boost on the first floor(tier_split * K) zeros
        k = g.size
        n_low = max(1, int(np.floor(float(np.clip(tier_split, 0.05, 0.95)) * k)))
        tier = np.ones(k, dtype=float)
        tier[:n_low] *= float(max(low_boost, 1e-6))
        weights = weights * tier
        # Per-mode IR micro-tuning on lowest three harmonics
        ir = np.array(
            [float(w1_mult), float(w2_mult), float(w3_mult)],
            dtype=float,
        )
        ir = np.clip(ir, 1e-6, None)
        n_ir = min(3, k)
        weights[:n_ir] *= ir[:n_ir]
        # Multi-scale harmonic envelope (Witten–Morse landscape aid): mild
        # mid-band boost so intermediate-length Crit structure is not washed
        # out by pure IR or pure UV heat weighting. Scale-free, sum-normalized.
        if k >= 6:
            idx = np.arange(k, dtype=float)
            mid = 0.5 * (k - 1)
            width = max(0.25 * k, 1.0)
            envelope = 1.0 + 0.12 * np.exp(-((idx - mid) ** 2) / (2.0 * width**2))
            weights = weights * envelope
        weights = weights / (np.sum(weights) + 1e-15)
        return cls(omega=omega, weights=weights, cutoff_Lambda=Lambda)

    def S(self, theta: np.ndarray | float) -> np.ndarray | float:
        th = np.asarray(theta, dtype=float)
        # broadcast: (...,) vs (K,)
        acc = np.zeros_like(th, dtype=float)
        for w, om in zip(self.weights, self.omega):
            acc = acc + w * (1.0 - np.cos(om * th))
        return acc

    def dS(self, theta: np.ndarray | float) -> np.ndarray | float:
        th = np.asarray(theta, dtype=float)
        acc = np.zeros_like(th, dtype=float)
        for w, om in zip(self.weights, self.omega):
            acc = acc + w * om * np.sin(om * th)
        return acc

    def d2S(self, theta: np.ndarray | float) -> np.ndarray | float:
        th = np.asarray(theta, dtype=float)
        acc = np.zeros_like(th, dtype=float)
        for w, om in zip(self.weights, self.omega):
            acc = acc + w * (om**2) * np.cos(om * th)
        return acc


# ---------------------------------------------------------------------------
# D3 — critical holonomies
# ---------------------------------------------------------------------------

def critical_holonomies(
    action: SpectralAction,
    n_grid: int = 4000,
    max_crit: int = 12,
) -> list[dict[str, float]]:
    """Find θ* ∈ (0, 2π) with S'(θ*)=0, classify min/max/saddle by S''."""
    grid = np.linspace(1e-6, 2 * np.pi - 1e-6, n_grid)
    d = action.dS(grid)
    crits: list[dict[str, float]] = []
    for i in range(len(grid) - 1):
        if d[i] == 0.0 or d[i] * d[i + 1] > 0:
            continue
        try:
            th = float(brentq(lambda x: float(action.dS(x)), grid[i], grid[i + 1]))
        except ValueError:
            continue
        s2 = float(action.d2S(th))
        kind = "minimum" if s2 > 0 else ("maximum" if s2 < 0 else "inflection")
        crits.append(
            {
                "theta": th,
                "S": float(action.S(th)),
                "S_second": s2,
                "kind": kind,
            }
        )
    # Dedup
    kept: list[dict[str, float]] = []
    for c in sorted(crits, key=lambda x: x["theta"]):
        if kept and abs(c["theta"] - kept[-1]["theta"]) < 1e-4:
            continue
        kept.append(c)
    # Prefer minima for "stable" geometric sectors; fill with others
    mins = [c for c in kept if c["kind"] == "minimum"]
    rest = [c for c in kept if c["kind"] != "minimum"]
    ordered = mins + rest
    return ordered[:max_crit]


# ---------------------------------------------------------------------------
# D4 — multi-mode geometric realization
# ---------------------------------------------------------------------------

def embed_multimode_cycle(
    N: int,
    theta: float,
    field: ZetaField,
    n_modes: int = 4,
    radius: float = 1.0,
) -> np.ndarray:
    """Realize C_N ⊂ R³ as a Fourier ribbon weighted by the zeta seed.

    x + iy = R(φ) e^{iφ},   z(φ) = Σ_{m=1}^{M} a_m sin(m φ + m θ + ψ_m)

    where a_m ∝ w_m off the first M zeros and ψ_m = ω_m θ carries the holonomy.
    Exact planar closure in (x,y); z is a free height field on the circle.
    """
    g = field.gammas[:n_modes]
    w = np.exp(-g / (2.0 * g[-1]))
    w = w / (np.sum(w) + 1e-15)
    omega = g / (g[0] + 1e-15)
    phi = 2.0 * np.pi * np.arange(N) / N
    # Radial breathing from total action density
    R = radius * (1.0 + 0.06 * np.sum(w[:, None] * np.cos(np.outer(omega, phi) + theta), axis=0))
    x = R * np.cos(phi)
    y = R * np.sin(phi)
    z = np.zeros(N, dtype=float)
    for m, (a, om) in enumerate(zip(w, omega), start=1):
        z += a * np.sin(m * phi + om * theta)
    pts = np.column_stack([x, y, z])
    pts -= pts.mean(axis=0)
    # Normalize size
    scale = np.sqrt(np.mean(np.sum(pts**2, axis=1))) + 1e-15
    pts /= scale
    return pts


# ---------------------------------------------------------------------------
# D5–D6 — full derivation bundle
# ---------------------------------------------------------------------------

@dataclass
class DerivationStep:
    id: str
    title: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "payload": self.payload}


@dataclass
class DerivationResult:
    """Full derived package: field → action → critical θ* → sectors → spectra."""

    field: ZetaField
    action: SpectralAction
    critical: list[dict[str, float]]
    sectors: list[InducedSector]
    spectra: list[Spectrum]
    steps: list[DerivationStep]
    N: int
    d: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ontology": "geometry_derived_off_zeta_spectral_action",
            "N": self.N,
            "d": self.d,
            "field": self.field.to_dict(),
            "action": {
                "omega": self.action.omega.tolist(),
                "weights": self.action.weights.tolist(),
                "Lambda": self.action.cutoff_Lambda,
            },
            "critical_holonomies": self.critical,
            "sectors": [s.to_dict() for s in self.sectors],
            "spectra": [s.to_dict() for s in self.spectra],
            "steps": [s.to_dict() for s in self.steps],
            "spectral_gaps": [float(s.spectral_gap) for s in self.spectra],
            "thetas": [float(s.twist) for s in self.sectors],
        }

    def summary(self) -> dict[str, Any]:
        mins = [c for c in self.critical if c["kind"] == "minimum"]
        return {
            "ontology": "geometry_derived_off_zeta_spectral_action",
            "n_zeros_seed": int(self.field.gammas.size),
            "n_critical": len(self.critical),
            "n_minima": len(mins),
            "n_sectors": len(self.sectors),
            "thetas_minima": [c["theta"] for c in mins],
            "spectral_gaps": [float(s.spectral_gap) for s in self.spectra],
            "steps": [s.id + ": " + s.title for s in self.steps],
        }


@dataclass
class Deriver:
    """Run the derivation ladder end-to-end."""

    N: int = 11
    d: int = 2
    n_zeros: int = 12
    n_sectors: int = 6
    prefer_maxop: bool = True
    Lambda: float | None = None
    multimode: bool = True
    omega_scale: float = 1.0
    weight_power: float = 1.0
    tier_split: float = 0.45
    low_boost: float = 1.0
    w1_mult: float = 1.0
    w2_mult: float = 1.0
    w3_mult: float = 1.0
    gammas: np.ndarray | None = None  # optional seed inject (null battery)

    def run(self) -> DerivationResult:
        steps: list[DerivationStep] = []

        # D0
        if self.gammas is not None:
            field = ZetaField.from_gammas(self.gammas)
        else:
            field = ZetaField.first(self.n_zeros)
        steps.append(
            DerivationStep(
                "D0",
                "ZetaField seed {γ_n} (generative, not eigenvalues)",
                field.to_dict(),
            )
        )

        # D1
        unfolded = unfold_zeros(field.gammas)
        dens = [mean_spacing_density(t) for t in field.gammas]
        steps.append(
            DerivationStep(
                "D1",
                "Unfolded heights & local mean density (Riemann–von Mangoldt)",
                {
                    "unfolded": unfolded.tolist(),
                    "mean_density_at_gamma": dens,
                    "normalized_spacings": (
                        np.diff(unfolded) / (np.mean(np.diff(unfolded)) + 1e-15)
                    ).tolist()
                    if unfolded.size > 1
                    else [],
                },
            )
        )

        # D2
        action = SpectralAction.from_field(
            field,
            Lambda=self.Lambda,
            omega_scale=self.omega_scale,
            weight_power=self.weight_power,
            tier_split=self.tier_split,
            low_boost=self.low_boost,
            w1_mult=self.w1_mult,
            w2_mult=self.w2_mult,
            w3_mult=self.w3_mult,
        )
        th_grid = np.linspace(0, 2 * np.pi, 361)
        steps.append(
            DerivationStep(
                "D2",
                "Spectral action S_Λ(θ)=Σ w_n(1-cos(ω_n θ)) on U(1) holonomy",
                {
                    "omega": action.omega.tolist(),
                    "weights": action.weights.tolist(),
                    "Lambda": action.cutoff_Lambda,
                    "S_sample": action.S(th_grid).tolist(),
                    "formula": "S(θ)=Σ_n w_n(1-cos(ω_n θ)), ω_n=γ_n/γ_1, w_n∝e^{-γ_n/Λ}",
                },
            )
        )

        # D3
        crit = critical_holonomies(action, max_crit=max(self.n_sectors * 2, 8))
        steps.append(
            DerivationStep(
                "D3",
                "Critical holonomies θ* ∈ Crit(S) — preferred monodromies of the field",
                {"critical": crit, "selection": "prefer S minima as stable geometric sectors"},
            )
        )
        logger.info("D3: %d critical holonomies (%d minima)", len(crit), sum(1 for c in crit if c["kind"] == "minimum"))

        # D4 — diverse Crit(S) keys only (minima first). Never echo-jitter collapse.
        mins = [c for c in crit if c["kind"] == "minimum"]
        rest = [c for c in crit if c["kind"] != "minimum"]
        # Dedup by angular separation (tighter pack so we can seat n_sectors keys)
        min_sep = np.pi / max(3 * self.n_sectors, 3)

        def _take_diverse(cands: list, need: int, taken: list) -> list:
            out = list(taken)
            for c in sorted(cands, key=lambda x: x["S"]):  # deeper wells first among mins
                if len(out) >= need:
                    break
                th = float(c["theta"])
                if any(
                    min(abs(th - float(t["theta"])) % (2 * np.pi), 2 * np.pi - abs(th - float(t["theta"])) % (2 * np.pi))
                    < min_sep
                    for t in out
                ):
                    continue
                out.append(c)
            return out

        pool = _take_diverse(mins, self.n_sectors, [])
        if len(pool) < self.n_sectors:
            pool = _take_diverse(rest, self.n_sectors, pool)
        if len(pool) < self.n_sectors:
            # Fill from uniform samples that are *local* minima of S on a fine grid
            grid = np.linspace(0, 2 * np.pi, 2000, endpoint=False)
            Sv = np.asarray(action.S(grid), dtype=float)
            for i in range(1, len(grid) - 1):
                if len(pool) >= self.n_sectors:
                    break
                if Sv[i] <= Sv[i - 1] and Sv[i] <= Sv[i + 1]:
                    c = {
                        "theta": float(grid[i]),
                        "S": float(Sv[i]),
                        "S_second": float(action.d2S(grid[i])),
                        "kind": "grid_minimum",
                    }
                    pool = _take_diverse([c], self.n_sectors, pool)
        pool = pool[: self.n_sectors]

        sectors: list[InducedSector] = []
        for i, c in enumerate(pool):
            th = float(c["theta"])
            if self.multimode:
                # Longer scaffolds: more Fourier modes (steric mid-length floors)
                if self.N >= 13:
                    n_modes = min(8, int(field.gammas.size))
                elif self.N >= 12:
                    n_modes = min(6, int(field.gammas.size))
                else:
                    n_modes = min(4, int(field.gammas.size))
                pts = embed_multimode_cycle(self.N, th, field, n_modes=n_modes)
            else:
                pts = embed_cycle_from_twist(self.N, th)
            # seed label: nearest γ (bookkeeping only)
            seed = float(field.gammas[min(i, len(field.gammas) - 1)])
            sectors.append(
                InducedSector(
                    id=i + 1,
                    gamma_seed=seed,
                    twist=th,
                    positions=pts,
                    mode_index=i,
                )
            )
        steps.append(
            DerivationStep(
                "D4",
                "Geometric realization: multi-mode C_N ⊂ R³ from each θ*",
                {
                    "n_sectors": len(sectors),
                    "thetas": [s.twist for s in sectors],
                    "multimode": self.multimode,
                    "note": "exact circle closure; height field carries zeta-weighted Fourier modes",
                },
            )
        )

        # D5 — sheaf spectra of derived geometry
        from realm.cohesive import CohesiveHomotopyFunctor

        functor = CohesiveHomotopyFunctor(N=self.N, d=self.d)
        spectra: list[Spectrum] = []
        for sec in sectors:
            A = functor.rotation_monodromy(sec.twist)
            L, eigs, meta = sharp_laplacian(self.N, self.d, A, prefer_maxop=True)
            gap = functor.spectral_gap(eigs)
            Z = functor.partition_function(eigs)
            frust = float(2.0 - 2.0 * np.cos(sec.twist / self.N)) if not np.isclose(sec.twist, 0.0) else 0.0
            spectra.append(
                Spectrum(
                    sector_id=sec.id,
                    twist=sec.twist,
                    eigenvalues=eigs,
                    spectral_gap=gap,
                    lambda_min=float(eigs[0]),
                    frustration_closed_form=frust,
                    partition_function=Z,
                    backend=str(meta.get("backend", "?")),
                    laplacian=L,
                )
            )
        steps.append(
            DerivationStep(
                "D5",
                "Sheaf Laplacian spectra of derived geometries (own spectrum ≠ γ_n)",
                {
                    "gaps": [float(s.spectral_gap) for s in spectra],
                    "backends": [s.backend for s in spectra],
                },
            )
        )

        # D6 — cross-structure: action value vs spectral gap correlation
        S_at = [float(action.S(s.twist)) for s in sectors]
        gaps = np.array([s.spectral_gap for s in spectra], dtype=float)
        if len(S_at) >= 2 and np.std(S_at) > 1e-15 and np.std(gaps) > 1e-15:
            corr = float(np.corrcoef(S_at, gaps)[0, 1])
        else:
            corr = float("nan")
        steps.append(
            DerivationStep(
                "D6",
                "Readout: corr(S(θ*), λ_gap) on derived sectors — structural, not identity",
                {
                    "S_at_sectors": S_at,
                    "spectral_gaps": gaps.tolist(),
                    "corr_S_vs_gap": corr,
                    "ontology": "geometry_derived_off_zeta_spectral_action",
                },
            )
        )
        logger.info("D6: corr(S(θ*), λ_gap)=%.4f", corr)

        return DerivationResult(
            field=field,
            action=action,
            critical=crit,
            sectors=sectors,
            spectra=spectra,
            steps=steps,
            N=self.N,
            d=self.d,
        )


def derive(N: int = 11, **kwargs) -> DerivationResult:
    """One-liner continued derivation."""
    return Deriver(N=N, **kwargs).run()
