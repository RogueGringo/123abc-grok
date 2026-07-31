"""Multi-window zigzag-style H0 barcodes (Stalk A).

Transfer from: ACADEMIC/PERSISTENT TOPOLOGICAL FEATURES IN.pdf
  (Gardinazzi et al. arXiv:2410.11042 — zigzag across layers).

Repo dual: **windows** along a 1-D series or Crit scale index — not LLM layers.
Long-lived bars = stable multi-scale structure; short bars = rearrangement noise.
Never retunes pin. Informational descriptors only.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

KB_SOURCE = (
    "ACADEMIC/PERSISTENT TOPOLOGICAL FEATURES IN.pdf | arXiv:2410.11042"
)
TRANSFER_NOTE = "windows as discrete time (not LLM transformer layers)"


def _sublevel_h0_1d(values: np.ndarray) -> list[tuple[float, float]]:
    """Circular-free linear 1-D sublevel H0 (elder rule) on a finite chain.

    Returns list of (birth, death) pairs; essential components die at max+span.
    """
    v = np.asarray(values, dtype=float).ravel()
    n = int(v.size)
    if n == 0:
        return []
    if n == 1:
        s = float(v[0])
        return [(s, s + 1e-12)]

    s_min, s_max = float(v.min()), float(v.max())
    span = max(s_max - s_min, 1e-15)

    parent = np.arange(n)
    rank = np.zeros(n, dtype=int)
    birth_of_root: dict[int, float] = {}
    active = np.zeros(n, dtype=bool)
    deaths: list[tuple[float, float]] = []

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int, t: float) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        ba, bb = birth_of_root[ra], birth_of_root[rb]
        if ba < bb or (ba == bb and ra < rb):
            parent[rb] = ra
            deaths.append((bb, t))
            if rank[ra] == rank[rb]:
                rank[ra] += 1
        else:
            parent[ra] = rb
            deaths.append((ba, t))
            if rank[rb] == rank[ra]:
                rank[rb] += 1

    order = np.argsort(v, kind="mergesort")
    for i in order:
        t = float(v[i])
        active[i] = True
        birth_of_root[int(i)] = t
        parent[i] = i
        for j in (int(i) - 1, int(i) + 1):
            if 0 <= j < n and active[j]:
                union(int(i), j, t)

    roots = {find(i) for i in range(n) if active[i]}
    infinite = [(birth_of_root[r], s_max + span) for r in roots]
    return deaths + infinite


def _window_slices(n: int, n_windows: int) -> list[tuple[int, int]]:
    """Partition [0, n) into n_windows contiguous slices (last may be longer)."""
    n_windows = max(1, int(n_windows))
    if n <= 0:
        return []
    if n_windows >= n:
        return [(i, i + 1) for i in range(n)]
    edges = np.linspace(0, n, n_windows + 1, dtype=int)
    out: list[tuple[int, int]] = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b > a:
            out.append((int(a), int(b)))
    return out


def zigzag_window_barcode(
    series: Sequence[float] | np.ndarray,
    *,
    n_windows: int = 4,
    long_frac: float = 0.25,
    homology_dims: tuple[int, ...] = (0,),
) -> dict[str, Any]:
    """Multi-window H0 barcodes + coarse multi-scale summary.

    For each window, compute 1-D sublevel H0. Aggregate bars; mark long vs short
    relative to global value span. Optional multi-scale: also barcode full series.

    Parameters
    ----------
    series
        1-D real values (e.g. Crit action samples, SSSI, torque).
    n_windows
        Number of contiguous windows along the series (discrete 'time').
    long_frac
        Bars with persistence > long_frac * global_span count as long-lived.
    homology_dims
        Only dim 0 implemented in v1; other dims recorded as skipped.
    """
    v = np.asarray(series, dtype=float).ravel()
    n = int(v.size)
    dims = tuple(int(d) for d in homology_dims)
    skipped = [d for d in dims if d != 0]

    base: dict[str, Any] = {
        "kind": "zigzag_window_barcode",
        "kb_source": KB_SOURCE,
        "transfer_note": TRANSFER_NOTE,
        "not_acceptance": True,
        "ontology": "kb_geometry_zigzag_not_lambda_eq_gamma",
        "n_points": n,
        "n_windows": int(n_windows),
        "homology_dims": list(dims),
        "homology_skipped": skipped,
        "windows": [],
        "bars": [],
        "n_long": 0,
        "n_short": 0,
        "global_span": 0.0,
        "full_series": None,
        "phases": None,
        "note": (
            "Informational multi-window H0; not ACCEPTANCE / not pin retune. "
            "Windows dual LLM layers from zigzag paper."
        ),
    }

    if n == 0:
        base["note"] = "empty series"
        return base

    s_min, s_max = float(v.min()), float(v.max())
    span = max(s_max - s_min, 1e-15)
    thr = float(long_frac) * span
    base["global_span"] = span
    base["long_threshold"] = thr

    all_bars: list[dict[str, Any]] = []
    window_reports: list[dict[str, Any]] = []

    for wi, (lo, hi) in enumerate(_window_slices(n, n_windows)):
        chunk = v[lo:hi]
        diagram = _sublevel_h0_1d(chunk) if 0 in dims else []
        w_bars = []
        for b, d in diagram:
            p = float(d - b)
            long_lived = p > thr
            rec = {
                "window": wi,
                "lo": lo,
                "hi": hi,
                "birth": float(b),
                "death": float(d),
                "persistence": p,
                "long": long_lived,
                "dim": 0,
            }
            w_bars.append(rec)
            all_bars.append(rec)
        window_reports.append(
            {
                "window": wi,
                "lo": lo,
                "hi": hi,
                "n_points": int(hi - lo),
                "n_bars": len(w_bars),
                "n_long": sum(1 for x in w_bars if x["long"]),
                "max_persistence": float(max((x["persistence"] for x in w_bars), default=0.0)),
            }
        )

    # Full-series barcode (coarse scale)
    full_diag = _sublevel_h0_1d(v) if 0 in dims else []
    full_bars = []
    for b, d in full_diag:
        p = float(d - b)
        full_bars.append(
            {
                "window": "full",
                "birth": float(b),
                "death": float(d),
                "persistence": p,
                "long": p > thr,
                "dim": 0,
            }
        )

    n_long = sum(1 for x in all_bars if x["long"])
    n_short = len(all_bars) - n_long
    base["windows"] = window_reports
    base["bars"] = all_bars
    base["n_long"] = int(n_long)
    base["n_short"] = int(n_short)
    base["n_bars"] = len(all_bars)
    base["full_series"] = {
        "n_bars": len(full_bars),
        "n_long": sum(1 for x in full_bars if x["long"]),
        "max_persistence": float(max((x["persistence"] for x in full_bars), default=0.0)),
        "bars": full_bars,
    }
    base["phases"] = phase_summary(base)
    return base


def phase_summary(barcode: dict[str, Any]) -> dict[str, Any]:
    """Soft phase labels from multi-window long/short structure (info only).

    Dual of zigzag paper 'phases of prompt processing' — here along windows:
      rearrange | stable | refine | emit
    """
    windows = barcode.get("windows") or []
    if not windows:
        return {
            "labels": [],
            "dominant": "empty",
            "not_acceptance": True,
        }

    labels: list[str] = []
    for i, w in enumerate(windows):
        n_long = int(w.get("n_long") or 0)
        n_bars = int(w.get("n_bars") or 0)
        n_short = n_bars - n_long
        if n_bars == 0:
            labels.append("emit")
        elif n_short > n_long * 2 and i == 0:
            labels.append("rearrange")
        elif n_long >= max(1, n_short):
            labels.append("stable")
        elif i >= len(windows) - 1:
            labels.append("emit")
        else:
            labels.append("refine")

    # dominant by majority
    from collections import Counter

    c = Counter(labels)
    dominant = c.most_common(1)[0][0] if c else "empty"
    return {
        "labels": labels,
        "dominant": dominant,
        "counts": dict(c),
        "not_acceptance": True,
        "note": "Soft phase labels; never gate ACCEPTANCE or pin.",
    }


def zigzag_from_crit_filtration(
    filt: dict[str, Any],
    *,
    n_windows: int = 4,
) -> dict[str, Any]:
    """Build multi-window summary from crit_action_filtration diagram_H0.

    Uses persistence heights of H0 bars as a 1-D series along birth order
    (windowed multi-scale view of the existing Crit filtration).
    """
    diagram = filt.get("diagram_H0") or []
    if not diagram:
        # flat fallback from s_min/s_max
        series = np.linspace(
            float(filt.get("s_min") or 0.0),
            float(filt.get("s_max") or 1.0),
            32,
        )
    else:
        # ordered by birth
        ordered = sorted(diagram, key=lambda x: float(x.get("birth") or 0.0))
        series = np.array(
            [float(x.get("persistence") or 0.0) for x in ordered],
            dtype=float,
        )
        if series.size < 4:
            series = np.resize(series, 8)

    out = zigzag_window_barcode(series, n_windows=n_windows)
    out["source"] = "crit_action_filtration"
    out["crit_n_persistent"] = filt.get("n_persistent")
    out["crit_max_persistence"] = filt.get("max_persistence")
    return out
