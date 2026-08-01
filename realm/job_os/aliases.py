"""Inherited channel dictionary — mnemonic aliases for pack / pin (C6).

Sheaf-for-meaning restriction (ground, don't invent): map vendor curve names
onto pack canonicals when the physical series already exists. Never fabricates
samples; never retunes pin ε.

Examples: WOBX/SWOB → WOB, TQA → TOR, SPPA → SPP, GAM/GRC → GAMMA.
"""

from __future__ import annotations

from typing import Any

# Canonical pack mnemonic → preferred source keys (first present with data wins).
# First entry is the canonical itself so existing files keep identity.
CHANNEL_ALIASES: dict[str, tuple[str, ...]] = {
    "DEPT": ("DEPT", "DEPTH", "MD", "MTTVD"),
    "WOB": ("WOB", "WOBX", "SWOB", "SOB"),
    "RPM": ("RPM", "RPM_P", "MRPM"),
    "TOR": ("TOR", "TQA", "TQX", "TORQUE", "MTOR"),
    "SPP": ("SPP", "SPPA", "SPRESS", "MPRS"),
    "SSSI": ("SSSI", "SSS_P", "SSS"),
    "GAMMA": ("GAMMA", "GAM", "GRC", "GR", "GRFET"),
}


def _has_data(arr: Any) -> bool:
    if arr is None:
        return False
    try:
        return len(arr) > 0
    except TypeError:
        return False


def apply_channel_aliases(series: dict[str, Any]) -> dict[str, Any]:
    """Copy vendor series onto missing canonical pack keys.

    Does not overwrite an existing non-empty canonical. Records mappings under
    ``alias_applied`` for ledger transparency (not ACCEPTANCE).
    """
    out = dict(series)
    channels = {str(k).upper(): v for k, v in (series.get("channels") or {}).items()}
    # preserve list identity copy for mutation safety on new keys only
    channels = {k: (list(v) if isinstance(v, list) else v) for k, v in channels.items()}
    units = {str(k).upper(): v for k, v in (series.get("units") or {}).items()}
    applied: list[dict[str, str]] = []

    for canon, sources in CHANNEL_ALIASES.items():
        if _has_data(channels.get(canon)):
            continue
        for src in sources:
            src_u = src.upper()
            if src_u == canon:
                continue
            if _has_data(channels.get(src_u)):
                channels[canon] = list(channels[src_u])
                if src_u in units and canon not in units:
                    units[canon] = units[src_u]
                applied.append({"canonical": canon, "from": src_u})
                break

    # Depth vector: if depths missing but DEPT/DEPTH filled via alias, expose depths
    depths = out.get("depths")
    depth_key = out.get("depth_key")
    if (depths is None or (isinstance(depths, list) and len(depths) == 0)) and _has_data(
        channels.get("DEPT")
    ):
        raw = channels["DEPT"]
        depths = []
        for d in raw:
            if d is None:
                depths.append(float("nan"))
            else:
                try:
                    depths.append(float(d))
                except (TypeError, ValueError):
                    depths.append(float("nan"))
        out["depths"] = depths
        depth_key = "DEPT"
    elif depth_key is None and "DEPT" in channels:
        depth_key = "DEPT"

    out["channels"] = channels
    out["units"] = units
    out["depth_key"] = depth_key or out.get("depth_key")
    out["alias_applied"] = applied
    out["alias_ontology"] = "job_channel_aliases_inherited_not_invented"
    out["not_acceptance"] = True
    return out
