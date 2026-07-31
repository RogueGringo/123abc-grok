"""MicroPulse memory CSV ingest for Job Coherence OS P2.

Real MicroPulse files use a header-skip layout:
  line 1: MicroPulse
  line 2: <Kind> Log   (Gamma, Shock, Vibe, Pulse, Telem, Temp, Flow, Survey, …)
  metadata key/value lines
  then a CSV header row (Time / RTC_TIME / …) and data rows.
  Some kinds insert a unit line after the header.

Joins available fibers (GAMMA, SHOCK, VIBE, PULSE, TELEM, TEMP, FLOW, …)
as downhole channel fibers onto the job manifold. Does NOT invent surveys
or depth when the file has none.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

# Known log kinds (filename / title). SURVEY is parsed but survey stalk is P3.
KNOWN_KINDS = (
    "GAMMA",
    "ROTGAMMA",
    "SHOCK",
    "VIBE",
    "PULSE",
    "TELEM",
    "TEMP",
    "FLOW",
    "SURVEY",
    "BABLFISH",
    "CONFIG",
    "DEBUG",
    "ERROR",
    "SYSTEM",
    "VOLTAGES",
    "ROUTE",
    "ENVIRONMENT_LIFETIME",
)

# Fibers that count as MWD downhole channel pack members (export/pin)
DOWNHOLE_FIBER_KINDS = ("GAMMA", "SHOCK", "VIBE", "PULSE", "TELEM", "TEMP", "FLOW")

# Canonical channel aliases promoted into the joined series for pack checks
_KIND_PRIMARY_CHANNEL: dict[str, str] = {
    "GAMMA": "GAMMA",
    "ROTGAMMA": "GAMMA",
    "SHOCK": "SHOCK",
    "VIBE": "VIBE",
    "PULSE": "PULSE",
    "TELEM": "TELEM",
    "TEMP": "TEMP",
    "FLOW": "FLOW",
}

_TIME_KEYS = (
    "RTC_TIME",
    "LOGTAG_RTC_TIME",
    "TIME",
    "CLOCK_TIME",
    "TIMESTAMP",
    "DATETIME",
)
_DEPTH_KEYS = ("DEPT", "DEPTH", "MD", "BIT_DEPTH", "HOLE_DEPTH", "TVD")

_TIME_FORMATS = (
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%d/%m/%Y %H:%M:%S",
)


def _kind_from_name(path: Path) -> str | None:
    name = path.stem.upper()
    # Prefer longest match (ENVIRONMENT_LIFETIME before ENVIRONMENT)
    for kind in sorted(KNOWN_KINDS, key=len, reverse=True):
        if f"_{kind}_" in f"_{name}_" or name.endswith(f"_{kind}") or name == kind:
            return kind
        if kind in name.split("_"):
            return kind
    return None


def _kind_from_title(title_line: str) -> str | None:
    t = (title_line or "").strip().upper()
    # "Gamma Log", "Shock Log", …
    t = t.replace(" LOG", "").replace("LOG", "").strip()
    for kind in sorted(KNOWN_KINDS, key=len, reverse=True):
        if kind in t.replace(" ", "_") or kind in t:
            return kind
    return None


def _parse_time(tok: str) -> float | None:
    """Parse timestamp to unix epoch seconds (float). None if not parseable."""
    s = (tok or "").strip().strip('"')
    if not s:
        return None
    # numeric epoch?
    try:
        v = float(s)
        # treat large numbers as epoch; tiny as not
        if v > 1e8:
            return v
    except ValueError:
        pass
    for fmt in _TIME_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.timestamp()
        except ValueError:
            continue
    return None


def _is_unit_line(parts: list[str]) -> bool:
    """Heuristic: unit row after header (e.g. 'MM/dd/yyyy hh:mm:ss, Celcius')."""
    if not parts:
        return False
    joined = " ".join(parts).lower()
    unitish = (
        "mm/dd",
        "yyyy",
        "hh:mm",
        "celcius",
        "celsius",
        "degrees",
        "gauss",
        "g rms",
        "standard=",
    )
    if any(u in joined for u in unitish):
        return True
    # Mostly non-numeric tokens
    numeric = 0
    for p in parts:
        try:
            float(p)
            numeric += 1
        except ValueError:
            pass
    return numeric == 0 and len(parts) >= 1


def _looks_like_header(parts: list[str]) -> bool:
    if not parts:
        return False
    first = parts[0].strip().upper().replace(" ", "_")
    if first in _TIME_KEYS or first in ("CLOCK_TICKS", "TIME"):
        return True
    # Header-ish if mostly alphabetic tokens
    alpha = sum(1 for p in parts if re.match(r"^[A-Za-z_][A-Za-z0-9_ \-./]*$", p.strip()))
    return alpha >= max(1, len(parts) // 2) and not _is_unit_line(parts)


def detect_kind(path: Path, title_lines: list[str]) -> str:
    k = _kind_from_name(path)
    if k:
        return k
    for line in title_lines[:5]:
        k = _kind_from_title(line)
        if k:
            return k
    return "UNKNOWN"


def parse_micropulse_csv(path: str | Path) -> dict[str, Any]:
    """Parse one MicroPulse CSV into a fiber dict.

    Returns
    -------
    dict
        kind, times (list[float|None] epoch), depths (list[float|None]),
        channels (dict[str, list]), n_rows, source_path, meta, header, units_row
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"MicroPulse CSV not found: {p}")

    text = p.read_text(encoding="utf-8", errors="replace")
    # Normalize newlines; keep raw for csv reader after header skip
    raw_lines = text.splitlines()

    title_lines: list[str] = []
    meta: dict[str, str] = {}
    header_idx: int | None = None
    header: list[str] = []
    units_row: list[str] | None = None

    for i, raw in enumerate(raw_lines):
        line = raw.strip()
        if not line:
            continue
        # CSV-split lightly for detection
        parts = next(csv.reader(io.StringIO(raw)))
        parts = [c.strip() for c in parts if c is not None]
        if not parts:
            continue

        if header_idx is None:
            if _looks_like_header(parts):
                header_idx = i
                header = [c.strip() for c in parts]
                # Optional unit line immediately after
                if i + 1 < len(raw_lines):
                    nxt_parts = next(csv.reader(io.StringIO(raw_lines[i + 1])))
                    nxt_parts = [c.strip() for c in nxt_parts]
                    if _is_unit_line(nxt_parts):
                        units_row = nxt_parts
                break
            # Still in preamble
            title_lines.append(line)
            if len(parts) >= 2 and parts[0].endswith(":"):
                key = parts[0].rstrip(":").strip()
                val = ",".join(parts[1:]).strip()
                meta[key] = val
            elif len(parts) >= 2 and ":" in parts[0]:
                key, _, rest = parts[0].partition(":")
                meta[key.strip()] = (rest + "," + ",".join(parts[1:])).strip(" ,")
            continue

    kind = detect_kind(p, title_lines)
    if header_idx is None or not header:
        return {
            "kind": kind,
            "times": [],
            "depths": [],
            "channels": {},
            "n_rows": 0,
            "source_path": str(p.resolve()),
            "meta": meta,
            "header": [],
            "units_row": None,
            "title_lines": title_lines,
            "note": "no_csv_header_found",
        }

    data_start = header_idx + 1
    if units_row is not None:
        data_start = header_idx + 2

    # Normalize header names
    colnames = [re.sub(r"\s+", "_", h.strip()).upper() for h in header]
    # Drop empty trailing names
    while colnames and not colnames[-1]:
        colnames.pop()

    cols: dict[str, list[Any]] = {name: [] for name in colnames}
    n_cols = len(colnames)

    for raw in raw_lines[data_start:]:
        if not raw.strip():
            continue
        parts = next(csv.reader(io.StringIO(raw)))
        parts = [c.strip() for c in parts]
        if not parts:
            continue
        # Skip accidental second unit/header echoes
        if _is_unit_line(parts) or _looks_like_header(parts):
            # only skip if looks non-data
            numeric = 0
            for tok in parts:
                try:
                    float(tok)
                    numeric += 1
                except ValueError:
                    if _parse_time(tok) is not None:
                        numeric += 1
            if numeric == 0:
                continue
        # Pad / trim
        if len(parts) < n_cols:
            parts = parts + [""] * (n_cols - len(parts))
        for j, name in enumerate(colnames):
            cols[name].append(parts[j] if j < len(parts) else "")

    n_rows = len(next(iter(cols.values()))) if cols else 0

    # Resolve time column
    time_key = None
    for cand in _TIME_KEYS:
        if cand in cols:
            time_key = cand
            break
    if time_key is None:
        for name in colnames:
            if "TIME" in name:
                time_key = name
                break

    times: list[float | None] = []
    if time_key:
        for tok in cols[time_key]:
            times.append(_parse_time(str(tok)))
    else:
        times = [None] * n_rows

    # Resolve depth column (often absent on memory logs)
    depth_key = None
    for cand in _DEPTH_KEYS:
        if cand in cols:
            depth_key = cand
            break
    depths: list[float | None] = []
    if depth_key:
        for tok in cols[depth_key]:
            try:
                depths.append(float(tok))
            except (TypeError, ValueError):
                depths.append(None)
    else:
        depths = [None] * n_rows

    # Numeric channels (exclude pure time text col; keep numeric parses)
    channels: dict[str, list[float | None]] = {}
    for name, arr in cols.items():
        if name == time_key:
            continue
        out: list[float | None] = []
        n_num = 0
        for tok in arr:
            try:
                out.append(float(tok))
                n_num += 1
            except (TypeError, ValueError):
                # leave non-numeric as None (bitstream strings etc.)
                out.append(None)
        # Keep channel if any numeric content OR it's a known depth key
        if n_num > 0 or name == depth_key:
            channels[name] = out

    # Promote a primary pack mnemonic for this kind when possible
    primary = _KIND_PRIMARY_CHANNEL.get(kind)
    if primary and primary not in channels:
        # Prefer name containing primary (GAMMA1 → GAMMA)
        for name, arr in channels.items():
            if primary in name or name.startswith(primary):
                channels[primary] = list(arr)
                break
        # SHOCK: use max abs of X/Y/Z if present
        if primary == "SHOCK" and primary not in channels:
            axes = [channels[a] for a in ("X_SHOCK", "Y_SHOCK", "Z_SHOCK") if a in channels]
            if axes:
                mags: list[float | None] = []
                for i in range(n_rows):
                    vals = []
                    for ax in axes:
                        if i < len(ax) and ax[i] is not None:
                            vals.append(abs(float(ax[i])))
                    mags.append(max(vals) if vals else None)
                channels["SHOCK"] = mags
        if primary == "VIBE" and primary not in channels:
            axes = [channels[a] for a in ("X_VIBE", "Y_VIBE", "Z_VIBE") if a in channels]
            if axes:
                mags = []
                for i in range(n_rows):
                    vals = []
                    for ax in axes:
                        if i < len(ax) and ax[i] is not None:
                            vals.append(abs(float(ax[i])))
                    mags.append(max(vals) if vals else None)
                channels["VIBE"] = mags
        if primary == "TEMP" and primary not in channels:
            for name, arr in channels.items():
                if "TEMP" in name:
                    channels["TEMP"] = list(arr)
                    break
        if primary == "FLOW" and primary not in channels:
            for name, arr in channels.items():
                if "FLOW" in name:
                    channels["FLOW"] = list(arr)
                    break
        if primary == "PULSE" and primary not in channels:
            for name, arr in channels.items():
                if "PULSE" in name or name == "PULSE":
                    channels["PULSE"] = list(arr)
                    break
        if primary == "TELEM" and primary not in channels:
            # Telem may be sparse numeric VALUE
            if "VALUE" in channels:
                channels["TELEM"] = list(channels["VALUE"])
            else:
                channels["TELEM"] = [1.0 if times[i] is not None else None for i in range(n_rows)]

    return {
        "kind": kind,
        "times": times,
        "depths": depths,
        "channels": channels,
        "n_rows": n_rows,
        "source_path": str(p.resolve()),
        "meta": meta,
        "header": colnames,
        "units_row": units_row,
        "title_lines": title_lines,
        "time_key": time_key,
        "depth_key": depth_key,
        "primary_channel": primary,
    }


