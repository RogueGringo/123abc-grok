"""Regime stalk (C) for Job Coherence OS P4.

Windowed H0-style persistence summary on available surface channels
(SSSI / TOR / RPM preferred). Shock exceedance counts when SHOCK fiber
is present. Uses free param ``window_scale`` for window length.

Free param ``regime_mode``: off | persist_h0 | dual_gate_windows.

Science dual-gate lives in ``science.py`` (informational only).
Regime never retunes the QC pin and never invents channels/depths.
"""

from __future__ import annotations

from typing import Any

# Preferred surface fibers for stick-slip / rotary regime barcode
REGIME_SURFACE_CHANNELS = ("SSSI", "TOR", "RPM")
# Alternate names that map to the same role
_CHANNEL_ALIASES: dict[str, str] = {
    "TORQUE": "TOR",
    "TRQ": "TOR",
    "STICK_SLIP": "SSSI",
    "SS": "SSSI",
    "ROTARY": "RPM",
}

# Base window length (rows) at window_scale=1; scale multiplies
_BASE_WINDOW = 4
# Max windows stored in report (full aggregate still uses all)
_MAX_WINDOWS_STORED = 24
# Shock exceedance: values above mean + k * std
_SHOCK_K = 1.5


def _finite_list(arr: Any) -> list[float]:
    out: list[float] = []
    if not arr:
        return out
    for x in arr:
        if x is None:
            continue
        try:
            v = float(x)
        except (TypeError, ValueError):
            continue
        if v != v:  # nan
            continue
        out.append(v)
    return out


def _mean(xs: list[float]) -> float:
    if not xs:
        return 0.0
    return float(sum(xs) / len(xs))


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return float(var ** 0.5)


def window_length(n_rows: int, window_scale: int, *, base: int = _BASE_WINDOW) -> int:
    """Window length from free param window_scale (clamped to series length)."""
    ws = max(1, int(window_scale))
    n = max(0, int(n_rows))
    if n <= 0:
        return 0
    return max(2, min(n, base * ws))


def h0_runs_above(values: list[float], threshold: float) -> list[int]:
    """H0 bars: contiguous run lengths where value > threshold."""
    bars: list[int] = []
    start: int | None = None
    for i, v in enumerate(values):
        if v > threshold:
            if start is None:
                start = i
        else:
            if start is not None:
                bars.append(i - start)
                start = None
    if start is not None:
        bars.append(len(values) - start)
    return bars


