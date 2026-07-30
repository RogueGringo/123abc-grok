"""Dual instrument: baseline operation matrix L vs geometric projection.

Ontology
--------
* Substrate  — zeta field (or control seed) → SpectralAction → Crit θ*
* Operation  — connection Laplacian L(A(θ)) at those holonomies (MaxOp / numpy)
* Projection — Crit-induced multimode geometry in R³ (CA mold / Kabsch)

Never scores λ ≈ γ. Dual score pairs projection distance with operator
fingerprint distance so evidence lives on the dual, not lock–key seating.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from realm.cohesive import CohesiveHomotopyFunctor
from realm.lock_key import Keymaker
from realm.validate.decoys import score_geometry_vs_crit, theta_proxy_from_ca


@dataclass
class OperatorFingerprint:
    thetas: np.ndarray
    gaps: np.ndarray
    frustrations: np.ndarray
    logZ: np.ndarray
    mean_gap: float
    gap_cv: float
    mean_frustration: float
    mean_logZ: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "thetas": self.thetas.tolist(),
            "gaps": self.gaps.tolist(),
            "frustrations": self.frustrations.tolist(),
            "logZ": self.logZ.tolist(),
            "mean_gap": self.mean_gap,
            "gap_cv": self.gap_cv,
            "mean_frustration": self.mean_frustration,
            "mean_logZ": self.mean_logZ,
        }

    def feature_matrix(self) -> np.ndarray:
        """Per-sector features for nearest-neighbor dual distance."""
        # scale-free-ish columns
        g = self.gaps
        f = self.frustrations
        z = self.logZ
        g_n = g / (np.mean(g) + 1e-15)
        f_n = f / (np.mean(np.abs(f)) + 1e-15)
        z_n = z - np.mean(z)
        return np.column_stack([g_n, f_n, z_n])


def operator_fingerprint(
    thetas: np.ndarray | list[float],
    N: int,
    d: int = 2,
    prefer_maxop: bool = True,
) -> OperatorFingerprint:
    """Evaluate L(A(θ)) at each Crit holonomy — baseline operation matrix side."""
    th = np.asarray(thetas, dtype=float).ravel()
    fun = CohesiveHomotopyFunctor(N=int(N), d=int(d))
    gaps, frust, logz = [], [], []
    for i, t in enumerate(th):
        st = fun.evaluate_state_from_twist(
            i + 1, float(t), float(t), prefer_maxop=prefer_maxop
        )
        gaps.append(float(st.spectral_gap))
        frust.append(float(st.frustration_closed_form))
        logz.append(float(np.log(max(st.partition_function, 1e-300))))
    g = np.asarray(gaps, float)
    f = np.asarray(frust, float)
    z = np.asarray(logz, float)
    mean_g = float(np.mean(g)) if g.size else 0.0
    cv = float(np.std(g) / (mean_g + 1e-15)) if g.size else 0.0
    return OperatorFingerprint(
        thetas=th.copy(),
        gaps=g,
        frustrations=f,
        logZ=z,
        mean_gap=mean_g,
        gap_cv=cv,
        mean_frustration=float(np.mean(f)) if f.size else 0.0,
        mean_logZ=float(np.mean(z)) if z.size else 0.0,
    )


def operator_point_at_theta(
    theta: float,
    N: int,
    d: int = 2,
    prefer_maxop: bool = True,
) -> np.ndarray:
    """Single-holonomy operator feature vector (gap_n, frust_n, logZ_c)."""
    fp = operator_fingerprint([theta], N=N, d=d, prefer_maxop=prefer_maxop)
    # raw then mild normalize locally
    g, f, z = float(fp.gaps[0]), float(fp.frustrations[0]), float(fp.logZ[0])
    return np.array([g, f, z], dtype=float)


def operator_distance_to_crit(
    xyz: np.ndarray,
    crit_fp: OperatorFingerprint,
    N: int,
    prefer_maxop: bool = True,
) -> dict[str, float]:
    """Projection-side holonomy proxy → L fingerprint vs nearest Crit sector.

    θ_geom from CA ring (FALLBACK_THETA_PROXY). Distance in feature space
    to nearest Crit operator point (after column z-score of Crit matrix).
    """
    th = float(theta_proxy_from_ca(xyz))
    pt = operator_point_at_theta(th, N=N, prefer_maxop=prefer_maxop)
    M = crit_fp.feature_matrix()
    if M.size == 0:
        return {"op_dist": 1e9, "theta_geom": th, "method": "OP_CRIT_NN"}
    # column scale from Crit ensemble
    mu = M.mean(axis=0)
    sig = M.std(axis=0) + 1e-15
    # raw pt needs same feature recipe as feature_matrix
    g_n = pt[0] / (crit_fp.mean_gap + 1e-15)
    f_n = pt[1] / (abs(crit_fp.mean_frustration) + 1e-15)
    z_n = pt[2] - crit_fp.mean_logZ
    p = np.array([g_n, f_n, z_n], dtype=float)
    Mn = (M - mu) / sig
    pn = (p - mu) / sig
    d = np.linalg.norm(Mn - pn[None, :], axis=1)
    return {
        "op_dist": float(np.min(d)),
        "theta_geom": th,
        "method": "OP_CRIT_NN",
    }


def multimode_for_ca_length(n_ca: int, mode: str = "adaptive_short") -> bool:
    """Whether Crit rings use Fourier multimode height field.

    adaptive_short: multimode only for short rings (CA≤8) — height ribbon
    helps tiny cyclics; planar holonomy circle ranks better for longer rings.
    on / off: force all multimode or all planar.
    self_fit: not length-based — caller must pick via native Crit distance.
    """
    mode = str(mode or "adaptive_short").lower().strip()
    if mode in ("on", "true", "1", "yes"):
        return True
    if mode in ("off", "false", "0", "no", "planar"):
        return False
    if mode in ("self_fit", "self-fit", "fit"):
        # length heuristic only as fallback; prefer select_multimode_by_fit
        return int(n_ca) <= 8
    # adaptive_short (default production)
    return int(n_ca) <= 8


def select_multimode_by_fit(
    xyz: np.ndarray,
    knobs: dict[str, Any],
    *,
    N: int,
    n_zeros: int,
    n_sectors: int,
    soft_T: float = 0.04,
    prefer_maxop: bool = True,
) -> tuple[bool, dict[str, Any], dict[str, Any]]:
    """Pick planar vs multimode Crit mold by native projection distance.

    Structure-conditioned mold choice (not decoy-label training): forge both,
    keep the ensemble with lower softmin Kabsch distance to the native CA.
    Returns (use_multimode, pack, diagnostics).
    """
    from realm.validate.decoys import score_geometry_vs_crit

    pack_p = forge_crit_geometry(
        knobs,
        N=N,
        n_zeros=n_zeros,
        n_sectors=n_sectors,
        multimode=False,
        prefer_maxop=prefer_maxop,
    )
    pack_m = forge_crit_geometry(
        knobs,
        N=N,
        n_zeros=n_zeros,
        n_sectors=n_sectors,
        multimode=True,
        prefer_maxop=prefer_maxop,
    )
    d_p = float(
        score_geometry_vs_crit(xyz, pack_p["templates"], soft_T=soft_T)["mean_dist"]
    )
    d_m = float(
        score_geometry_vs_crit(xyz, pack_m["templates"], soft_T=soft_T)["mean_dist"]
    )
    use_m = d_m < d_p - 1e-12
    pack = pack_m if use_m else pack_p
    diag = {
        "dist_planar": d_p,
        "dist_multimode": d_m,
        "chosen": "multimode" if use_m else "planar",
        "margin": float(d_p - d_m),
    }
    return use_m, pack, diag


def sectors_for_ca_length(n_ca: int, mode: str = "fixed", default: int = 6) -> int:
    """Choose Crit sector count from ring length (projection mold capacity).

    adaptive (default production): short rings use fewer valleys so softmin
    is not diluted by grid-filled surplus sectors.
      n_ca ≤ 8 → 4,  else → 6
    (Long rings previously tried 8 valleys; full-batch 40×3 preferred cap-6.)
    fixed: always ``default``
    """
    mode = str(mode or "fixed").lower().strip()
    if mode == "adaptive":
        n = int(n_ca)
        if n <= 8:
            return 4
        return 6
    return max(2, int(default))


def forge_crit_geometry(
    knobs: dict[str, Any],
    *,
    N: int,
    n_zeros: int = 14,
    n_sectors: int = 6,
    gammas: np.ndarray | None = None,
    prefer_maxop: bool = True,
    multimode: bool | None = None,
) -> dict[str, Any]:
    """Forge substrate → Crit templates + operator fingerprint."""
    kn = dict(knobs)
    if gammas is not None:
        kn["gammas"] = np.asarray(gammas, float).ravel()
    if multimode is not None:
        kn["multimode"] = bool(multimode)
    der = Keymaker(N=N, n_zeros=n_zeros, n_sectors=n_sectors).forge(**kn)
    templates: list[np.ndarray] = []
    thetas: list[float] = []
    for s in der.sectors:
        thetas.append(float(s.twist))
        pts = getattr(s, "positions", None)
        if pts is not None:
            arr = np.asarray(pts, dtype=float)
            if arr.ndim == 2 and arr.shape[1] >= 3:
                templates.append(arr[:, :3])
    fp = operator_fingerprint(thetas, N=N, prefer_maxop=prefer_maxop)
    return {
        "templates": templates,
        "thetas": np.asarray(thetas, float),
        "operator": fp,
        "derivation": der,
        "n_sectors": len(templates),
        "N": N,
        "multimode": bool(kn.get("multimode", True)),
    }


def dual_score_geometry(
    xyz: np.ndarray,
    pack: dict[str, Any],
    *,
    alpha_proj: float = 0.85,
    prefer_maxop: bool = True,
    soft_T: float = 0.04,
    aggregate: str = "softmin",
) -> dict[str, Any]:
    """Joint score: α·projection + (1-α)·operator distance (lower better).

    Projection = Crit Kabsch ensemble (softmin / blend). Operator = NN
    distance in L-feature space at θ_geom vs Crit. α=1 pure projection.
    """
    templates = pack["templates"]
    crit_fp: OperatorFingerprint = pack["operator"]
    N = int(pack["N"])
    proj = score_geometry_vs_crit(
        xyz, templates, soft_T=soft_T, aggregate=aggregate
    )
    a = float(np.clip(alpha_proj, 0.0, 1.0))
    # skip expensive L eval when pure projection ranking
    if a >= 1.0 - 1e-12:
        return {
            "mean_dist": float(proj["mean_dist"]),
            "proj_dist": float(proj["mean_dist"]),
            "op_dist": 0.0,
            "op_dist_scaled": 0.0,
            "theta_geom": None,
            "alpha_proj": a,
            "method": proj.get("method"),
            "in_basin": bool(proj.get("in_basin")),
            "n_templates": proj.get("n_templates"),
            "top_k": proj.get("top_k"),
            "min_dist": proj.get("min_dist"),
            "soft_T": proj.get("soft_T"),
            "aggregate": proj.get("aggregate"),
        }
    op = operator_distance_to_crit(
        xyz, crit_fp, N=N, prefer_maxop=prefer_maxop
    )
    # soft scale op into projection Kabsch range
    op_s = float(op["op_dist"]) * 0.25
    dual = a * float(proj["mean_dist"]) + (1.0 - a) * op_s
    return {
        "mean_dist": dual,
        "proj_dist": float(proj["mean_dist"]),
        "op_dist": float(op["op_dist"]),
        "op_dist_scaled": op_s,
        "theta_geom": op["theta_geom"],
        "alpha_proj": a,
        "method": "DUAL_PROJ_OP",
        "in_basin": bool(proj.get("in_basin")),
        "n_templates": proj.get("n_templates"),
        "top_k": proj.get("top_k"),
        "min_dist": proj.get("min_dist"),
        "soft_T": proj.get("soft_T"),
        "aggregate": proj.get("aggregate"),
    }
