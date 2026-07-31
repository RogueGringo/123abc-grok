"""Minimal LAS 2.0 ingest adapter for Job Coherence OS P1.

Parses curve section + ASCII data; returns channel arrays + depths + units.
Stdlib only (no lasio required).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def parse_las(
    path: str | Path,
    *,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Parse a LAS 2.0 file into series dict for pin/observe.

    Parameters
    ----------
    max_rows
        Optional cap on ASCII data rows (out-of-core / huge-file inspect).
        Header curves still fully read; data stops after max_rows lines/chunks.

    Returns
    -------
    dict
        depths : list[float]
        channels : dict[str, list[float | None]]  (upper mnemonic keys)
        units : dict[str, str]
        null_value : float | None
        curve_names : list[str]  (order as in ~C)
        n_rows : int
        source_path : str
        wrap : bool
        max_rows_cap : int | None
        truncated : bool
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"LAS not found: {p}")

    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    row_cap = int(max_rows) if max_rows is not None else None

    section: str | None = None
    curve_names: list[str] = []
    units: dict[str, str] = {}
    null_value: float | None = -999.25
    wrap = False
    data_lines: list[str] = []
    well_meta: dict[str, str] = {}

    curve_re = re.compile(
        r"^\s*([A-Za-z0-9_]+)\s*\.([^\s:]*)\s*([^:]*)\s*:\s*(.*)$"
    )
    # Simpler: MNEM.UNIT  value : desc  OR  MNEM.UNIT : desc
    well_re = re.compile(
        r"^\s*([A-Za-z0-9_]+)\s*\.([^\s:]*)\s*([^:]*)\s*:\s*(.*)$"
    )

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("~"):
            tag = stripped[1:2].upper() if len(stripped) > 1 else ""
            # ~VERSION, ~WELL, ~CURVE, ~PARAMETER, ~OTHER, ~A
            up = stripped.upper()
            if up.startswith("~V"):
                section = "V"
            elif up.startswith("~W"):
                section = "W"
            elif up.startswith("~C"):
                section = "C"
            elif up.startswith("~P"):
                section = "P"
            elif up.startswith("~O"):
                section = "O"
            elif up.startswith("~A"):
                section = "A"
            else:
                section = "X"
            continue

        if section == "V":
            m = well_re.match(line)
            if m and m.group(1).upper() == "WRAP":
                wrap = m.group(3).strip().upper().startswith("Y")
        elif section == "W":
            m = well_re.match(line)
            if m:
                mnem = m.group(1).upper()
                unit = (m.group(2) or "").strip()
                val = (m.group(3) or "").strip()
                well_meta[mnem] = val
                if mnem == "NULL":
                    try:
                        null_value = float(val)
                    except ValueError:
                        pass
                if mnem in ("STRT", "STOP", "STEP") and unit:
                    # depth unit from well
                    pass
        elif section == "C":
            m = curve_re.match(line)
            if m:
                mnem = m.group(1).upper()
                unit = (m.group(2) or "").strip()
                curve_names.append(mnem)
                units[mnem] = unit
        elif section == "A":
            data_lines.append(stripped)
            # Early stop collecting ASCII when cap known (line-oriented WRAP=NO)
            if (
                row_cap is not None
                and not wrap
                and len(data_lines) >= row_cap
            ):
                break

    if not curve_names:
        raise ValueError(f"LAS has no curves: {p}")

    # Parse ASCII rows (WRAP=NO assumed for P1 fixture; basic wrap support)
    n_curves = len(curve_names)
    values: list[list[float | None]] = [[] for _ in range(n_curves)]
    null = null_value
    truncated = False

    def _to_float(tok: str) -> float | None:
        try:
            v = float(tok)
        except ValueError:
            return None
        if null is not None and abs(v - null) < 1e-9:
            return None
        return v

    if wrap:
        # Best-effort WRAP=YES: flatten tokens then chunk by n_curves.
        # P1 fixture uses WRAP=NO; wrapped support is partial (no multi-line
        # depth-first continuation beyond token stream chunking).
        tokens: list[str] = []
        for dl in data_lines:
            tokens.extend(dl.split())
        n_full = 0
        for i in range(0, len(tokens) - n_curves + 1, n_curves):
            if row_cap is not None and n_full >= row_cap:
                truncated = True
                break
            chunk = tokens[i : i + n_curves]
            if len(chunk) < n_curves:
                break
            for j, tok in enumerate(chunk):
                values[j].append(_to_float(tok))
            n_full += 1
    else:
        for di, dl in enumerate(data_lines):
            if row_cap is not None and di >= row_cap:
                truncated = True
                break
            parts = dl.split()
            if len(parts) < n_curves:
                # pad missing short rows as null (None)
                parts = parts + ["null"] * (n_curves - len(parts))
            for j in range(n_curves):
                values[j].append(_to_float(parts[j]))
        if row_cap is not None and len(data_lines) >= row_cap:
            # may have stopped collection early
            if len(data_lines) == row_cap:
                # ambiguous: exact cap — mark truncated only if file had more
                # (we cannot know without scanning further; leave flag if cap set
                # and n_rows == cap)
                pass

    channels: dict[str, list[float | None]] = {
        curve_names[j]: values[j] for j in range(n_curves)
    }

    # Depths: DEPT or first curve
    depth_key = None
    for cand in ("DEPT", "DEPTH", "MD"):
        if cand in channels:
            depth_key = cand
            break
    if depth_key is None:
        depth_key = curve_names[0]

    depths_raw = channels.get(depth_key) or []
    depths: list[float] = []
    for d in depths_raw:
        if d is None:
            depths.append(float("nan"))
        else:
            depths.append(float(d))

    n_rows = len(depths)
    if row_cap is not None and n_rows >= row_cap:
        truncated = True
    return {
        "depths": depths,
        "channels": channels,
        "units": units,
        "null_value": null_value,
        "curve_names": curve_names,
        "n_rows": n_rows,
        "source_path": str(p.resolve()),
        "wrap": wrap,
        "well_meta": well_meta,
        "depth_key": depth_key,
        "max_rows_cap": row_cap,
        "truncated": bool(truncated),
    }


def apply_null_policy(
    series: dict[str, Any],
    policy: str = "mark_only",
) -> dict[str, Any]:
    """Return a shallow-copied series with nulls handled per free param.

    drop: drop surface rows where any *surface-aligned* channel is null
    hold_last: forward-fill nulls on surface-aligned channels only
    mark_only: leave nulls as None (default)

    Surface-aligned = channel length equals len(depths) / n_rows.
    Length-mismatched MicroPulse fibers are presence-only until a real
    align/resample stalk exists; they must not drive surface row drops.
    """
    pol = (policy or "mark_only").lower().strip()
    channels = {k: list(v) for k, v in (series.get("channels") or {}).items()}
    depths = list(series.get("depths") or [])
    n = int(series.get("n_rows") or len(depths) or 0)
    if n <= 0:
        n = len(depths)

    def _is_surface_aligned(arr: list[Any]) -> bool:
        return len(arr) == n

    surface_keys = [k for k, arr in channels.items() if _is_surface_aligned(arr)]
    # Presence-only fibers (e.g. shorter MicroPulse pack channels)
    fiber_keys = [k for k in channels if k not in surface_keys]

    if pol == "mark_only":
        out = dict(series)
        out["channels"] = channels
        out["depths"] = depths
        out["null_policy_applied"] = pol
        out["null_policy_surface_channels"] = surface_keys
        out["null_policy_fiber_channels_skipped"] = fiber_keys
        return out

    if pol == "hold_last":
        for name in surface_keys:
            arr = channels[name]
            last: float | None = None
            for i in range(len(arr)):
                if arr[i] is None:
                    arr[i] = last
                else:
                    last = arr[i]
        # Leave fiber_keys untouched (not depth-row aligned)
        out = dict(series)
        out["channels"] = channels
        out["depths"] = depths
        out["null_policy_applied"] = pol
        out["null_policy_surface_channels"] = surface_keys
        out["null_policy_fiber_channels_skipped"] = fiber_keys
        return out

    if pol == "drop":
        keep: list[int] = []
        for i in range(n):
            row_ok = True
            if i < len(depths):
                row_ok = depths[i] == depths[i]  # not nan
            else:
                row_ok = False
            if not row_ok:
                continue
            # Only surface-aligned channels participate in the drop mask
            for name in surface_keys:
                arr = channels[name]
                if arr[i] is None:
                    row_ok = False
                    break
            if row_ok:
                keep.append(i)
        new_depths = [depths[i] for i in keep if i < len(depths)]
        new_channels: dict[str, list[Any]] = {}
        for k, arr in channels.items():
            if k in surface_keys:
                new_channels[k] = [arr[i] for i in keep]
            else:
                # Preserve mismatched MP fibers whole (presence-only)
                new_channels[k] = list(arr)
        out = dict(series)
        out["depths"] = new_depths
        out["channels"] = new_channels
        out["n_rows"] = len(new_depths)
        out["null_policy_applied"] = pol
        out["null_policy_surface_channels"] = surface_keys
        out["null_policy_fiber_channels_skipped"] = fiber_keys
        return out

    out = dict(series)
    out["null_policy_applied"] = pol
    return out


def select_channel_pack(
    series: dict[str, Any],
    pack: str = "surface_min",
) -> dict[str, Any]:
    """Filter channels to those relevant for pack (keeps DEPT always).

    P2: mwd_full keeps required surface + downhole fibers present;
    job_union keeps the full joined manifold (surface + MicroPulse).
    """
    from realm.job_os.types import DOWNHOLE_PACK_CHANNELS, PACK_REQUIRED

    pack_l = (pack or "surface_min").lower().strip()
    required = PACK_REQUIRED.get(pack_l, PACK_REQUIRED["surface_min"])
    channels = dict(series.get("channels") or {})
    channels_u = {str(k).upper(): v for k, v in channels.items()}

    if pack_l == "job_union":
        # keep all surface + downhole fibers
        selected = channels_u
    else:
        want = {r.upper() for r in required}
        want.add("DEPT")
        want.add("DEPTH")
        if pack_l == "mwd_full":
            # Keep any present downhole pack channels (joined MicroPulse)
            want.update(c.upper() for c in DOWNHOLE_PACK_CHANNELS)
        # surface_full etc. — also keep any present required
        selected = {k: v for k, v in channels_u.items() if k in want}
        # Always keep depth key
        dk = series.get("depth_key")
        if dk and dk in channels_u and dk not in selected:
            selected[dk] = channels_u[dk]

    out = dict(series)
    out["channels"] = selected
    out["channel_pack"] = pack_l
    out["pack_required"] = list(required)
    return out
