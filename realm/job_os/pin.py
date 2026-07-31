"""QC / SOP pin for oilfield job coherence — locked, never free-param.

Invariants checked every cycle:
  - depth monotonic on depth-indexed series (tolerance ε_d)
  - required channel set present for selected channel_pack
  - unit sanity (known units; no silent inversion)

NEVER retune pin mid-run for score. NEVER invent surveys or reorder depth.
"""

from __future__ import annotations

from typing import Any

from realm.job_os.types import PACK_REQUIRED

# Known unit tokens (case-insensitive). Missing/unknown → warn, not hard fail
# unless inverted pair detected.
_KNOWN_UNITS = {
    "FT",
    "M",
    "KLBF",
    "LBF",
    "KLB",
    "RPM",
    "SPM",
    "PSI",
    "KPA",
    "BAR",
    "KLBF.FT",
    "FT-LBF",
    "N.M",
    "NM",
    "DEG",
    "GAPI",
    "",
}

# Obvious unit inversion pairs (unit present that contradicts depth unit family)
_DEPTH_UNIT_FAMILIES = {
    "FT": "imperial_depth",
    "M": "metric_depth",
}


def verify_job_pin(
    series: dict[str, Any],
    pack: str = "surface_min",
    *,
    depth_mono_eps: float = 1e-6,
) -> dict[str, Any]:
    """Verify QC pin against ingested series.

    Parameters
    ----------
    series :
        Output of parse_las / adapter: must include ``depths`` (array-like),
        ``channels`` (dict mnemonic -> array), optional ``units`` (mnemonic -> str),
        optional ``null_value``.
    pack :
        channel_pack name selecting required mnemonics.
    depth_mono_eps :
        Locked tolerance for non-decreasing depth (config, not free param).

    Returns
    -------
    dict with at least ``ok`` (bool) and ``reasons`` (list[str]).
    """
    reasons: list[str] = []
    details: dict[str, Any] = {
        "pack": pack,
        "depth_mono_eps": float(depth_mono_eps),
        "ontology": "job_qc_pin_not_rop_score",
    }

    channels = dict(series.get("channels") or {})
    # Normalize keys to upper
    channels_u = {str(k).upper(): v for k, v in channels.items()}
    depths = series.get("depths")
    if depths is None and "DEPT" in channels_u:
        depths = channels_u["DEPT"]
    if depths is None and "DEPTH" in channels_u:
        depths = channels_u["DEPTH"]

    # --- required channels ---
    required = PACK_REQUIRED.get(str(pack).lower().strip(), PACK_REQUIRED["surface_min"])
    present = []
    missing = []
    for name in required:
        key = name.upper()
        if key == "DEPT":
            # DEPT satisfied by depths vector or DEPT/DEPTH channel
            if depths is not None or "DEPT" in channels_u or "DEPTH" in channels_u:
                present.append(key)
            else:
                missing.append(key)
            continue
        if key in channels_u and channels_u[key] is not None:
            arr = channels_u[key]
            try:
                n = len(arr)
            except TypeError:
                n = 0
            if n > 0:
                present.append(key)
            else:
                missing.append(key)
        else:
            missing.append(key)

    details["required"] = list(required)
    details["present"] = present
    details["missing"] = missing
    if missing:
        reasons.append(f"missing_channels:{','.join(missing)}")

    # --- depth monotonic ---
    depth_mono_ok = True
    n_depth = 0
    n_violations = 0
    if depths is None:
        depth_mono_ok = False
        reasons.append("depth_missing")
    else:
        try:
            depth_list = [float(x) for x in depths]
        except (TypeError, ValueError):
            depth_mono_ok = False
            reasons.append("depth_not_numeric")
            depth_list = []
        n_depth = len(depth_list)
        eps = float(depth_mono_eps)
        for i in range(1, len(depth_list)):
            if depth_list[i] + eps < depth_list[i - 1]:
                n_violations += 1
        if n_violations > 0:
            depth_mono_ok = False
            reasons.append(f"depth_not_monotonic:violations={n_violations}")
        if n_depth < 1:
            depth_mono_ok = False
            if "depth_missing" not in reasons and "depth_not_numeric" not in reasons:
                reasons.append("depth_empty")

    details["depth_mono_ok"] = depth_mono_ok
    details["n_depth"] = n_depth
    details["n_mono_violations"] = n_violations

    # --- unit sanity ---
    units_raw = dict(series.get("units") or {})
    units = {str(k).upper(): str(v or "").upper().strip() for k, v in units_raw.items()}
    unit_sanity_ok = True
    unit_notes: list[str] = []
    # Depth unit if present
    depth_unit = units.get("DEPT") or units.get("DEPTH") or ""
    if depth_unit and depth_unit not in _KNOWN_UNITS:
        unit_notes.append(f"unknown_depth_unit:{depth_unit}")
        # unknown is warn unless clearly inverted
    # Check for simultaneous FT and M as depth (contradiction)
    # Channel-level: WOB with depth-like unit is suspicious
    for ch, u in units.items():
        if not u:
            continue
        if u not in _KNOWN_UNITS and ch not in ("DEPT", "DEPTH"):
            unit_notes.append(f"unknown_unit:{ch}={u}")
        # Inversion: depth channel with pressure unit
        if ch in ("DEPT", "DEPTH") and u in ("PSI", "KPA", "BAR"):
            unit_sanity_ok = False
            reasons.append(f"unit_inversion:depth_as_pressure:{u}")
        # WOB with depth unit
        if ch == "WOB" and u in ("FT", "M"):
            unit_sanity_ok = False
            reasons.append(f"unit_inversion:wob_as_depth:{u}")

    details["unit_sanity_ok"] = unit_sanity_ok
    details["unit_notes"] = unit_notes
    details["units"] = units

    ok = depth_mono_ok and not missing and unit_sanity_ok
    return {
        "ok": bool(ok),
        "reasons": reasons,
        "depth_mono_ok": depth_mono_ok,
        "unit_sanity_ok": unit_sanity_ok,
        "missing_channels": missing,
        "present_channels": present,
        "required_channels": list(required),
        "n_depth": n_depth,
        "details": details,
        "note": "QC pin locked; free-param negotiate never retunes pin thresholds",
    }