def channel_h0_summary(
    values: list[float],
    *,
    window_scale: int = 1,
) -> dict[str, Any]:
    """Windowed H0 persistence summary for one 1-D series."""
    n = len(values)
    w = window_length(n, window_scale)
    if n == 0 or w <= 0:
        return {
            "n_samples": n,
            "window_len": w,
            "n_windows": 0,
            "barcode_n_bars": 0,
            "total_persistence": 0.0,
            "mean_n_bars": 0.0,
            "mean_max_bar": 0.0,
            "global_mean": 0.0,
            "global_std": 0.0,
            "windows": [],
        }

    step = max(1, w // 2)  # 50% overlap
    windows: list[dict[str, Any]] = []
    starts = list(range(0, max(1, n - w + 1), step))
    if not starts:
        starts = [0]

    total_bars = 0
    total_persist = 0.0
    sum_n_bars = 0.0
    sum_max_bar = 0.0

    for start in starts:
        chunk = values[start : start + w]
        if len(chunk) < 2:
            continue
        thr = _mean(chunk)
        bars = h0_runs_above(chunk, thr)
        n_bars = len(bars)
        persist = float(sum(bars))
        max_bar = float(max(bars)) if bars else 0.0
        total_bars += n_bars
        total_persist += persist
        sum_n_bars += n_bars
        sum_max_bar += max_bar
        if len(windows) < _MAX_WINDOWS_STORED:
            windows.append(
                {
                    "start": start,
                    "len": len(chunk),
                    "threshold": thr,
                    "n_bars": n_bars,
                    "mean_bar": (_mean([float(b) for b in bars]) if bars else 0.0),
                    "max_bar": max_bar,
                    "total_persist": persist,
                }
            )

    n_win = len(starts) if starts else 0
    # Recount windows actually processed
    n_processed = max(1, len(starts))
    return {
        "n_samples": n,
        "window_len": w,
        "n_windows": n_processed,
        "barcode_n_bars": int(total_bars),
        "total_persistence": float(total_persist),
        "mean_n_bars": float(sum_n_bars / n_processed),
        "mean_max_bar": float(sum_max_bar / n_processed),
        "global_mean": _mean(values),
        "global_std": _std(values),
        "windows": windows,
    }


def resolve_regime_channels(channels: dict[str, Any]) -> dict[str, list[float]]:
    """Map series channels to preferred regime mnemonics (available surface)."""
    upper = {str(k).upper(): v for k, v in (channels or {}).items()}
    # Alias fold
    folded: dict[str, Any] = {}
    for k, v in upper.items():
        canon = _CHANNEL_ALIASES.get(k, k)
        if canon not in folded:
            folded[canon] = v

    out: dict[str, list[float]] = {}
    for name in REGIME_SURFACE_CHANNELS:
        arr = folded.get(name)
        if arr is None:
            continue
        finite = _finite_list(arr)
        if finite:
            out[name] = finite
    # If none of preferred, pick any numeric surface-ish channel (honest fallback)
    if not out:
        skip = {
            "DEPT",
            "DEPTH",
            "MD",
            "TIME",
            "GAMMA",
            "SHOCK",
            "VIBE",
            "PULSE",
            "TELEM",
            "TEMP",
            "FLOW",
        }
        for name, arr in sorted(folded.items()):
            if name in skip:
                continue
            finite = _finite_list(arr)
            if len(finite) >= 2:
                out[name] = finite
                break
    return out


def shock_exceedance(
    channels: dict[str, Any],
    *,
    k: float = _SHOCK_K,
) -> dict[str, Any]:
    """Count SHOCK (or X/Y/Z shock) samples above mean + k*std."""
    upper = {str(key).upper(): val for key, val in (channels or {}).items()}
    shock_key = None
    for cand in ("SHOCK", "X_SHOCK", "Z_SHOCK", "Y_SHOCK"):
        if cand in upper and upper[cand]:
            shock_key = cand
            break
    if shock_key is None:
        return {
            "present": False,
            "channel": None,
            "n_samples": 0,
            "n_exceed": 0,
            "threshold": None,
            "k": float(k),
        }
    vals = _finite_list(upper[shock_key])
    if not vals:
        return {
            "present": True,
            "channel": shock_key,
            "n_samples": 0,
            "n_exceed": 0,
            "threshold": None,
            "k": float(k),
        }
    thr = _mean(vals) + float(k) * _std(vals)
    n_ex = sum(1 for v in vals if v > thr)
    return {
        "present": True,
        "channel": shock_key,
        "n_samples": len(vals),
        "n_exceed": int(n_ex),
        "threshold": float(thr),
        "k": float(k),
        "mean": _mean(vals),
        "std": _std(vals),
    }


def structure_score(channel_summaries: dict[str, dict[str, Any]]) -> float:
    """Scalar 0..1 structure score from barcode summaries (info only / dual-gate)."""
    if not channel_summaries:
        return 0.0
    parts: list[float] = []
    for _name, s in channel_summaries.items():
        n_win = max(1, int(s.get("n_windows") or 1))
        n_bars = float(s.get("barcode_n_bars") or 0)
        persist = float(s.get("total_persistence") or 0.0)
        # denser bars + longer total persistence → higher structure (capped)
        density = min(1.0, n_bars / (4.0 * n_win))
        persist_term = min(1.0, persist / (8.0 * n_win))
        parts.append(0.5 * density + 0.5 * persist_term)
    return float(sum(parts) / len(parts))


def evaluate_regime(
    series: dict[str, Any] | None,
    *,
    regime_mode: str = "off",
    window_scale: int = 1,
    enabled: bool = False,
    require_regime: bool = False,
    shock_k: float = _SHOCK_K,
) -> dict[str, Any]:
    """Build regime_report for one cycle.

    Parameters
    ----------
    enabled
        True when ``--with-regime`` (or require) is set. When False and mode is
        ``off``, returns a disabled stub with stalk_ok=True.
    require_regime
        When True, stalk_ok needs channels + engaged mode.
    """
    mode = str(regime_mode or "off").lower().strip()
    if mode not in ("off", "persist_h0", "dual_gate_windows"):
        mode = "off"
    ws = max(1, int(window_scale))
    engaged = bool(enabled) or mode != "off" or bool(require_regime)

    notes: list[str] = []
    channels = (series or {}).get("channels") or {}
    n_rows = int((series or {}).get("n_rows") or 0)

    if not engaged:
        return {
            "enabled": False,
            "regime_mode": mode,
            "window_scale": ws,
            "present": False,
            "stalk_ok": True,
            "channels_used": [],
            "barcode_n_bars": 0,
            "total_persistence": 0.0,
            "structure_score": 0.0,
            "channel_summaries": {},
            "shock": {"present": False, "n_exceed": 0},
            "notes": ["regime_off"],
            "ontology": "regime_stalk_c_not_rop_score",
            "informational_only": True,
        }

    # Effective analysis mode when flag on but free param still off
    analysis_mode = mode if mode != "off" else "persist_h0"
    regime_chs = resolve_regime_channels(channels)
    ch_summaries: dict[str, dict[str, Any]] = {}
    total_bars = 0
    total_persist = 0.0
    for name, vals in regime_chs.items():
        summary = channel_h0_summary(vals, window_scale=ws)
        ch_summaries[name] = summary
        total_bars += int(summary.get("barcode_n_bars") or 0)
        total_persist += float(summary.get("total_persistence") or 0.0)

    shock = shock_exceedance(channels, k=shock_k)
    score = structure_score(ch_summaries)
    present = bool(ch_summaries)

    # P4 multi-scale: zigzag window barcode + optional spectral labels (info only)
    multi_scale: dict[str, Any] = {"enabled": False}
    graph_labels: dict[str, Any] = {"enabled": False}
    if present:
        try:
            from realm.kb_geometry.zigzag_windows import zigzag_window_barcode

            # Prefer SSSI then first regime channel for multi-scale barcode
            primary = (
                regime_chs.get("SSSI")
                or regime_chs.get("TOR")
                or next(iter(regime_chs.values()))
            )
            n_win = max(2, min(8, 2 * ws))
            multi_scale = zigzag_window_barcode(
                primary, n_windows=n_win, long_frac=0.20
            )
            multi_scale["enabled"] = True
            multi_scale["channel"] = (
                "SSSI"
                if "SSSI" in regime_chs
                else ("TOR" if "TOR" in regime_chs else sorted(regime_chs)[0])
            )
            notes.append(
                f"multi_scale_n_long:{multi_scale.get('n_long')}"
            )
        except Exception as exc:  # noqa: BLE001
            multi_scale = {
                "enabled": False,
                "error": str(exc),
                "not_acceptance": True,
            }
        try:
            from realm.kb_geometry.graph import (
                knn_graph,
                series_point_cloud,
                spectral_labels,
            )
            from realm.kb_geometry.rips_h0 import (
                algebraic_connectivity,
                vietoris_rips_h0,
            )

            cloud = series_point_cloud(regime_chs, max_points=48)
            if cloud.shape[0] >= 4:
                g = knn_graph(cloud, k=min(5, cloud.shape[0] - 1))
                lab = spectral_labels(g, n_clusters=2, seed=0)
                lam = algebraic_connectivity(g)
                rips = vietoris_rips_h0(cloud, long_frac=0.25)
                graph_labels = {
                    "enabled": True,
                    "n_points": int(cloud.shape[0]),
                    "n_clusters": lab.get("n_clusters"),
                    "labels": lab.get("labels"),
                    "lambda_1": lam.get("lambda_1"),
                    "rips_h0_n_long": rips.get("n_long"),
                    "rips_h0_n_bars": rips.get("n_bars"),
                    "not_acceptance": True,
                    "informational_only": True,
                    "note": (
                        "Spectral labels + VR H0 + graph λ1 are informational; "
                        "never set SOLVED; λ1 is graph connectivity not λ=γ."
                    ),
                }
                notes.append("spectral_labels_info")
                notes.append(f"graph_lambda1:{lam.get('lambda_1')}")
        except Exception as exc:  # noqa: BLE001
            graph_labels = {
                "enabled": False,
                "error": str(exc),
                "not_acceptance": True,
            }

    if not present:
        notes.append("regime_no_surface_channels")
    else:
        notes.append(f"regime_channels:{','.join(sorted(ch_summaries))}")
    if shock.get("present"):
        notes.append(f"shock_exceed:{shock.get('n_exceed')}")
    if mode == "off" and enabled:
        notes.append("regime_mode_off_analysis_persist_h0")

    # stalk_ok: commercial optional gate when require_regime
    if require_regime:
        stalk_ok = present and mode != "off"
        if mode == "off":
            notes.append("regime_require_but_mode_off")
        if not present:
            notes.append("regime_require_missing_channels")
    else:
        # Info stalk: ok unless engaged mode with zero surface signal
        if mode == "off":
            stalk_ok = True
        else:
            stalk_ok = present
            if not present:
                notes.append("regime_mode_on_missing_channels")

    return {
        "enabled": True,
        "regime_mode": mode,
        "analysis_mode": analysis_mode,
        "window_scale": ws,
        "window_len": window_length(n_rows or max((len(v) for v in regime_chs.values()), default=0), ws),
        "n_rows": n_rows,
        "present": present,
        "stalk_ok": bool(stalk_ok),
        "channels_used": sorted(ch_summaries.keys()),
        "barcode_n_bars": int(total_bars),
        "total_persistence": float(total_persist),
        "structure_score": float(score),
        "channel_summaries": ch_summaries,
        "multi_scale": multi_scale,
        "graph_labels": graph_labels,
        "shock": shock,
        "shock_exceedance": int(shock.get("n_exceed") or 0),
        "notes": notes,
        "ontology": "regime_stalk_c_not_rop_score",
        "informational_only": True,
        "not_acceptance": True,
        "disclaimers": [
            "Regime barcode is informational unless --require-regime.",
            "Multi-scale zigzag + spectral labels never set SOLVED alone.",
            "Never retunes QC pin. Never ROP / ζ claim.",
            "Science dual-gate annex never sets SOLVED alone.",
        ],
    }
