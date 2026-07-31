"""CA decoys + mold ranking helpers (FALLBACK_THETA_PROXY for v1)."""

from __future__ import annotations

from typing import Any

import numpy as np

from realm.lock_key import _circular_dist
from realm.projection import ModuliLandscape


def closure_residual(xyz: np.ndarray) -> float:
    xyz = np.asarray(xyz, dtype=float)
    if xyz.shape[0] < 2:
        return 0.0
    return float(np.linalg.norm(xyz[0] - xyz[-1]))


def make_ca_decoys(
    xyz: np.ndarray,
    n: int,
    rng: np.random.Generator,
    noise: float = 0.5,
    max_closure: float = 8.0,
) -> list[np.ndarray]:
    """Jitter CA coords; reject if ring ends far apart."""
    xyz = np.asarray(xyz, dtype=float)
    out: list[np.ndarray] = []
    attempts = 0
    while len(out) < n and attempts < n * 20:
        attempts += 1
        jitter = xyz + rng.normal(0.0, noise, size=xyz.shape)
        # re-center
        jitter = jitter - jitter.mean(axis=0)
        if closure_residual(jitter) <= max_closure:
            out.append(jitter)
    # pad with noisier samples if needed
    while len(out) < n:
        jitter = xyz + rng.normal(0.0, noise * 1.5, size=xyz.shape)
        jitter = jitter - jitter.mean(axis=0)
        out.append(jitter)
    return out


def _center(xyz: np.ndarray) -> np.ndarray:
    a = np.asarray(xyz, dtype=float)
    return a - a.mean(axis=0)


def make_ca_decoy_reverse(xyz: np.ndarray) -> np.ndarray:
    """Orientation-reversed closed ring (still closed)."""
    return _center(np.asarray(xyz, dtype=float)[::-1].copy())


def make_ca_decoy_roll(xyz: np.ndarray, shift: int) -> np.ndarray:
    """Cyclic index roll — same coords, re-indexed along the ring."""
    a = np.asarray(xyz, dtype=float)
    n = int(a.shape[0])
    if n < 3:
        return _center(a)
    s = int(shift) % n
    return _center(np.roll(a, s, axis=0))


