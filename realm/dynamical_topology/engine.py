"""Stage-axis dynamical topology engine (zigzag-faithful dual spine).

Stages are discrete time (not LLM layers). Measure-only: never pin, never soft_T,
never ACCEPTANCE.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Sequence

import numpy as np

from realm.dynamical_topology.complexes import knn_adjacency
from realm.dynamical_topology.types import Stage, empty_report, finalize_report
from realm.kb_geometry.rips_h0 import vietoris_rips_h0
from realm.kb_geometry.zigzag_windows import phase_summary, zigzag_window_barcode

_KNOWN_PHASES = frozenset({"rearrange", "stable", "refine", "emit"})


def _as_points(points: np.ndarray | Sequence[Sequence[float]]) -> np.ndarray:
    pts = np.asarray(points, dtype=float)
    if pts.ndim == 1:
        pts = pts.reshape(-1, 1)
    return pts


def _structure_score(
    points: np.ndarray,
    *,
    knn_k: int,
    long_frac: float,
) -> tuple[float, dict[str, Any]]:
    """Per-stage structure from VR H0 (n_long / total_persistence) + kNN adj."""
    n = int(points.shape[0])
    if n < 2:
        return 0.0, {
            "n_points": n,
            "n_long": 0,
            "n_short": 0,
            "total_persistence": 0.0,
            "mean_knn_edge": 0.0,
            "skipped": True,
        }

    adj = knn_adjacency(points, knn_k)
    # Mean edge length of kNN graph (informational dual stalk)
    mean_edge = 0.0
    n_edges = 0
    if adj.size and n >= 2:
        # Reconstruct edge lengths from pairwise distances on edges
        sq = np.sum(points * points, axis=1, keepdims=True)
        d2 = np.maximum(sq + sq.T - 2.0 * (points @ points.T), 0.0)
        d = np.sqrt(d2)
        iu = np.triu_indices(n, k=1)
        mask = adj[iu] > 0
        if np.any(mask):
            mean_edge = float(np.mean(d[iu][mask]))
            n_edges = int(np.sum(mask))

    rips = vietoris_rips_h0(points, long_frac=long_frac)
    n_long = int(rips.get("n_long") or 0)
    bars = rips.get("bars") or []
    total_p = float(sum(float(b.get("persistence") or 0.0) for b in bars))
    # Prefer n_long with total_persistence tie-break for stage-axis series
    score = float(n_long) + 0.01 * total_p

    detail = {
        "n_points": n,
        "n_long": n_long,
        "n_short": int(rips.get("n_short") or 0),
        "total_persistence": total_p,
        "mean_knn_edge": mean_edge,
        "n_knn_edges": n_edges,
        "rips_n_bars": int(rips.get("n_bars") or len(bars)),
        "skipped": False,
    }
    return score, detail


def _phases_from_stages(
    stages: Sequence[Stage],
    barcode: dict[str, Any],
) -> dict[str, Any]:
    """Use stage labels when they are known phases; else phase_summary."""
    labels_raw = [str(s.label) for s in stages]
    if labels_raw and all(lab in _KNOWN_PHASES for lab in labels_raw):
        counts = dict(Counter(labels_raw))
        dominant = Counter(labels_raw).most_common(1)[0][0]
        return {
            "labels": list(labels_raw),
            "dominant": dominant,
            "counts": counts,
            "source": "stage_labels",
            "not_acceptance": True,
        }
    # Fall back to zigzag-window phase_summary when labels are free-form
    if barcode.get("windows"):
        summary = phase_summary(barcode)
        summary["source"] = "phase_summary"
        return summary
    # Single-window fallback from stage count
    if not labels_raw:
        return {"labels": [], "dominant": None, "source": "empty", "not_acceptance": True}
    # Map unknown labels via coarse barcode majority if available
    summary = phase_summary(barcode) if barcode else {
        "labels": [],
        "dominant": "refine",
        "not_acceptance": True,
    }
    # Preserve free-form labels but clamp dominant into known set when possible
    if summary.get("dominant") not in _KNOWN_PHASES:
        summary["dominant"] = "refine"
    summary["labels"] = list(labels_raw)
    summary["source"] = "mixed_labels"
    summary["not_acceptance"] = True
    return summary


def run_dynamical_topology(
    stages: Sequence[Stage],
    *,
    knn_k: int = 5,
    long_frac: float = 0.25,
) -> dict[str, Any]:
    """Build per-stage complexes and stage-axis barcode report.

    Structure score per stage from VR H0 (n_long / total_persistence).
    Stage-axis: 1-D series of scores → zigzag_window_barcode elder H0.
    Always finalize_report (not_acceptance, pin/acceptance non-writable).
    """
    base = empty_report()
    stage_list = list(stages or [])
    n_stages = len(stage_list)
    base["n_stages"] = n_stages

    if n_stages == 0:
        return finalize_report(base)

    scores: list[float] = []
    per_stage: list[dict[str, Any]] = []
    spatial_n_long = 0
    spatial_n_short = 0

    for st in stage_list:
        pts = _as_points(st.points)
        score, detail = _structure_score(pts, knn_k=knn_k, long_frac=long_frac)
        scores.append(score)
        spatial_n_long += int(detail.get("n_long") or 0)
        spatial_n_short += int(detail.get("n_short") or 0)
        per_stage.append(
            {
                "index": int(st.index),
                "label": str(st.label),
                "structure_score": float(score),
                **detail,
            }
        )

    # Stage-axis barcode: structure scores as discrete-time series
    n_win = max(1, min(n_stages, max(2, n_stages // 1)))
    # Prefer one window per stage when few stages so phase_summary has T windows
    n_win = n_stages if n_stages <= 8 else min(8, n_stages)
    zz = zigzag_window_barcode(
        scores,
        n_windows=n_win,
        long_frac=float(long_frac),
    )

    bars = list(zz.get("bars") or [])
    n_long = int(zz.get("n_long") or 0)
    n_short = int(zz.get("n_short") or 0)
    # Dual spine: if stage-axis series is flat/short, surface spatial long structure
    if n_long < 1 and spatial_n_long >= 1:
        n_long = spatial_n_long
        n_short = spatial_n_short

    phases = _phases_from_stages(stage_list, zz)

    base.update(
        {
            "n_stages": n_stages,
            "bars": bars,
            "n_long": int(n_long),
            "n_short": int(n_short),
            "n_bars": len(bars),
            "phases": phases,
            "structure_scores": [float(s) for s in scores],
            "per_stage": per_stage,
            "stage_axis": {
                "kind": zz.get("kind"),
                "n_windows": zz.get("n_windows"),
                "n_long": zz.get("n_long"),
                "n_short": zz.get("n_short"),
                "full_series": zz.get("full_series"),
                "windows": zz.get("windows"),
            },
            "spatial_n_long": int(spatial_n_long),
            "spatial_n_short": int(spatial_n_short),
            "knn_k": int(knn_k),
            "long_frac": float(long_frac),
            "sheaf_dual": None,
        }
    )
    return finalize_report(base)


def topology_stable(
    report: dict[str, Any] | None,
    *,
    prev: dict[str, Any] | None = None,
    drop_tol: float = 0.5,
) -> bool:
    """Pin-safe stability check for dual-spine control (measure side).

    Collapse if n_long drops more than drop_tol relative to prev.
    rearrange-dominant with prev → False. Empty / no stages → False.
    Never writes pin or soft_T.
    """
    if not report:
        return False

    n_stages = int(report.get("n_stages") or 0)
    if n_stages < 1:
        return False

    phases = report.get("phases") or {}
    dominant = phases.get("dominant")
    n_long = int(report.get("n_long") or 0)

    if prev is not None:
        prev_n_long = int(prev.get("n_long") or 0)
        if prev_n_long > 0 and n_long < (1.0 - float(drop_tol)) * prev_n_long:
            return False
        if dominant == "rearrange":
            return False
        return True

    # No previous report: defined boolean when stages exist (no collapse check).
    # Prefer stable|emit; other dominants still count as defined (True).
    if dominant in ("stable", "emit"):
        return True
    return True
