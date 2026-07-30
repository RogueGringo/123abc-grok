"""Prime folding engine: Coutsias loop closure → MaxOp sheaf L → spectral action.

Pipeline
--------
  1. Coutsias multi-start kinematic roots (6-DOF free torsions) → closed CA rings
  2. SO(2) twist monodromy from discrete Frenet/Bishop holonomy
  3. Cellular sheaf connection Laplacian L = δ*δ (MaxOp or numpy)
  4. Spectral action on *geometry's* spectrum:
         S_L(s) = Σ_{λ_i > 0} λ_i^{-s}
     (coordinate-free stability proxy — NOT λ = γ_n Riemann zeros)
  5. Euclidean recovery: Coutsias frame-step positions (NeRF-style) + soft close

Ontology (realm.ontology)
-------------------------
  ζ may seed Crit molds elsewhere; this loop scores *induced* L spectra only.
  Never λ=γ. Never residual seating as ζ preference.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from realm.cohesive import CohesiveHomotopyFunctor
from realm.coutsias import ClosedGeometry, CoutsiasKinematics
from realm.ontology import ontology_note
from realm.sheaf_backend import sharp_laplacian
from realm.sheaf_defects import ca_to_stalk_section, dirichlet_energy

logger = logging.getLogger(__name__)


def spectral_zeta_action(
    eigenvalues: np.ndarray | list[float],
    *,
    s: float = 2.0,
    eps: float = 1e-6,
) -> float:
    """Spectral zeta of a positive operator: Σ λ^{-s} over λ > eps.

    Lower action ≈ more stable / less frustrated connection spectrum.
    This is spectral geometry of L_F, not the Riemann zeta function itself.
    """
    e = np.asarray(eigenvalues, dtype=float).ravel()
    pos = e[e > float(eps)]
    if pos.size == 0:
        return float("inf")
    s = float(s)
    return float(np.sum(np.power(pos, -s)))


def score_closed_geometry(
    geo: ClosedGeometry,
    *,
    N: int,
    d: int = 2,
    s: float = 2.0,
    prefer_maxop: bool = True,
    residual_weight: float = 0.35,
    dirichlet_weight: float = 0.15,
) -> dict[str, Any]:
    """Score one Coutsias sector via MaxOp/numpy L spectrum + kinematics residual.

    Combined energy (lower better):
      E = S_L(s) + w_r · residual + w_D · (normalized Dirichlet of CA section)
    """
    fun = CohesiveHomotopyFunctor(N=int(N), d=int(d))
    A = fun.rotation_monodromy(float(geo.twist_so2))
    L, eigs, meta = sharp_laplacian(int(N), int(d), A, prefer_maxop=prefer_maxop)
    action = spectral_zeta_action(eigs, s=s)

    # Optional sheaf section energy of the embedded ring (scale-free PCA stalks)
    D_energy = 0.0
    try:
        sec = ca_to_stalk_section(geo.positions, d=d)
        # Resize section if N atoms != N scaffold
        if sec.shape[0] != N:
            # resample ring to N
            from realm.validate.decoys import _resample_ring

            pts = _resample_ring(geo.positions, N)
            sec = ca_to_stalk_section(pts, d=d)
        D_energy, _, _ = dirichlet_energy(sec, A, prefer_maxop=prefer_maxop)
    except Exception:  # noqa: BLE001
        D_energy = 0.0

    # Normalize Dirichlet into O(1) vs residual
    D_n = float(D_energy) / max(float(N), 1.0)
    total = (
        float(action)
        + float(residual_weight) * float(geo.residual)
        + float(dirichlet_weight) * D_n
    )
    gap = float(eigs[eigs > 1e-8][0]) if np.any(eigs > 1e-8) else 0.0
    return {
        "total": total,
        "spectral_action": action,
        "residual": float(geo.residual),
        "dirichlet": float(D_energy),
        "dirichlet_norm": D_n,
        "spectral_gap": gap,
        "twist_so2": float(geo.twist_so2),
        "root_t": float(geo.root_t),
        "backend": meta.get("backend"),
        "n_eigs": int(eigs.size),
        "s": float(s),
        "ontology": "spectral_action_of_L_not_lambda_eq_gamma",
    }


@dataclass
class PrimeFoldResult:
    """Ground-state isolation report + Cartesian embed."""

    N: int
    ground_state: ClosedGeometry
    score: dict[str, Any]
    candidates: list[dict[str, Any]] = field(default_factory=list)
    coordinates: np.ndarray | None = None
    status: str = "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "N": self.N,
            "ontology_note": ontology_note(),
            "ground_state": self.ground_state.to_dict(),
            "score": self.score,
            "n_candidates": len(self.candidates),
            "candidates": self.candidates[:12],
            "coordinates": None
            if self.coordinates is None
            else np.asarray(self.coordinates, float).tolist(),
            "pipeline": (
                "Coutsias roots → SO(2) monodromy → MaxOp L=δ*δ → "
                "spectral zeta action S_L(s) → NeRF/frame embed"
            ),
            "never": ["lambda_eq_gamma"],
        }


class PrimeFoldingEngine:
    """Coutsias kinematic multi-start + sheaf spectral ground-state isolation.

    Parameters
    ----------
    N : cycle length (CA atoms / residues)
    s : spectral zeta order (default 2 → Tr L^{-2} style)
    prefer_maxop : use MaxOp CellularSheaf when available
    """

    def __init__(
        self,
        N: int = 11,
        *,
        d: int = 2,
        s: float = 2.0,
        prefer_maxop: bool = True,
        residual_tol: float = 0.45,
        n_starts: int = 32,
        use_de: bool = True,
        rng_seed: int = 11,
        residual_weight: float = 0.35,
        dirichlet_weight: float = 0.15,
    ):
        self.N = int(N)
        self.d = int(d)
        self.s = float(s)
        self.prefer_maxop = bool(prefer_maxop)
        self.residual_weight = float(residual_weight)
        self.dirichlet_weight = float(dirichlet_weight)
        self.kin = CoutsiasKinematics(
            N=self.N,
            residual_tol=residual_tol,
            n_starts=n_starts,
            use_de=use_de,
            rng_seed=rng_seed,
        )

    def generate_closures(self, max_roots: int = 8) -> list[ClosedGeometry]:
        """Multi-start Coutsias loop closure → discrete near-closed sectors."""
        geoms = self.kin.find_real_roots()
        return list(geoms[: max(1, int(max_roots))])

    def score_conformation(self, geo: ClosedGeometry) -> dict[str, Any]:
        return score_closed_geometry(
            geo,
            N=self.N,
            d=self.d,
            s=self.s,
            prefer_maxop=self.prefer_maxop,
            residual_weight=self.residual_weight,
            dirichlet_weight=self.dirichlet_weight,
        )

    def embed_to_3d(self, geo: ClosedGeometry) -> np.ndarray:
        """NeRF/Bishop-style Cartesian recovery from Coutsias closed geometry.

        Positions already come from discrete frame stepping + soft loop close
        (see realm.coutsias._frame_step / soft_close_positions).
        """
        P = np.asarray(geo.positions, dtype=float)
        if P.ndim != 2 or P.shape[1] < 3:
            raise ValueError("geometry positions must be (n,3)")
        P = P[:, :3].copy()
        P -= P.mean(axis=0)
        return P

    def execute_folding(
        self,
        *,
        max_roots: int = 8,
        max_iterations: int | None = None,
    ) -> PrimeFoldResult:
        """Main loop: roots → sheaf L → spectral action → ground state embed.

        max_iterations is accepted for API parity with external sketches; when
        set, it overrides Coutsias n_starts for this call only.
        """
        if max_iterations is not None and int(max_iterations) > 0:
            self.kin.n_starts = int(max_iterations)

        logger.info(
            "PrimeFold N=%d s=%.2f starts=%d prefer_maxop=%s",
            self.N,
            self.s,
            self.kin.n_starts,
            self.prefer_maxop,
        )
        geoms = self.generate_closures(max_roots=max_roots)
        if not geoms:
            raise RuntimeError("Coutsias produced no closed geometries")

        scored: list[tuple[ClosedGeometry, dict[str, Any]]] = []
        for i, g in enumerate(geoms):
            sc = self.score_conformation(g)
            scored.append((g, sc))
            logger.info(
                "  conf[%d] total=%.4f S_L=%.4f res=%.4f gap=%.4f twist=%+.3f backend=%s",
                i,
                sc["total"],
                sc["spectral_action"],
                sc["residual"],
                sc["spectral_gap"],
                sc["twist_so2"],
                sc.get("backend"),
            )

        scored.sort(key=lambda t: t[1]["total"])
        best_g, best_sc = scored[0]
        coords = self.embed_to_3d(best_g)

        cands = []
        for g, sc in scored:
            cands.append(
                {
                    "total": sc["total"],
                    "spectral_action": sc["spectral_action"],
                    "residual": sc["residual"],
                    "spectral_gap": sc["spectral_gap"],
                    "twist_so2": sc["twist_so2"],
                    "root_t": sc["root_t"],
                    "backend": sc.get("backend"),
                }
            )

        return PrimeFoldResult(
            N=self.N,
            ground_state=best_g,
            score=best_sc,
            candidates=cands,
            coordinates=coords,
            status="success",
        )


def fold_sequence_length(
    n_residues: int,
    **kwargs: Any,
) -> PrimeFoldResult:
    """Convenience: fold an n-mer cyclic backbone (no sequence chemistry yet)."""
    return PrimeFoldingEngine(N=int(n_residues), **kwargs).execute_folding()


# ---------------------------------------------------------------------------
# Ranking bridge: Coutsias mold bank → Kabsch softmin (projection dual)
# ---------------------------------------------------------------------------

_COUTSIAS_BANK_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}


def forge_coutsias_mold_bank(
    N: int,
    *,
    max_roots: int = 6,
    n_starts: int = 14,
    use_de: bool = False,
    prefer_maxop: bool = False,
    s: float = 2.0,
    rng_seed: int = 11,
    residual_tol: float = 0.55,
    cache: bool = True,
) -> dict[str, Any]:
    """Build a structure-free Coutsias mold bank scored by spectral action.

    Templates are soft-closed CA rings from multi-start loop closure.
    Softmin weights favor low S_L + residual (stable sheaf spectra).
    Cached by (N, starts, roots, seed) for ranking batch reuse.
    """
    key = (int(N), int(max_roots), int(n_starts), bool(use_de), int(rng_seed), float(s))
    if cache and key in _COUTSIAS_BANK_CACHE:
        return _COUTSIAS_BANK_CACHE[key]

    eng = PrimeFoldingEngine(
        N=int(N),
        s=float(s),
        prefer_maxop=prefer_maxop,
        n_starts=int(n_starts),
        use_de=bool(use_de),
        rng_seed=int(rng_seed),
        residual_tol=float(residual_tol),
    )
    geoms = eng.generate_closures(max_roots=max_roots)
    templates: list[np.ndarray] = []
    scores: list[float] = []
    twists: list[float] = []
    residuals: list[float] = []
    for g in geoms:
        sc = eng.score_conformation(g)
        templates.append(np.asarray(g.positions, dtype=float)[:, :3])
        scores.append(float(sc["total"]))
        twists.append(float(g.twist_so2))
        residuals.append(float(g.residual))

    sc_arr = np.asarray(scores, dtype=float)
    if sc_arr.size == 0:
        bank = {
            "templates": [],
            "weights": np.zeros(0),
            "scores": sc_arr,
            "twists": [],
            "residuals": [],
            "N": int(N),
            "empty": True,
        }
    else:
        m = float(np.min(sc_arr))
        scale = 0.5 * float(np.std(sc_arr)) + 0.15
        w = np.exp(-(sc_arr - m) / scale)
        w = w / (float(np.mean(w)) + 1e-15)
        bank = {
            "templates": templates,
            "weights": w,
            "scores": sc_arr,
            "twists": twists,
            "residuals": residuals,
            "N": int(N),
            "empty": False,
            "n_bank": len(templates),
            "best_total": m,
            "ontology": "coutsias_molds_spectral_action_not_lambda_eq_gamma",
        }
    if cache:
        _COUTSIAS_BANK_CACHE[key] = bank
    return bank


def score_geometry_vs_coutsias(
    xyz: np.ndarray,
    bank: dict[str, Any] | None = None,
    *,
    N: int | None = None,
    soft_T: float = 0.04,
    **bank_kw: Any,
) -> dict[str, Any]:
    """Kabsch softmin of CA ring vs Coutsias spectral-action mold bank."""
    from realm.validate.decoys import score_geometry_vs_crit

    if bank is None:
        if N is None:
            N = int(np.asarray(xyz).shape[0])
        bank = forge_coutsias_mold_bank(int(N), **bank_kw)
    if bank.get("empty") or not bank.get("templates"):
        return {
            "mean_dist": 1e9,
            "min_dist": 1e9,
            "method": "COUTSIAS_EMPTY",
            "n_templates": 0,
        }
    out = score_geometry_vs_crit(
        xyz,
        bank["templates"],
        soft_T=soft_T,
        aggregate="softmin_persist",
        sector_weights=bank.get("weights"),
    )
    out["method"] = "COUTSIAS_KABSCH_SOFTMIN"
    out["coutsias_n_bank"] = bank.get("n_bank")
    out["coutsias_best_total"] = bank.get("best_total")
    return out


def blend_crit_coutsias_dist(
    crit_dist: float,
    coutsias_dist: float,
    *,
    alpha: float = 0.10,
) -> float:
    """Projection blend: (1-α)·Crit + α·Coutsias Kabsch (lower better)."""
    a = float(np.clip(alpha, 0.0, 1.0))
    return (1.0 - a) * float(crit_dist) + a * float(coutsias_dist)
