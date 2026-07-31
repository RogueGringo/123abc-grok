"""Observe job cycle: pin + export completeness + align/glue + physics.

Builds Observations from ingest series + pin report + free params.
P2: multi-source glue_score (surface LAS + MicroPulse fibers) feeds align_score.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from realm.job_os.glue import compute_glue
from realm.job_os.pin import verify_job_pin
from realm.job_os.types import FreeParams, JobThresholds, Observations, PACK_REQUIRED


def _align_score(
    series: dict[str, Any],
    params: FreeParams,
    glue: dict[str, Any] | None = None,
) -> float:
    """Align / glue score for is_solved.

    P1 single-source: depth presence.
    P2 multi-source: structural glue_score from compute_glue (depth/time
    proximity or honest fiber-join — not score-chase).
    """
    if glue is not None and glue.get("multi_source"):
        return float(glue.get("score") or 0.0)

    depths = series.get("depths") or []
    n = len(depths)
    if n <= 0:
        return 0.0
    am = params.align_mode
    if am == "none":
        return 0.5
    if am == "survey_anchor":
        # No survey fiber in P1/P2 core — incomplete glue until P3
        return 0.25
    # depth_primary or time_primary on single LAS: rows present → good
    finite = sum(1 for d in depths if d == d)  # not nan
    return float(finite / max(n, 1))


def _physics_rollups(
    series: dict[str, Any],
    pin: dict[str, Any],
    thr: JobThresholds,
) -> tuple[int, int, int, list[str]]:
    """Count physics ok/warn/fail from pin + simple channel bounds."""
    notes: list[str] = []
    n_ok = 0
    n_warn = 0
    n_fail = 0

    if not pin.get("depth_mono_ok", pin.get("ok")):
        n_fail += 1
        notes.append("physics_depth_mono_fail")
    else:
        n_ok += 1

    if not pin.get("unit_sanity_ok", True):
        n_fail += 1
        notes.append("physics_unit_fail")
    else:
        n_ok += 1

    missing = pin.get("missing_channels") or []
    if missing:
        n_fail += 1
        notes.append("physics_missing_channels")
    else:
        n_ok += 1

    # Soft bound warnings (WOB negative etc.) — surface channels only
    channels = {str(k).upper(): v for k, v in (series.get("channels") or {}).items()}
    for name, lo in (("WOB", -1.0), ("RPM", -1.0), ("SPP", -1.0)):
        arr = channels.get(name)
        if not arr:
            continue
        bad = 0
        for x in arr:
            if x is None:
                continue
            try:
                if float(x) < lo:
                    bad += 1
            except (TypeError, ValueError):
                bad += 1
        if bad > 0:
            n_warn += 1
            notes.append(f"bound_warn:{name}:{bad}")
        else:
            n_ok += 1

    return n_ok, n_warn, n_fail, notes


def observe_job(
    *,
    series: dict[str, Any],
    params: FreeParams,
    thr: JobThresholds | None = None,
    out_dir: Path | str = ".",
    pin: dict[str, Any] | None = None,
    glue: dict[str, Any] | None = None,
) -> Observations:
    """Extract observations from one execute (ingest + pin + align/glue)."""
    thr = thr or JobThresholds()
    p = params.clamp()
    if pin is None:
        pin = verify_job_pin(
            series,
            pack=p.channel_pack,
            depth_mono_eps=float(thr.depth_mono_eps),
        )

    # Glue: use provided report or compute from series.micropulse bundle-like
    if glue is None:
        mp = series.get("micropulse")
        if mp:
            # Reconstruct minimal bundle for glue from joined summary
            bundle = {
                "n_fibers": int(mp.get("n_fibers") or 0),
                "times_union": list(mp.get("times_union") or []),
                "depths_union": list(mp.get("depths_union") or []),
                "downhole_kinds_present": list(mp.get("downhole_kinds_present") or []),
                "pack_channels": {
                    k: True for k in (mp.get("pack_channels") or [])
                },
            }
            glue = compute_glue(
                series,
                bundle,
                align_mode=p.align_mode,
                channel_pack=p.channel_pack,
            )
        else:
            glue = compute_glue(
                series,
                None,
                align_mode=p.align_mode,
                channel_pack=p.channel_pack,
            )

    required = PACK_REQUIRED.get(p.channel_pack, PACK_REQUIRED["surface_min"])
    present = pin.get("present_channels") or []
    missing = pin.get("missing_channels") or []
    n_required = len(required)
    n_required_present = n_required - len(missing)

    n_rows = int(series.get("n_rows") or len(series.get("depths") or []) or 0)
    n_channels = len(series.get("channels") or {})

    export_ok_fraction = (
        float(n_required_present) / float(max(n_required, 1)) if n_required else 0.0
    )
    # rows must exist for export completeness
    if n_rows <= 0:
        export_ok_fraction = 0.0

    align = _align_score(series, p, glue=glue)
    n_ok, n_warn, n_fail, phys_notes = _physics_rollups(series, pin, thr)

    notes: list[str] = []
    if not pin.get("ok"):
        notes.append("pin_fail")
    if export_ok_fraction + 1e-12 < thr.min_export_ok_fraction:
        notes.append("export_incomplete")
    if n_fail > thr.max_physics_fail:
        notes.append("physics_fail")
    if align + 1e-12 < thr.min_align_score:
        notes.append("align_weak")
    glue_notes = list(glue.get("notes") or [])
    if "glue_incomplete" in glue_notes:
        notes.append("glue_incomplete")
    notes.extend(phys_notes)

    verify_ok = bool(pin.get("ok")) and export_ok_fraction + 1e-12 >= thr.min_export_ok_fraction
    if thr.require_verify_ok and n_fail > thr.max_physics_fail:
        verify_ok = False

    mp_info = series.get("micropulse") or {}
    has_mp = bool(series.get("has_micropulse") or glue.get("has_micropulse"))

    return Observations(
        pin_ok=bool(pin.get("ok")),
        n_rows=n_rows,
        n_channels=n_channels,
        n_required=n_required,
        n_required_present=n_required_present,
        export_ok_fraction=export_ok_fraction,
        verify_ok=verify_ok,
        align_score=align,
        physics_n_ok=n_ok,
        physics_n_warn=n_warn,
        physics_n_fail=n_fail,
        depth_mono_ok=bool(pin.get("depth_mono_ok", False)),
        unit_sanity_ok=bool(pin.get("unit_sanity_ok", False)),
        out_dir=str(out_dir),
        notes=notes,
        has_micropulse=has_mp,
        glue_score=float(glue.get("score") or 0.0),
        glue_method=str(glue.get("method") or "") or None,
        mp_n_fibers=int(mp_info.get("n_fibers") or 0),
        mp_kinds=list(mp_info.get("kinds") or []),
        glue_notes=glue_notes,
        glue_has_depth_domain=bool(glue.get("has_depth_domain")),
        glue_has_time_domain=bool(glue.get("has_time_domain")),
    )


def is_solved(obs: Observations, thr: JobThresholds, params: FreeParams) -> bool:
    """Job routine coherence gate: pin + export + physics + align/glue (not ROP)."""
    p = params.clamp()
    if thr.require_pin and not obs.pin_ok:
        return False
    if obs.n_rows <= 0:
        return False
    if obs.export_ok_fraction + 1e-12 < thr.min_export_ok_fraction:
        return False
    if thr.require_verify_ok and obs.verify_ok is False:
        return False
    if obs.physics_n_fail > thr.max_physics_fail:
        return False
    if thr.require_align and p.align_mode == "none":
        return False
    if obs.align_score + 1e-12 < thr.min_align_score:
        # survey_anchor without survey / weak multi-source glue → honest unsolved
        return False
    return True


def coherence_score(obs: Observations, thr: JobThresholds, params: FreeParams) -> float:
    """Scalar 0..1 for trajectory logging (not commercial accept / not ROP).

    Multi-source: align_score already carries glue_score — do not double-count.
    """
    parts: list[float] = []
    parts.append(1.0 if obs.pin_ok else 0.0)
    parts.append(float(obs.export_ok_fraction))
    if obs.verify_ok is True:
        parts.append(1.0)
    elif obs.verify_ok is False:
        parts.append(0.0)
    else:
        parts.append(0.5)
    n_phys = obs.physics_n_ok + obs.physics_n_warn + obs.physics_n_fail
    if n_phys > 0:
        parts.append(1.0 - obs.physics_n_fail / n_phys)
    else:
        parts.append(0.5)
    # align_score is glue_score when multi-source; single term only
    parts.append(max(0.0, min(1.0, float(obs.align_score))))
    return float(sum(parts) / len(parts))
