"""Cellular sheaf defect tracking — local obstruction before full 3D projection.

Treats a CA ring as a candidate section of the discrete vector bundle on C_N
with cut-edge monodromy A(θ). Local defects are edge coboundary residuals:

  (δx)(e_i) = F_j x_j − F_i x_i

with F = I on ordinary edges and F_0 = A, F_{N-1} = I on the cut.

The Dirichlet energy E = xᵀ L x (L = δ*δ) is the global obstruction cocycle
norm; the edge residual profile is the localized strain inventory.

Used as MaxOp dual diagnostic and optional projection co-score.
Never λ=γ; ζ remains substrate only.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from realm.cohesive import CohesiveHomotopyFunctor
from realm.sheaf_backend import numpy_connection_laplacian, sharp_laplacian


def ca_to_stalk_section(xyz: np.ndarray, d: int = 2) -> np.ndarray:
    """Map CA coords to R^d fiber section via centered PCA (scale-free)."""
    xyz = np.asarray(xyz, dtype=float)
    n = xyz.shape[0]
    c = xyz - xyz.mean(axis=0)
    # PCA basis
    try:
        _, _, vt = np.linalg.svd(c, full_matrices=False)
    except np.linalg.LinAlgError:
        vt = np.eye(3)
    basis = vt[: min(d, 3)].T  # 3 x d'
    sec = c @ basis  # n x d'
    if sec.shape[1] < d:
        pad = np.zeros((n, d - sec.shape[1]))
        sec = np.hstack([sec, pad])
    # unit RMS scale
    scale = float(np.sqrt(np.mean(np.sum(sec**2, axis=1)))) + 1e-15
    return sec / scale


def edge_coboundary_residuals(
    section: np.ndarray,
    monodromy: np.ndarray,
) -> np.ndarray:
    """Per-edge residual norms ||(δx)(e)|| for cycle with cut monodromy A."""
    x = np.asarray(section, dtype=float)
    n, d = x.shape
    A = np.asarray(monodromy, dtype=float)
    I = np.eye(d)
    res = np.zeros(n, dtype=float)
    for i in range(n):
        j = (i + 1) % n
        if i == n - 1:
            # cut: measure x_0 - A x_{N-1}  (matches sheaf_backend convention)
            r = x[j] - A @ x[i]
        else:
            r = x[j] - I @ x[i]
        res[i] = float(np.linalg.norm(r))
    return res


def _path_monodromy(A: np.ndarray, n: int, i: int, hop: int) -> np.ndarray:
    """Parallel transport map along the oriented hop-path i → i+hop (mod n).

    Only the cut edge (n-1 → 0) carries monodromy A; ordinary edges are I.
    Path composition therefore applies A once per cut crossing.
    """
    d = A.shape[0]
    F = np.eye(d)
    for s in range(int(hop)):
        e = (i + s) % n
        if e == n - 1:
            F = A @ F
    return F


def chord_coboundary_residuals(
    section: np.ndarray,
    monodromy: np.ndarray,
    hop: int = 2,
) -> np.ndarray:
    """Multi-residue chord residuals (simplicial 1-skeleton beyond nearest-neighbor).

    For hop=k, residual at vertex i is ||x_{i+k} − F_path x_i|| where F_path
    is the composed connection along the backbone arc. Captures localized
    obstruction on multi-residue peptide spans before full 3D projection.
    """
    x = np.asarray(section, dtype=float)
    n, d = x.shape
    A = np.asarray(monodromy, dtype=float)
    h = int(max(1, hop))
    if h >= n:
        h = n - 1
    res = np.zeros(n, dtype=float)
    for i in range(n):
        j = (i + h) % n
        F = _path_monodromy(A, n, i, h)
        r = x[j] - F @ x[i]
        res[i] = float(np.linalg.norm(r))
    return res


def multi_scale_obstruction(
    section: np.ndarray,
    monodromy: np.ndarray,
    hops: tuple[int, ...] = (1, 2, 3),
) -> dict[str, Any]:
    """Localized obstruction inventory over a simplicial hop filtration."""
    profiles: dict[int, list[float]] = {}
    means: dict[str, float] = {}
    for h in hops:
        if h <= 0:
            continue
        if h == 1:
            r = edge_coboundary_residuals(section, monodromy)
        else:
            r = chord_coboundary_residuals(section, monodromy, hop=h)
        profiles[int(h)] = r.tolist()
        means[f"hop{h}_mean"] = float(np.mean(r))
        means[f"hop{h}_max"] = float(np.max(r))
    # Combined multi-residue strain (edge-primary, chords secondary)
    e1 = means.get("hop1_mean", 0.0)
    e2 = means.get("hop2_mean", 0.0)
    e3 = means.get("hop3_mean", 0.0)
    combined = e1 + 0.35 * e2 + 0.15 * e3
    return {
        "profiles": profiles,
        "means": means,
        "combined_strain": float(combined),
        "hops": list(hops),
    }


def dirichlet_energy(
    section: np.ndarray,
    monodromy: np.ndarray,
    prefer_maxop: bool = True,
) -> tuple[float, np.ndarray, dict[str, Any]]:
    """Global sheaf energy E = xᵀ L x and edge residual profile."""
    x = np.asarray(section, dtype=float)
    n, d = x.shape
    A = np.asarray(monodromy, dtype=float)
    try:
        L, eigs, meta = sharp_laplacian(n, d, A, prefer_maxop=prefer_maxop)
    except Exception:  # noqa: BLE001
        L, eigs = numpy_connection_laplacian(n, d, A)
        meta = {"backend": "numpy.fallback"}
    xv = x.reshape(-1)
    E = float(xv @ L @ xv)
    residuals = edge_coboundary_residuals(x, A)
    multi = multi_scale_obstruction(x, A, hops=(1, 2, 3) if n >= 8 else (1, 2))
    return (
        E,
        residuals,
        {
            **meta,
            "n": n,
            "d": d,
            "spectral_gap": float(eigs[eigs > 1e-10][0]) if np.any(eigs > 1e-10) else 0.0,
            "multi_scale": multi,
        },
    )


def adaptive_chord_weight(n_ca: int, override: float | None = None) -> float:
    """Length-adaptive multi-residue chord weight.

    Short rings (≤11 CA): pure edge Dirichlet (confirmed β=0.20 baseline).
    Mid/long rings (≥12): mild hop-2/3 strain to attack steric floors.
    """
    if override is not None:
        return float(np.clip(override, 0.0, 1.0))
    n = int(n_ca)
    if n >= 13:
        return 0.25
    if n >= 12:
        return 0.12
    return 0.0


def defect_report_for_twist(
    xyz: np.ndarray,
    twist: float,
    *,
    d: int = 2,
    prefer_maxop: bool = True,
    chord_weight: float | None = None,
) -> dict[str, Any]:
    """Local-to-global defect inventory for CA ring under holonomy θ.

    Score combines MaxOp Dirichlet energy with multi-residue chord strain
    (simplicial filtration hops 2–3) on mid-length backbones. Short rings
    keep pure edge Dirichlet to preserve the confirmed ranking baseline.
    """
    n = int(np.asarray(xyz).shape[0])
    fun = CohesiveHomotopyFunctor(N=n, d=d)
    A = fun.rotation_monodromy(float(twist))
    sec = ca_to_stalk_section(xyz, d=d)
    E, residuals, meta = dirichlet_energy(sec, A, prefer_maxop=prefer_maxop)
    multi = meta.get("multi_scale") or multi_scale_obstruction(sec, A)
    cw = adaptive_chord_weight(n, override=chord_weight)
    strain = float(multi.get("combined_strain", float(np.mean(residuals))))
    E_aug = float(E) + cw * float(n) * (strain**2)
    return {
        "twist": float(twist),
        "dirichlet_energy": E,
        "augmented_energy": E_aug,
        "mean_edge_residual": float(np.mean(residuals)),
        "max_edge_residual": float(np.max(residuals)),
        "edge_residuals": residuals.tolist(),
        "cut_edge_residual": float(residuals[-1]),
        "hotspot_index": int(np.argmax(residuals)),
        "multi_scale": multi,
        "chord_weight": cw,
        "backend": meta.get("backend"),
        "operator_gap": meta.get("spectral_gap"),
    }


def softmin_defect_vs_crit(
    xyz: np.ndarray,
    thetas: np.ndarray | list[float],
    *,
    soft_T: float = 0.04,
    d: int = 2,
    prefer_maxop: bool = True,
    chord_weight: float | None = None,
) -> dict[str, Any]:
    """Softmin multi-scale sheaf defect against Crit monodromies.

    Uses augmented energy (Dirichlet + adaptive multi-residue chords).
    Projection-primary ranking may blend this with Kabsch; alone it is the
    local-to-global obstruction score (sheaf defect track / AQFT local strain).
    """
    th = np.asarray(thetas, dtype=float).ravel()
    if th.size == 0:
        return {"mean_dist": 1e9, "method": "SHEAF_DEFECT_SOFTMIN", "energies": []}
    n = int(np.asarray(xyz).shape[0])
    cw = adaptive_chord_weight(n, override=chord_weight)
    energies = []
    profiles = []
    for t in th:
        rep = defect_report_for_twist(
            xyz,
            float(t),
            d=d,
            prefer_maxop=prefer_maxop,
            chord_weight=cw,
        )
        energies.append(rep["augmented_energy"])
        profiles.append(rep)
    e = np.asarray(energies, dtype=float)
    # energies can be large; softmin on sqrt energy for scale
    s = np.sqrt(np.clip(e, 0.0, None))
    m = float(np.min(s))
    T = max(float(soft_T), 1e-12)
    w = np.exp(-(s - m) / T)
    soft = float(np.sum(w * s) / (np.sum(w) + 1e-15))
    method = "SHEAF_DEFECT_MULTISCALE" if cw > 1e-12 else "SHEAF_DEFECT_SOFTMIN"
    return {
        "mean_dist": soft,
        "min_dist": m,
        "method": method,
        "energies": energies,
        "best_twist": float(th[int(np.argmin(s))]),
        "profiles": profiles,
        "soft_T": T,
        "chord_weight": float(cw),
    }


def blend_projection_defect(
    proj_dist: float,
    defect_dist: float,
    *,
    beta: float = 0.08,
) -> float:
    """Projection-primary blend: (1-β)·Kabsch + β·sheaf-defect softmin."""
    b = float(np.clip(beta, 0.0, 1.0))
    # scale defect into Kabsch range (~0.3–0.6)
    d_scaled = float(defect_dist) * 0.15
    return (1.0 - b) * float(proj_dist) + b * d_scaled