def discover_micropulse_files(path: str | Path) -> list[Path]:
    """Return sorted CSV paths from a file or directory."""
    p = Path(path)
    if p.is_file():
        return [p]
    if not p.is_dir():
        raise FileNotFoundError(f"MicroPulse path not found: {p}")
    files = sorted(p.glob("*.csv")) + sorted(p.glob("*.CSV"))
    # de-dupe preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for f in files:
        key = str(f.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def load_micropulse_bundle(path: str | Path) -> dict[str, Any]:
    """Load all MicroPulse CSVs under path into a multi-fiber bundle.

    Returns
    -------
    dict
        fibers: dict[kind, fiber]
        kinds: list[str]
        n_fibers: int
        source_path: str
        times_union: list of all finite timestamps (sorted unique-ish)
        depths_union: list of all finite depths
        pack_channels: dict of promoted pack mnemonics → arrays
    """
    files = discover_micropulse_files(path)
    fibers: dict[str, dict[str, Any]] = {}
    pack_channels: dict[str, list[float | None]] = {}
    all_times: list[float] = []
    all_depths: list[float] = []
    sources: list[str] = []

    for f in files:
        fiber = parse_micropulse_csv(f)
        kind = str(fiber.get("kind") or "UNKNOWN")
        # If duplicate kind, keep first non-empty or last with more rows
        prev = fibers.get(kind)
        if prev is None or int(fiber.get("n_rows") or 0) > int(prev.get("n_rows") or 0):
            fibers[kind] = fiber
        sources.append(str(f.resolve()))
        for t in fiber.get("times") or []:
            if t is not None and t == t:
                all_times.append(float(t))
        for d in fiber.get("depths") or []:
            if d is not None and d == d:
                all_depths.append(float(d))
        # Promote primary pack channel
        primary = fiber.get("primary_channel") or _KIND_PRIMARY_CHANNEL.get(kind)
        if primary:
            chans = fiber.get("channels") or {}
            if primary in chans:
                pack_channels[primary] = list(chans[primary])
            elif kind == "ROTGAMMA" and "GAMMA" not in pack_channels:
                # already handled in parse
                pass

    all_times.sort()
    all_depths.sort()
    kinds = sorted(fibers.keys())
    return {
        "fibers": fibers,
        "kinds": kinds,
        "n_fibers": len(fibers),
        "source_path": str(Path(path).resolve()),
        "sources": sources,
        "times_union": all_times,
        "depths_union": all_depths,
        "pack_channels": pack_channels,
        "downhole_kinds_present": [
            k for k in DOWNHOLE_FIBER_KINDS if k in fibers or k in pack_channels
        ],
    }


def join_surface_micropulse(
    surface: dict[str, Any],
    mp_bundle: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge MicroPulse pack channels into surface series for pin/export.

    Surface depth skeleton is preserved. Downhole fibers are attached as
    additional channels (may have different length — pin only checks presence).
    """
    out = dict(surface)
    channels = {str(k).upper(): list(v) for k, v in (surface.get("channels") or {}).items()}
    units = {str(k).upper(): v for k, v in (surface.get("units") or {}).items()}

    if not mp_bundle:
        out["channels"] = channels
        out["units"] = units
        out["micropulse"] = None
        out["has_micropulse"] = False
        return out

    pack_ch = mp_bundle.get("pack_channels") or {}
    for name, arr in pack_ch.items():
        key = str(name).upper()
        channels[key] = list(arr)
        if key not in units:
            units[key] = ""

    # Also attach per-fiber raw channels under FIBER__CHANNEL to avoid collisions
    fiber_index: dict[str, Any] = {}
    for kind, fiber in (mp_bundle.get("fibers") or {}).items():
        fiber_index[kind] = {
            "n_rows": fiber.get("n_rows"),
            "source_path": fiber.get("source_path"),
            "time_key": fiber.get("time_key"),
            "depth_key": fiber.get("depth_key"),
            "header": fiber.get("header"),
            "n_times_finite": sum(1 for t in (fiber.get("times") or []) if t is not None),
            "n_depths_finite": sum(
                1 for d in (fiber.get("depths") or []) if d is not None and d == d
            ),
        }

    out["channels"] = channels
    out["units"] = units
    out["micropulse"] = {
        "kinds": list(mp_bundle.get("kinds") or []),
        "n_fibers": int(mp_bundle.get("n_fibers") or 0),
        "source_path": mp_bundle.get("source_path"),
        "sources": list(mp_bundle.get("sources") or []),
        "times_union": list(mp_bundle.get("times_union") or []),
        "depths_union": list(mp_bundle.get("depths_union") or []),
        "downhole_kinds_present": list(mp_bundle.get("downhole_kinds_present") or []),
        "pack_channels": sorted(pack_ch.keys()),
        "fibers": fiber_index,
    }
    out["has_micropulse"] = True
    # Surface times if present on LAS
    if "times" not in out:
        out["times"] = _surface_times(surface)
    return out


def _surface_times(surface: dict[str, Any]) -> list[float | None]:
    """Extract times from surface series if a TIME-like channel exists."""
    channels = {str(k).upper(): v for k, v in (surface.get("channels") or {}).items()}
    for key in _TIME_KEYS:
        if key in channels:
            out: list[float | None] = []
            for x in channels[key]:
                if x is None:
                    out.append(None)
                    continue
                if isinstance(x, (int, float)):
                    out.append(float(x))
                else:
                    out.append(_parse_time(str(x)))
            return out
    return []