def make_ca_decoy_block_permute(
    xyz: np.ndarray,
    rng: np.random.Generator,
    n_blocks: int = 3,
) -> np.ndarray:
    """Permute contiguous blocks along the ring (harder near-native adversary)."""
    a = np.asarray(xyz, dtype=float)
    n = int(a.shape[0])
    if n < 6:
        return make_ca_decoy_roll(a, int(rng.integers(1, max(n, 2))))
    nb = max(2, min(int(n_blocks), n // 2))
    cuts = sorted(rng.choice(n, size=nb - 1, replace=False).tolist())
    edges = [0] + cuts + [n]
    blocks = [a[edges[i] : edges[i + 1]] for i in range(len(edges) - 1)]
    order = rng.permutation(len(blocks))
    out = np.vstack([blocks[i] for i in order])
    return _center(out)


def make_ca_decoy_segment_twist(
    xyz: np.ndarray,
    rng: np.random.Generator,
    angle_scale: float = 0.8,
) -> np.ndarray:
    """Rotate a contiguous segment about the chord between its endpoints."""
    a = np.asarray(xyz, dtype=float).copy()
    n = int(a.shape[0])
    if n < 6:
        return make_ca_decoys(a, 1, rng, noise=0.6)[0]
    i0 = int(rng.integers(0, n))
    span = int(rng.integers(max(2, n // 5), max(3, n // 2)))
    idx = [(i0 + k) % n for k in range(span)]
    p0, p1 = a[idx[0]], a[idx[-1]]
    axis = p1 - p0
    norm = float(np.linalg.norm(axis))
    if norm < 1e-8:
        return make_ca_decoys(a, 1, rng, noise=0.5)[0]
    axis = axis / norm
    ang = float(rng.normal(0.0, angle_scale))
    # Rodrigues
    K = np.array(
        [
            [0.0, -axis[2], axis[1]],
            [axis[2], 0.0, -axis[0]],
            [-axis[1], axis[0], 0.0],
        ],
        dtype=float,
    )
    R = np.eye(3) + np.sin(ang) * K + (1.0 - np.cos(ang)) * (K @ K)
    for j in idx[1:-1]:
        a[j] = p0 + R @ (a[j] - p0)
    return _center(a)


def make_decoy_bank(
    xyz: np.ndarray,
    n: int,
    rng: np.random.Generator,
    *,
    mode: str = "soft",
    noise: float = 0.45,
    max_closure: float = 8.0,
) -> list[np.ndarray]:
    """Build n decoys under a difficulty mode (closed-ring preferring).

    mode
      soft   — production default: half soft jitter + half harder jitter
      mixed  — soft + reverse/roll/block/twist structured set
      hard   — structured-heavy (minimal pure jitter)
    """
    xyz = np.asarray(xyz, dtype=float)
    n = max(0, int(n))
    if n == 0:
        return []
    m = str(mode or "soft").lower().strip()
    out: list[np.ndarray] = []

    if m in ("soft", "jitter", "default", ""):
        n_soft = max(n // 2, 1) if n > 1 else n
        n_hard = n - n_soft
        out.extend(make_ca_decoys(xyz, n_soft, rng, noise=noise, max_closure=max_closure))
        if n_hard > 0:
            out.extend(
                make_ca_decoys(
                    xyz, n_hard, rng, noise=noise * 1.8, max_closure=max_closure
                )
            )
        return out[:n]

    # structured generators
    structured_builders = [
        lambda: make_ca_decoy_reverse(xyz),
        lambda: make_ca_decoy_roll(xyz, int(rng.integers(1, max(xyz.shape[0], 2)))),
        lambda: make_ca_decoy_block_permute(xyz, rng),
        lambda: make_ca_decoy_segment_twist(xyz, rng),
    ]

    if m in ("hard", "structured"):
        n_struct = max(int(round(0.75 * n)), 1)
        n_jit = n - n_struct
    else:  # mixed
        n_struct = max(int(round(0.5 * n)), 1)
        n_jit = n - n_struct

    attempts = 0
    while len(out) < n_struct and attempts < n_struct * 30:
        attempts += 1
        builder = structured_builders[int(rng.integers(0, len(structured_builders)))]
        try:
            d = builder()
        except Exception:  # noqa: BLE001
            continue
        if d.shape != xyz.shape:
            continue
        if closure_residual(d) <= max_closure * 1.5:
            out.append(d)
        elif len(out) < n_struct // 2:
            # keep a few even if slightly open (harder class)
            out.append(_center(d))

    if n_jit > 0:
        out.extend(
            make_ca_decoys(
                xyz, n_jit, rng, noise=noise * (1.5 if m == "hard" else 1.0), max_closure=max_closure
            )
        )

    # pad
    while len(out) < n:
        out.extend(make_ca_decoys(xyz, 1, rng, noise=noise * 2.0, max_closure=max_closure))
    return out[:n]


def theta_proxy_from_ca(xyz: np.ndarray) -> float:
    """Map ring shape to [0, 2π) via principal-plane polar angle of centroid chords.

    Labeled FALLBACK_THETA_PROXY in reports — not full holonomy reconstruction.
    """
    xyz = np.asarray(xyz, dtype=float)
    c = xyz.mean(axis=0)
    v = xyz - c
    # PCA plane
    _, _, vt = np.linalg.svd(v, full_matrices=False)
    plane = v @ vt[:2].T
    ang = np.arctan2(plane[:, 1], plane[:, 0])
    # mean resultant angle
    m = np.mean(np.exp(1j * ang))
    th = float(np.angle(m) % (2 * np.pi))
    return th


def score_geometry_on_mold(
    xyz: np.ndarray,
    landscape: ModuliLandscape,
    basin: float | None = None,
) -> dict[str, Any]:
    th = theta_proxy_from_ca(xyz)
    valleys = landscape.valleys or []
    if not valleys:
        return {
            "theta_proxy": th,
            "mean_dist": float(np.pi),
            "in_basin": False,
            "method": "FALLBACK_THETA_PROXY",
        }
    dists = [_circular_dist(th, float(v["theta"])) for v in valleys]
    dmin = float(min(dists))
    if basin is None:
        # reuse occupancy test scale if present
        basin = float(np.pi / len(valleys))
    return {
        "theta_proxy": th,
        "mean_dist": dmin,
        "in_basin": dmin <= basin,
        "method": "FALLBACK_THETA_PROXY",
        "basin": basin,
    }


def _kabsch_rmsd_fixed(P: np.ndarray, Q: np.ndarray) -> float:
    """RMSD after optimal rotation (Kabsch); same length, already scaled/centered optional."""
    P = np.asarray(P, float)
    Q = np.asarray(Q, float)
    if P.shape[0] < 3 or P.shape != Q.shape:
        return 1e9
    P = P - P.mean(axis=0)
    Q = Q - Q.mean(axis=0)
    sp = np.sqrt(np.mean(np.sum(P**2, axis=1))) + 1e-15
    sq = np.sqrt(np.mean(np.sum(Q**2, axis=1))) + 1e-15
    P, Q = P / sp, Q / sq
    H = P.T @ Q
    U, _, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt = Vt.copy()
        Vt[-1, :] *= -1
        R = Vt.T @ U.T
    P_aligned = P @ R
    return float(np.sqrt(np.mean(np.sum((P_aligned - Q) ** 2, axis=1))))


def _resample_ring(xyz: np.ndarray, n: int) -> np.ndarray:
    """Resample closed CA ring to n vertices along index (cyclic lerp)."""
    xyz = np.asarray(xyz, float)
    if xyz.shape[0] == n:
        return xyz.copy()
    # close the loop for interpolation
    closed = np.vstack([xyz, xyz[0]])
    t_src = np.linspace(0.0, 1.0, closed.shape[0])
    t_dst = np.linspace(0.0, 1.0, n, endpoint=False)
    out = np.column_stack([np.interp(t_dst, t_src, closed[:, i]) for i in range(3)])
    return out


def _kabsch_rmsd(P: np.ndarray, Q: np.ndarray, cyclic: bool = True) -> float:
    """RMSD after Kabsch; optional best cyclic start index on P."""
    P = np.asarray(P, float)
    Q = np.asarray(Q, float)
    n = min(P.shape[0], Q.shape[0])
    if n < 3:
        return 1e9
    P = _resample_ring(P, n)
    Q = _resample_ring(Q, n)
    if not cyclic or n > 24:
        return _kabsch_rmsd_fixed(P, Q)
    best = 1e9
    for s in range(n):
        best = min(best, _kabsch_rmsd_fixed(np.roll(P, s, axis=0), Q))
        # reverse orientation
        best = min(best, _kabsch_rmsd_fixed(np.roll(P[::-1], s, axis=0), Q))
    return float(best)


def score_geometry_vs_crit(
    xyz: np.ndarray,
    sector_points: list[np.ndarray],
    top_k: int = 3,
    aggregate: str = "softmin",
    soft_T: float = 0.04,
    sector_weights: np.ndarray | list[float] | None = None,
) -> dict[str, Any]:
    """Cyclic Kabsch distance to Crit sector ensemble (projection side).

    aggregate
      softmin — temperature-weighted mean over all sector distances (default;
                multi-valley sheaf; more stable than hard min / top-k alone)
      softmin_persist — softmin reweighted by CTS basin-persistence weights
      topk    — mean of the *top_k* nearest templates
      min     — hard nearest template only

    sector_weights
      optional per-template positive weights (e.g. H0 basin persistence).
      Used when aggregate is softmin / softmin_persist.
    """
    if not sector_points:
        return {
            "mean_dist": 1e9,
            "method": "CRIT_KABSCH_SOFTMIN",
            "in_basin": False,
            "n_templates": 0,
        }
    dists = np.asarray(
        [_kabsch_rmsd(xyz, sp, cyclic=True) for sp in sector_points],
        dtype=float,
    )
    dmin = float(np.min(dists))
    mode = str(aggregate or "softmin").lower().strip()
    T = max(float(soft_T), 1e-12)
    m = dmin
    w = np.exp(-(dists - m) / T)
    sw = None
    if sector_weights is not None and mode in (
        "softmin",
        "softmin_persist",
        "persist",
        "cts",
        "softmin_min",
        "blend",
        "soft_min",
    ):
        sw = np.asarray(sector_weights, dtype=float).ravel()
        if sw.size == dists.size and np.all(np.isfinite(sw)) and float(np.sum(sw)) > 0:
            sw = np.clip(sw, 1e-6, None)
            w = w * sw
    soft = float(np.sum(w * dists) / (np.sum(w) + 1e-15))
    if mode == "min":
        dmean = dmin
        method = "CRIT_KABSCH_MIN"
        k = 1
    elif mode in ("topk", "top_k", "top-k"):
        order = np.sort(dists)
        k = max(1, min(int(top_k), order.size))
        dmean = float(np.mean(order[:k]))
        method = "CRIT_KABSCH_TOPK"
    elif mode in ("softmin_min", "blend", "soft_min"):
        # geometric mean of softmin and hard min — dual-scale Crit match
        dmean = float(np.sqrt(max(soft, 1e-15) * max(dmin, 1e-15)))
        method = "CRIT_KABSCH_SOFTMIN_MIN"
        k = int(dists.size)
    elif mode in ("softmin_persist", "persist", "cts"):
        dmean = soft
        method = "CRIT_KABSCH_SOFTMIN_PERSIST"
        k = int(dists.size)
    else:
        dmean = soft
        method = "CRIT_KABSCH_SOFTMIN"
        k = int(dists.size)
    return {
        "mean_dist": dmean,
        "min_dist": dmin,
        "method": method,
        "in_basin": dmean < 0.35,
        "n_templates": len(sector_points),
        "top_k": k,
        "aggregate": mode,
        "soft_T": float(soft_T) if mode not in ("min", "topk", "top_k", "top-k") else None,
        "weighted": bool(sw is not None),
    }
