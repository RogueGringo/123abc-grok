"""Structural surface↔downhole glue for Job Coherence OS P2.

Glue measures depth/time proximity between EDR (LAS) and MicroPulse fibers.
It is structural — not a score-chase accept gate. Commercial solved still
requires pin + export + physics; glue feeds align_score / align free params.

Rules:
  - Prefer shared domain (both depths or both times) when present.
  - Depth overlap / time overlap via range Jaccard + coverage.
  - Cross-domain (surface depth-only + MP time-only): honest structural
    fiber-join score from downhole pack presence — does NOT invent depth/time.
  - Never invent surveys or reorder depths.
"""

from __future__ import annotations

from typing import Any


def _finite(vals: list[Any]) -> list[float]:
    out: list[float] = []
    for x in vals:
        if x is None:
            continue
        try:
            v = float(x)
        except (TypeError, ValueError):
            continue
        if v == v:  # not nan
            out.append(v)
    return out


def _range_jaccard(a: list[float], b: list[float]) -> float:
    """Jaccard of closed ranges [min,max]. 0 if empty or non-overlapping."""
    if not a or not b:
        return 0.0
    a0, a1 = min(a), max(a)
    b0, b1 = min(b), max(b)
    if a1 < a0 or b1 < b0:
        return 0.0
    inter_lo = max(a0, b0)
    inter_hi = min(a1, b1)
    if inter_hi < inter_lo:
        return 0.0
    inter = inter_hi - inter_lo
    union = max(a1, b1) - min(a0, b0)
    if union <= 0:
        # degenerate point ranges
        return 1.0 if abs(a0 - b0) < 1e-9 else 0.0
    return float(inter / union)


def _coverage_in_range(points: list[float], lo: float, hi: float) -> float:
    if not points or hi < lo:
        return 0.0
    if hi == lo:
        return 1.0 if any(abs(p - lo) < 1e-9 for p in points) else 0.0
    inside = sum(1 for p in points if lo - 1e-12 <= p <= hi + 1e-12)
    return float(inside / len(points))


