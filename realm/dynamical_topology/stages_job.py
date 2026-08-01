"""Build dynamical-topology Stage lists from Job OS run artifacts.

Measure-only: never pin, never soft_T, never ACCEPTANCE.
Stages = discrete Job OS cycles (or synthesized sub-stages when artifacts are thin).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from realm.dynamical_topology.types import Stage

logger = logging.getLogger(__name__)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("stages_job skip unreadable %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None


def _as_points(arr: np.ndarray) -> np.ndarray:
    pts = np.asarray(arr, dtype=float)
    if pts.size == 0:
        return np.zeros((0, 1), dtype=float)
    if pts.ndim == 1:
        pts = pts.reshape(-1, 1)
    if pts.ndim > 2:
        pts = pts.reshape(pts.shape[0], -1)
    # Replace non-finite with column mean / 0
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


def _structure_score_cloud(score: float, barcode_n: float = 0.0) -> np.ndarray:
    """Minimal non-empty cloud from scalar structure metrics."""
    s = float(score)
    b = float(barcode_n)
    # Small 2-D cloud so knn/VR can run; not inventing acceptance.
    return _as_points(
        np.array(
            [
                [s, b],
                [s + 0.01, b],
                [s, b + 0.01],
                [s - 0.01, max(0.0, b - 0.01)],
            ],
            dtype=float,
        )
    )


def _points_from_channel_summaries(
    channel_summaries: dict[str, Any],
) -> np.ndarray | None:
    """Build points from per-window H0 metrics across channels."""
    rows: list[list[float]] = []
    for _name, summary in sorted((channel_summaries or {}).items()):
        if not isinstance(summary, dict):
            continue
        windows = summary.get("windows") or []
        for w in windows:
            if not isinstance(w, dict):
                continue
            rows.append(
                [
                    float(w.get("n_bars") or 0.0),
                    float(w.get("total_persist") or 0.0),
                    float(w.get("max_bar") or 0.0),
                    float(w.get("mean_bar") or 0.0),
                ]
            )
    if len(rows) >= 2:
        return _as_points(np.asarray(rows, dtype=float))
    if rows:
        # Pad to ≥2 points
        r0 = rows[0]
        return _as_points(np.asarray([r0, [x + 0.01 for x in r0]], dtype=float))
    return None


def _points_from_multi_scale(multi: dict[str, Any] | None) -> np.ndarray | None:
    if not multi or not isinstance(multi, dict):
        return None
    # Prefer window-level descriptors as points along discrete time
    windows = multi.get("windows") or []
    if isinstance(windows, list) and len(windows) >= 1:
        rows = []
        for w in windows:
            if not isinstance(w, dict):
                continue
            rows.append(
                [
                    float(w.get("n_bars") or 0.0),
                    float(w.get("n_long") or 0.0),
                    float(w.get("max_persistence") or 0.0),
                    float(w.get("n_points") or 0.0),
                ]
            )
        if len(rows) >= 2:
            return _as_points(np.asarray(rows, dtype=float))
        if rows:
            r0 = rows[0]
            return _as_points(np.asarray([r0, [x + 0.01 for x in r0]], dtype=float))

    # full_series may be a barcode dict (not a raw series)
    fs = multi.get("full_series")
    if isinstance(fs, dict):
        bars = fs.get("bars") or multi.get("bars") or []
        if bars:
            rows = [
                [
                    float(b.get("birth") or 0.0),
                    float(b.get("death") or 0.0),
                    float(b.get("persistence") or 0.0),
                ]
                for b in bars
                if isinstance(b, dict)
            ]
            if len(rows) >= 2:
                return _as_points(np.asarray(rows, dtype=float))
    elif isinstance(fs, (list, tuple)) and len(fs) >= 2:
        return _series_to_points(fs)

    bars = multi.get("bars") or []
    if isinstance(bars, list) and len(bars) >= 2:
        rows = [
            [
                float(b.get("birth") or 0.0),
                float(b.get("death") or 0.0),
                float(b.get("persistence") or 0.0),
            ]
            for b in bars
            if isinstance(b, dict)
        ]
        if len(rows) >= 2:
            return _as_points(np.asarray(rows, dtype=float))
    return None


def _points_from_las_series(
    source_path: str | Path | None,
    *,
    channel_pack: str | None = None,
    null_policy: str | None = None,
    max_points: int = 48,
) -> np.ndarray | None:
    """Re-ingest LAS and build series_point_cloud from regime channels."""
    if not source_path:
        return None
    path = Path(source_path)
    if not path.is_file():
        return None
    try:
        from realm.job_os.ingest_las import apply_null_policy, parse_las, select_channel_pack
        from realm.job_os.regime import resolve_regime_channels
        from realm.kb_geometry.graph import series_point_cloud

        raw = parse_las(path)
        series = apply_null_policy(raw, null_policy or "drop_row_any_null")
        if channel_pack:
            series = select_channel_pack(series, channel_pack)
        regime_chs = resolve_regime_channels(series.get("channels") or {})
        if not regime_chs:
            return None
        cloud = series_point_cloud(regime_chs, max_points=max_points)
        if cloud is None or cloud.size == 0 or cloud.shape[0] < 2:
            return None
        return _as_points(cloud)
    except Exception as exc:  # noqa: BLE001
        logger.debug("stages_job LAS point cloud failed: %s", exc)
        return None


def points_from_cycle_artifacts(
    cycle_dir: Path | str,
    *,
    regime_report: dict[str, Any] | None = None,
    sources_summary: dict[str, Any] | None = None,
) -> np.ndarray | None:
    """Extract a point cloud for one cycle from on-disk or in-memory reports."""
    cdir = Path(cycle_dir)
    reg = regime_report if regime_report is not None else _load_json(cdir / "regime_report.json")
    src = (
        sources_summary
        if sources_summary is not None
        else _load_json(cdir / "sources_summary.json")
    )
    if reg is None and src is None:
        return None

    # Prefer series_point_cloud via re-ingest when source path known
    source_path = None
    channel_pack = None
    null_policy = None
    if src:
        source_path = src.get("source_path")
        channel_pack = src.get("channel_pack")
        null_policy = src.get("null_policy")
    cloud = _points_from_las_series(
        source_path, channel_pack=channel_pack, null_policy=null_policy
    )
    if cloud is not None:
        return cloud

    # Prefer multi_scale / channel summaries from regime_report
    if reg:
        multi = reg.get("multi_scale")
        pts = _points_from_multi_scale(multi if isinstance(multi, dict) else None)
        if pts is not None:
            return pts
        pts = _points_from_channel_summaries(reg.get("channel_summaries") or {})
        if pts is not None:
            return pts
        score = float(reg.get("structure_score") or 0.0)
        bars = float(reg.get("barcode_n_bars") or 0.0)
        return _structure_score_cloud(score, bars)

    # sources_summary shallow regime only
    assert src is not None
    reg_s = src.get("regime") or {}
    multi = reg_s.get("multi_scale")
    pts = _points_from_multi_scale(multi if isinstance(multi, dict) else None)
    if pts is not None:
        return pts
    score = float(reg_s.get("structure_score") or 0.0)
    bars = float(reg_s.get("barcode_n_bars") or 0.0)
    if score != 0.0 or bars != 0.0 or reg_s.get("enabled"):
        return _structure_score_cloud(score, bars)
    return None


def build_stages_from_structure_scores(
    scores: Sequence[float],
    *,
    label_prefix: str = "score",
) -> list[Stage]:
    """Build one Stage per structure score (thin in-memory path)."""
    stages: list[Stage] = []
    for i, s in enumerate(scores):
        try:
            val = float(s)
        except (TypeError, ValueError):
            val = 0.0
        pts = _structure_score_cloud(val, float(i))
        stages.append(Stage(index=i, label=f"{label_prefix}_{i}", points=pts))
    return stages


def _synthesize_substages_from_cycle(
    cycle_dir: Path,
    *,
    start_index: int = 0,
) -> list[Stage]:
    """Expand one cycle's multi_scale / channel windows into multiple stages."""
    reg = _load_json(cycle_dir / "regime_report.json") or {}
    multi = reg.get("multi_scale") if isinstance(reg.get("multi_scale"), dict) else {}
    windows = (multi or {}).get("windows") or []
    stages: list[Stage] = []
    if isinstance(windows, list) and len(windows) >= 2:
        for j, w in enumerate(windows):
            if not isinstance(w, dict):
                continue
            row = [
                float(w.get("n_bars") or 0.0),
                float(w.get("n_long") or 0.0),
                float(w.get("max_persistence") or 0.0),
            ]
            pts = _as_points(
                np.asarray([row, [x + 0.01 for x in row], [x - 0.01 for x in row]], dtype=float)
            )
            stages.append(
                Stage(
                    index=start_index + j,
                    label=f"{cycle_dir.name}_win_{j}",
                    points=pts,
                )
            )
        if stages:
            return stages

    ch_sum = reg.get("channel_summaries") or {}
    # Collect first channel's window total_persist as 1-D series → one stage each pair
    series: list[float] = []
    for _name, summary in sorted(ch_sum.items()):
        if not isinstance(summary, dict):
            continue
        for w in summary.get("windows") or []:
            if isinstance(w, dict):
                series.append(float(w.get("total_persist") or 0.0))
        if series:
            break
    if len(series) >= 2:
        # Chunk series into stages of length ≥2
        chunk = max(2, len(series) // 2)
        idx = 0
        for j in range(0, len(series), chunk):
            part = series[j : j + chunk]
            if len(part) < 2:
                part = list(part) + [part[-1] + 0.01 if part else 0.0]
            stages.append(
                Stage(
                    index=start_index + idx,
                    label=f"{cycle_dir.name}_series_{idx}",
                    points=_series_to_points(part),
                )
            )
            idx += 1
        if stages:
            return stages

    score = float(reg.get("structure_score") or 0.0)
    bars = float(reg.get("barcode_n_bars") or 0.0)
    stages.append(
        Stage(
            index=start_index,
            label=f"{cycle_dir.name}_synth",
            points=_structure_score_cloud(score, bars),
        )
    )
    return stages


def build_stages_from_job_run(run_dir: Path | str) -> list[Stage]:
    """For each cycle_* with regime_report or sources_summary, build Stage points.

    Prefer series_point_cloud from regime channels (re-ingest LAS when source_path
    present); else use structure_score / barcode / multi_scale as embedded points.
    """
    root = Path(run_dir)
    if not root.is_dir():
        return []

    cycle_dirs = sorted(
        [
            p
            for p in root.iterdir()
            if p.is_dir() and p.name.startswith("cycle_")
        ],
        key=lambda p: p.name,
    )

    stages: list[Stage] = []
    for cdir in cycle_dirs:
        has_reg = (cdir / "regime_report.json").is_file()
        has_src = (cdir / "sources_summary.json").is_file()
        if not has_reg and not has_src:
            continue
        pts = points_from_cycle_artifacts(cdir)
        if pts is None or pts.shape[0] < 1:
            continue
        stages.append(
            Stage(
                index=len(stages),
                label=cdir.name,
                points=pts,
            )
        )

    # Thin artifacts: try structure scores from sources only
    if not stages:
        scores: list[float] = []
        for cdir in cycle_dirs:
            src = _load_json(cdir / "sources_summary.json") or {}
            reg_s = src.get("regime") or {}
            if "structure_score" in reg_s:
                scores.append(float(reg_s.get("structure_score") or 0.0))
            else:
                reg = _load_json(cdir / "regime_report.json") or {}
                if "structure_score" in reg:
                    scores.append(float(reg.get("structure_score") or 0.0))
        if scores:
            stages = build_stages_from_structure_scores(scores)

    # Still thin: synthesize substages from last available cycle
    if len(stages) < 2 and cycle_dirs:
        for cdir in reversed(cycle_dirs):
            if (cdir / "regime_report.json").is_file() or (
                cdir / "sources_summary.json"
            ).is_file():
                synth = _synthesize_substages_from_cycle(
                    cdir, start_index=len(stages)
                )
                if len(stages) == 0:
                    stages = synth
                elif len(stages) < 2 and len(synth) >= 2:
                    # Replace single coarse stage with richer substage split
                    stages = synth
                break

    # Re-index
    for i, st in enumerate(stages):
        st.index = i
    return stages
