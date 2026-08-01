"""Build dynamical-topology Stage lists from Crit action filtration.

Measure-only: diagram_H0 persistence series or S samples → windowed stages.
Never pin, never ACCEPTANCE.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from realm.dynamical_topology.types import Stage


def _as_points(arr: np.ndarray) -> np.ndarray:
    pts = np.asarray(arr, dtype=float)
    if pts.size == 0:
        return np.zeros((0, 1), dtype=float)
    if pts.ndim == 1:
        pts = pts.reshape(-1, 1)
    if pts.ndim > 2:
        pts = pts.reshape(pts.shape[0], -1)
    for j in range(pts.shape[1]):
        col = pts[:, j]
        finite = np.isfinite(col)
        if not np.any(finite):
            pts[:, j] = 0.0
        else:
            m = float(np.mean(col[finite]))
            pts[:, j] = np.where(finite, col, m)
    return pts


def _series_to_points(series: Sequence[float]) -> np.ndarray:
    """Embed 1-D series as (n, 2) points (index, value) for spatial VR."""
    vals = [float(x) for x in series if np.isfinite(float(x))]
    if not vals:
        return np.zeros((0, 2), dtype=float)
    n = len(vals)
    idx = np.arange(n, dtype=float)
    return _as_points(np.column_stack([idx, np.asarray(vals, dtype=float)]))


def _pad_cloud(pts: np.ndarray, min_n: int = 3) -> np.ndarray:
    """Ensure enough points for knn/VR without inventing structure."""
    if pts.size == 0:
        return _as_points(np.array([[0.0, 0.0], [0.01, 0.0], [0.0, 0.01]], dtype=float))
    if pts.ndim == 1:
        pts = pts.reshape(-1, 1)
    if pts.shape[0] >= min_n:
        return pts
    rows = [pts[i % pts.shape[0]].copy() for i in range(min_n)]
    for i, r in enumerate(rows):
        r = r + (i * 0.01)
        rows[i] = r
    return _as_points(np.asarray(rows, dtype=float))


def _diagram_persistence_series(filt: dict[str, Any]) -> list[float]:
    diagram = filt.get("diagram_H0") or []
    if not isinstance(diagram, list) or not diagram:
        return []
    ordered = sorted(
        [x for x in diagram if isinstance(x, dict)],
        key=lambda x: float(x.get("birth") or 0.0),
    )
    series: list[float] = []
    for bar in ordered:
        try:
            p = float(bar.get("persistence"))
        except (TypeError, ValueError):
            try:
                p = float(bar.get("death") or 0.0) - float(bar.get("birth") or 0.0)
            except (TypeError, ValueError):
                p = 0.0
        if not np.isfinite(p):
            p = 0.0
        series.append(p)
    return series


def _s_samples(filt: dict[str, Any]) -> list[float]:
    for key in ("S", "s_samples", "action_S", "samples"):
        raw = filt.get(key)
        if raw is None:
            continue
        if isinstance(raw, (list, tuple, np.ndarray)):
            out: list[float] = []
            for x in raw:
                try:
                    v = float(x)
                except (TypeError, ValueError):
                    continue
                if np.isfinite(v):
                    out.append(v)
            if out:
                return out
    return []


def _split_series_windows(
    series: Sequence[float],
    *,
    n_windows: int | None = None,
    min_points: int = 2,
) -> list[list[float]]:
    """Split a 1-D series into contiguous windows (stages)."""
    vals = [float(x) for x in series if np.isfinite(float(x))]
    if not vals:
        return []
    n = len(vals)
    if n_windows is None:
        # Prefer 2–4 windows when series is long enough
        if n < 4:
            n_windows = 1
        elif n < 8:
            n_windows = 2
        else:
            n_windows = min(4, max(2, n // 4))
    n_windows = max(1, int(n_windows))
    # Resize tiny series so each window has min_points
    if n < n_windows * min_points and n_windows > 1:
        n_windows = max(1, n // min_points) if n >= min_points else 1

    chunk = max(min_points, (n + n_windows - 1) // n_windows)
    windows: list[list[float]] = []
    for i in range(0, n, chunk):
        part = vals[i : i + chunk]
        if not part:
            continue
        if len(part) < min_points:
            # pad last short window by repeating end with mild jitter
            last = part[-1]
            while len(part) < min_points:
                part = list(part) + [last + 0.01 * len(part)]
        windows.append(list(part))
        if len(windows) >= n_windows:
            # fold any remaining into last window
            rest = vals[i + chunk :]
            if rest:
                windows[-1] = windows[-1] + list(rest)
            break
    return windows


def build_stages_from_crit_filtration(filt: dict) -> list[Stage]:
    """Build stages from Crit filtration dict.

    Prefer ``diagram_H0`` persistence (birth-ordered) split into windows;
    else use S samples if present. Returns [] for empty/flat input.
    """
    if not isinstance(filt, dict) or not filt:
        return []

    series = _diagram_persistence_series(filt)
    source = "diagram_H0"
    if not series:
        series = _s_samples(filt)
        source = "S"
    if not series:
        # Flat fallback from s_min/s_max when present
        try:
            s_min = float(filt.get("s_min") or 0.0)
            s_max = float(filt.get("s_max") or 0.0)
        except (TypeError, ValueError):
            return []
        if abs(s_max - s_min) < 1e-15 and not filt.get("n_levels"):
            return []
        series = list(np.linspace(s_min, s_max if s_max != s_min else s_min + 1.0, 16))
        source = "s_span"

    windows = _split_series_windows(series)
    if not windows:
        return []

    stages: list[Stage] = []
    for j, win in enumerate(windows):
        pts = _pad_cloud(_series_to_points(win))
        stages.append(
            Stage(
                index=j,
                label=f"crit_{source}_win_{j}",
                points=pts,
            )
        )
    return stages