def compute_glue(
    surface: dict[str, Any],
    mp_bundle: dict[str, Any] | None,
    *,
    align_mode: str = "depth_primary",
) -> dict[str, Any]:
    """Compute structural glue observation between surface and MicroPulse.

    Returns
    -------
    dict
        score (0..1), method, notes, domain flags, overlap metrics,
        n_surface_rows, n_mp_times, n_mp_depths, downhole_present, …
    """
    am = (align_mode or "depth_primary").lower().strip()
    notes: list[str] = []

    s_depths = _finite(list(surface.get("depths") or []))
    s_times = _finite(list(surface.get("times") or []))
    # Also try TIME channel if times not pre-extracted
    if not s_times:
        ch = {str(k).upper(): v for k, v in (surface.get("channels") or {}).items()}
        for key in ("TIME", "RTC_TIME", "TIMESTAMP"):
            if key in ch:
                s_times = _finite(list(ch[key]))
                break

    has_mp = bool(mp_bundle) and int((mp_bundle or {}).get("n_fibers") or 0) > 0
    if not has_mp:
        # Single-source: no multi-source glue required
        n = len(s_depths)
        score = 1.0 if n > 0 else 0.0
        if am == "none":
            score = 0.5 if n > 0 else 0.0
        elif am == "survey_anchor":
            score = 0.25 if n > 0 else 0.0
        return {
            "score": float(score),
            "method": "single_source",
            "multi_source": False,
            "has_micropulse": False,
            "notes": ["no_micropulse"],
            "depth_overlap": None,
            "time_overlap": None,
            "n_surface_depths": len(s_depths),
            "n_surface_times": len(s_times),
            "n_mp_depths": 0,
            "n_mp_times": 0,
            "downhole_present": [],
            "shared_domain": None,
            "align_mode": am,
        }

    mp = mp_bundle or {}
    mp_depths = _finite(list(mp.get("depths_union") or []))
    mp_times = _finite(list(mp.get("times_union") or []))
    downhole = list(mp.get("downhole_kinds_present") or [])
    pack_ch = list((mp.get("pack_channels") or {}).keys())

    depth_overlap = _range_jaccard(s_depths, mp_depths) if s_depths and mp_depths else 0.0
    time_overlap = _range_jaccard(s_times, mp_times) if s_times and mp_times else 0.0

    # Coverage of surface points inside MP range (when ranges exist)
    depth_cov = 0.0
    if s_depths and mp_depths:
        depth_cov = _coverage_in_range(s_depths, min(mp_depths), max(mp_depths))
    time_cov = 0.0
    if s_times and mp_times:
        time_cov = _coverage_in_range(s_times, min(mp_times), max(mp_times))

    has_depth_domain = bool(s_depths) and bool(mp_depths)
    has_time_domain = bool(s_times) and bool(mp_times)

    # Structural fiber-join completeness (cross-domain fallback)
    # Fraction of common downhole kinds present among GAMMA/SHOCK/VIBE/…
    target_fibers = ("GAMMA", "SHOCK", "VIBE", "PULSE", "TELEM", "TEMP", "FLOW")
    present_set = {str(x).upper() for x in downhole} | {str(x).upper() for x in pack_ch}
    n_target = len(target_fibers)
    n_present = sum(1 for t in target_fibers if t in present_set)
    fiber_frac = float(n_present / max(n_target, 1))
    surface_ok = 1.0 if s_depths else 0.0

    method = "none"
    score = 0.0
    shared_domain: str | None = None

    if am == "none":
        method = "multi_source_no_align"
        score = 0.3 if (s_depths or s_times) and (mp_times or mp_depths or n_present) else 0.0
        notes.append("align_mode_none")
    elif am == "survey_anchor":
        method = "survey_anchor_pending"
        score = 0.2
        notes.append("survey_anchor_requires_p3")
    elif am == "depth_primary":
        if has_depth_domain:
            method = "depth_proximity"
            shared_domain = "depth"
            score = 0.5 * depth_overlap + 0.5 * depth_cov
            notes.append("depth_domain_shared")
        elif has_time_domain:
            # Prefer depth but fall back to time with mild penalty
            method = "time_proximity_fallback"
            shared_domain = "time"
            score = 0.85 * (0.5 * time_overlap + 0.5 * time_cov)
            notes.append("depth_missing_on_mp_time_fallback")
        else:
            method = "structural_fiber_join"
            shared_domain = None
            # Honest partial: fibers co-present without shared axis
            score = 0.35 + 0.35 * fiber_frac * surface_ok
            notes.append("no_shared_depth_or_time_axis")
            notes.append("structural_fiber_join_only")
    elif am == "time_primary":
        if has_time_domain:
            method = "time_proximity"
            shared_domain = "time"
            score = 0.5 * time_overlap + 0.5 * time_cov
            notes.append("time_domain_shared")
        elif has_depth_domain:
            method = "depth_proximity_fallback"
            shared_domain = "depth"
            score = 0.85 * (0.5 * depth_overlap + 0.5 * depth_cov)
            notes.append("time_missing_on_surface_depth_fallback")
        else:
            method = "structural_fiber_join"
            shared_domain = None
            score = 0.35 + 0.35 * fiber_frac * surface_ok
            notes.append("no_shared_depth_or_time_axis")
            notes.append("structural_fiber_join_only")
    else:
        method = "unknown_align_mode"
        score = 0.0
        notes.append(f"unknown_align_mode:{am}")

    # Clamp
    score = max(0.0, min(1.0, float(score)))

    if score + 1e-12 < 0.5:
        notes.append("glue_incomplete")

    return {
        "score": score,
        "method": method,
        "multi_source": True,
        "has_micropulse": True,
        "notes": notes,
        "depth_overlap": depth_overlap if has_depth_domain else None,
        "time_overlap": time_overlap if has_time_domain else None,
        "depth_coverage": depth_cov if has_depth_domain else None,
        "time_coverage": time_cov if has_time_domain else None,
        "n_surface_depths": len(s_depths),
        "n_surface_times": len(s_times),
        "n_mp_depths": len(mp_depths),
        "n_mp_times": len(mp_times),
        "downhole_present": sorted(present_set),
        "fiber_frac": fiber_frac,
        "shared_domain": shared_domain,
        "align_mode": am,
        "has_depth_domain": has_depth_domain,
        "has_time_domain": has_time_domain,
    }
