"""Survey stalk (B) for Job Coherence OS P3.

Parse MicroPulse SURVEY CSV or a simple survey table (e.g. mini_survey.csv).
QC total G / MagF when present. Optional discrete holonomy/defect along MD
from successive Inc/Azi consistency — NEVER invent Inc/Azi values.

Free param survey_gate: off | qc_only | holonomy.
Pin bands are config (locked for a run); free params only gate depth.
"""

from __future__ import annotations

import csv
import io
import math
import re
from pathlib import Path
from typing import Any

# Default QC bands (locked pin-like config — not free params)
DEFAULT_TOTAL_G_CENTER = 1.0
DEFAULT_TOTAL_G_TOL = 0.05  # |G - 1| <= 0.05 → pass
DEFAULT_MAGF_LO = 0.15
DEFAULT_MAGF_HI = 1.20
# Discrete dogleg-ish jump (deg) between successive stations → defect
DEFAULT_DOGLEG_JUMP_DEG = 45.0
# Max |ΔInc| between stations without flagging (deg)
DEFAULT_DINC_JUMP_DEG = 30.0

_TIME_FORMATS = (
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
)


def _norm_header(name: str) -> str:
    s = re.sub(r"\s+", "_", (name or "").strip()).upper()
    s = s.replace("-", "_")
    return s


def _parse_float(tok: Any) -> float | None:
    if tok is None:
        return None
    s = str(tok).strip()
    if not s or s.upper() in ("NULL", "NAN", "NONE", "-999.25", "-9999"):
        return None
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    if v != v:  # nan
        return None
    return v


def _parse_time_epoch(tok: str) -> float | None:
    from datetime import datetime

    s = (tok or "").strip().strip('"')
    if not s:
        return None
    try:
        v = float(s)
        if v > 1e8:
            return v
    except ValueError:
        pass
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt).timestamp()
        except ValueError:
            continue
    return None


def _is_unit_line(parts: list[str]) -> bool:
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
        "standard=",
        "ft",
        "meters",
    )
    if any(u in joined for u in unitish):
        return True
    numeric = 0
    for p in parts:
        if _parse_float(p) is not None or _parse_time_epoch(p) is not None:
            numeric += 1
    return numeric == 0 and len(parts) >= 1


def _looks_like_survey_header(parts: list[str]) -> bool:
    if not parts:
        return False
    norms = [_norm_header(p) for p in parts]
    joined = " ".join(norms)
    # MicroPulse survey or simple table
    keys = (
        "INCLINATION",
        "AZIMUTH",
        "INC",
        "AZI",
        "TOTAL_GRAV",
        "TOTAL_G",
        "MAGF",
        "MD",
        "DEPT",
        "DEPTH",
    )
    hits = sum(1 for k in keys if k in norms or k in joined)
    if hits >= 2:
        return True
    # At least Inc+Azi aliases
    has_inc = any(x in ("INCLINATION", "INC", "INCL") for x in norms)
    has_azi = any(x in ("AZIMUTH", "AZI", "AZ") for x in norms)
    return has_inc and has_azi


def _pick_col(colnames: list[str], *candidates: str) -> str | None:
    upper = {c: c for c in colnames}
    for cand in candidates:
        if cand in upper:
            return cand
    # substring match
    for cand in candidates:
        for c in colnames:
            if cand in c:
                return c
    return None


def parse_survey_csv(path: str | Path) -> dict[str, Any]:
    """Parse a survey CSV (MicroPulse SURVEY or simple MD/Inc/Azi table).

    Never invents Inc/Azi — missing fields stay None.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"survey CSV not found: {p}")

    text = p.read_text(encoding="utf-8", errors="replace")
    raw_lines = text.splitlines()

    header_idx: int | None = None
    header: list[str] = []
    units_row: list[str] | None = None
    meta: dict[str, str] = {}
    title_lines: list[str] = []

    for i, raw in enumerate(raw_lines):
        line = raw.strip()
        if not line:
            continue
        parts = next(csv.reader(io.StringIO(raw)))
        parts = [c.strip() for c in parts if c is not None]
        if not parts:
            continue
        if header_idx is None:
            if _looks_like_survey_header(parts):
                header_idx = i
                header = [c.strip() for c in parts]
                if i + 1 < len(raw_lines):
                    nxt = next(csv.reader(io.StringIO(raw_lines[i + 1])))
                    nxt = [c.strip() for c in nxt]
                    if _is_unit_line(nxt):
                        units_row = nxt
                break
            title_lines.append(line)
            if len(parts) >= 2 and parts[0].endswith(":"):
                meta[parts[0].rstrip(":").strip()] = ",".join(parts[1:]).strip()
            continue

    if header_idx is None or not header:
        return {
            "stations": [],
            "n_stations": 0,
            "source_path": str(p.resolve()),
            "meta": meta,
            "header": [],
            "note": "no_survey_header_found",
            "kind": "SURVEY",
        }

    colnames = [_norm_header(h) for h in header]
    while colnames and not colnames[-1]:
        colnames.pop()

    data_start = header_idx + 1
    if units_row is not None:
        data_start = header_idx + 2

    md_key = _pick_col(colnames, "MD", "DEPT", "DEPTH", "MEASURED_DEPTH", "HOLE_DEPTH")
    inc_key = _pick_col(colnames, "INCLINATION", "INC", "INCL")
    azi_key = _pick_col(colnames, "AZIMUTH", "AZI", "AZ")
    magf_key = _pick_col(colnames, "MAGF", "MAG_F", "MAGNETIC_FIELD", "BTOTAL", "B_TOTAL")
    tg_key = _pick_col(
        colnames,
        "TOTAL_GRAV",
        "TOTAL_G",
        "TOTALG",
        "G_TOTAL",
        "GTOTAL",
        "TOTAL_GRAVITY",
    )
    time_key = _pick_col(colnames, "TIME", "RTC_TIME", "TIMESTAMP", "DATETIME")
    tvd_key = _pick_col(colnames, "TVD", "TRUE_VERTICAL_DEPTH")
    gtf_key = _pick_col(colnames, "GRAVITY_TOOL_FACE", "GTF", "GRAVITY_TOOLFACE")
    mtf_key = _pick_col(colnames, "MAGNETIC_TOOL_FACE", "MTF", "MAGNETIC_TOOLFACE")

    stations: list[dict[str, Any]] = []
    for raw in raw_lines[data_start:]:
        if not raw.strip():
            continue
        parts = next(csv.reader(io.StringIO(raw)))
        parts = [c.strip() for c in parts]
        if not parts:
            continue
        if _is_unit_line(parts) and not any(_parse_float(x) is not None for x in parts[1:]):
            continue
        # pad
        if len(parts) < len(colnames):
            parts = parts + [""] * (len(colnames) - len(parts))
        row = {colnames[j]: parts[j] if j < len(parts) else "" for j in range(len(colnames))}

        inc = _parse_float(row.get(inc_key or "", "")) if inc_key else None
        azi = _parse_float(row.get(azi_key or "", "")) if azi_key else None
        md = _parse_float(row.get(md_key or "", "")) if md_key else None
        magf = _parse_float(row.get(magf_key or "", "")) if magf_key else None
        total_g = _parse_float(row.get(tg_key or "", "")) if tg_key else None
        tvd = _parse_float(row.get(tvd_key or "", "")) if tvd_key else None
        t_epoch = None
        if time_key:
            t_epoch = _parse_time_epoch(str(row.get(time_key, "")))

        # Skip empty rows (no survey content)
        if inc is None and azi is None and md is None and total_g is None and magf is None:
            continue

        stations.append(
            {
                "md": md,
                "inc": inc,
                "azi": azi,
                "magf": magf,
                "total_g": total_g,
                "tvd": tvd,
                "time": t_epoch,
                "gtf": _parse_float(row.get(gtf_key or "", "")) if gtf_key else None,
                "mtf": _parse_float(row.get(mtf_key or "", "")) if mtf_key else None,
            }
        )

    return {
        "stations": stations,
        "n_stations": len(stations),
        "source_path": str(p.resolve()),
        "meta": meta,
        "header": colnames,
        "units_row": units_row,
        "title_lines": title_lines,
        "kind": "SURVEY",
        "keys": {
            "md": md_key,
            "inc": inc_key,
            "azi": azi_key,
            "magf": magf_key,
            "total_g": tg_key,
            "time": time_key,
        },
        "note": "parsed_survey_csv",
    }


def survey_from_micropulse_fiber(fiber: dict[str, Any]) -> dict[str, Any]:
    """Build a survey table from an already-parsed MicroPulse SURVEY fiber.

    Uses fiber channels (INCLINATION, AZIMUTH, MAGF, TOTAL_GRAV, …) when present.
    Does not invent Inc/Azi.
    """
    if not fiber:
        return {
            "stations": [],
            "n_stations": 0,
            "source_path": None,
            "kind": "SURVEY",
            "note": "empty_fiber",
        }
    ch = {str(k).upper(): v for k, v in (fiber.get("channels") or {}).items()}
    times = list(fiber.get("times") or [])
    depths = list(fiber.get("depths") or [])
    n = int(fiber.get("n_rows") or 0)
    if n <= 0:
        # derive from longest channel
        for arr in ch.values():
            try:
                n = max(n, len(arr))
            except TypeError:
                pass
        n = max(n, len(times), len(depths))

    def _col(*names: str) -> list[Any] | None:
        for name in names:
            if name in ch:
                return list(ch[name])
            for k, v in ch.items():
                if name in k:
                    return list(v)
        return None

    inc_arr = _col("INCLINATION", "INC", "INCL")
    azi_arr = _col("AZIMUTH", "AZI")
    magf_arr = _col("MAGF", "MAG_F", "BTOTAL")
    tg_arr = _col("TOTAL_GRAV", "TOTAL_G", "TOTALG", "G_TOTAL")
    md_arr = _col("MD", "DEPT", "DEPTH")
    if md_arr is None and any(d is not None for d in depths):
        md_arr = list(depths)

    stations: list[dict[str, Any]] = []
    for i in range(n):
        inc = _parse_float(inc_arr[i]) if inc_arr and i < len(inc_arr) else None
        azi = _parse_float(azi_arr[i]) if azi_arr and i < len(azi_arr) else None
        magf = _parse_float(magf_arr[i]) if magf_arr and i < len(magf_arr) else None
        total_g = _parse_float(tg_arr[i]) if tg_arr and i < len(tg_arr) else None
        md = _parse_float(md_arr[i]) if md_arr and i < len(md_arr) else None
        t = times[i] if i < len(times) else None
        if inc is None and azi is None and md is None and total_g is None and magf is None:
            continue
        stations.append(
            {
                "md": md,
                "inc": inc,
                "azi": azi,
                "magf": magf,
                "total_g": total_g,
                "tvd": None,
                "time": t,
                "gtf": None,
                "mtf": None,
            }
        )

    return {
        "stations": stations,
        "n_stations": len(stations),
        "source_path": fiber.get("source_path"),
        "kind": "SURVEY",
        "note": "from_micropulse_fiber",
        "header": list(fiber.get("header") or []),
    }


def load_survey(
    path: str | Path | None = None,
    *,
    mp_bundle: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Load survey from explicit path and/or MicroPulse bundle SURVEY fiber.

    Preference: explicit path if given; else SURVEY fiber in bundle.
    Returns None if no survey source available.
    """
    if path is not None:
        return parse_survey_csv(path)
    if mp_bundle:
        fibers = mp_bundle.get("fibers") or {}
        if "SURVEY" in fibers:
            return survey_from_micropulse_fiber(fibers["SURVEY"])
        # also accept lowercase / path-derived
        for k, fiber in fibers.items():
            if str(k).upper() == "SURVEY":
                return survey_from_micropulse_fiber(fiber)
    return None


def _sort_stations(stations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order by MD if available, else by time — never invent positions."""
    with_md = [s for s in stations if s.get("md") is not None]
    if len(with_md) == len(stations) and stations:
        return sorted(stations, key=lambda s: float(s["md"]))
    with_t = [s for s in stations if s.get("time") is not None]
    if len(with_t) == len(stations) and stations:
        return sorted(stations, key=lambda s: float(s["time"]))
    # partial MD: stable sort by md when present, keep relative order otherwise
    if with_md:
        indexed = list(enumerate(stations))
        indexed.sort(
            key=lambda iv: (
                0 if iv[1].get("md") is not None else 1,
                float(iv[1]["md"]) if iv[1].get("md") is not None else 0.0,
                iv[0],
            )
        )
        return [s for _, s in indexed]
    return list(stations)


def _angle_delta_deg(a: float, b: float) -> float:
    """Smallest signed difference b-a in degrees, wrapped to (-180, 180]."""
    d = b - a
    d = (d + 180.0) % 360.0 - 180.0
    return d


def qc_survey_stations(
    stations: list[dict[str, Any]],
    *,
    total_g_center: float = DEFAULT_TOTAL_G_CENTER,
    total_g_tol: float = DEFAULT_TOTAL_G_TOL,
    magf_lo: float = DEFAULT_MAGF_LO,
    magf_hi: float = DEFAULT_MAGF_HI,
) -> dict[str, Any]:
    """QC total G / MagF when present. Does not invent missing fields.

    Stations missing G or MagF are not counted as QC fails (not present → skip).
    """
    n = len(stations)
    qc_fail = 0
    fail_reasons: list[str] = []
    g_devs: list[float] = []
    magf_vals: list[float] = []
    n_g = 0
    n_magf = 0

    for i, s in enumerate(stations):
        station_fail = False
        tg = s.get("total_g")
        if tg is not None:
            n_g += 1
            dev = abs(float(tg) - float(total_g_center))
            g_devs.append(dev)
            if dev > float(total_g_tol) + 1e-12:
                station_fail = True
                fail_reasons.append(f"total_g_out_of_band:i={i}:|G-1|={dev:.4f}")
        magf = s.get("magf")
        if magf is not None:
            n_magf += 1
            mv = float(magf)
            magf_vals.append(mv)
            if mv < float(magf_lo) - 1e-12 or mv > float(magf_hi) + 1e-12:
                station_fail = True
                fail_reasons.append(f"magf_out_of_band:i={i}:MagF={mv:.4f}")
        if station_fail:
            qc_fail += 1

    max_g_dev = max(g_devs) if g_devs else None
    magf_min = min(magf_vals) if magf_vals else None
    magf_max = max(magf_vals) if magf_vals else None

    return {
        "n_stations": n,
        "qc_fail_count": qc_fail,
        "qc_ok": qc_fail == 0 and n > 0,
        "n_with_total_g": n_g,
        "n_with_magf": n_magf,
        "max_abs_g_minus_1": max_g_dev,
        "magf_min": magf_min,
        "magf_max": magf_max,
        "total_g_tol": float(total_g_tol),
        "magf_band": [float(magf_lo), float(magf_hi)],
        "fail_reasons": fail_reasons[:50],  # cap
        "note": "qc uses present G/MagF only; missing not invented",
    }


def discrete_holonomy_defects(
    stations: list[dict[str, Any]],
    *,
    dogleg_jump_deg: float = DEFAULT_DOGLEG_JUMP_DEG,
    dinc_jump_deg: float = DEFAULT_DINC_JUMP_DEG,
) -> dict[str, Any]:
    """Discrete holonomy / consistency defects along MD (or time order).

    Uses only present Inc/Azi — never invents values. Successive stations with
    both Inc and Azi contribute a dogleg-like angle; large jumps are defects.
    """
    ordered = _sort_stations(stations)
    defects: list[dict[str, Any]] = []
    n_pairs = 0
    cumulative_turn = 0.0
    used_md = all(s.get("md") is not None for s in ordered) and len(ordered) > 0

    prev = None
    prev_idx = -1
    for i, s in enumerate(ordered):
        inc = s.get("inc")
        azi = s.get("azi")
        if inc is None or azi is None:
            # cannot form frame — skip (honest; do not invent)
            continue
        if prev is None:
            prev = s
            prev_idx = i
            continue
        p_inc = prev.get("inc")
        p_azi = prev.get("azi")
        if p_inc is None or p_azi is None:
            prev = s
            prev_idx = i
            continue
        n_pairs += 1
        d_inc = float(inc) - float(p_inc)
        d_azi = _angle_delta_deg(float(p_azi), float(azi))
        # dogleg approximation (degrees): sqrt(dInc^2 + (dAzi*sin(I_avg))^2)
        i_avg = math.radians(0.5 * (float(inc) + float(p_inc)))
        dogleg = math.degrees(
            math.sqrt(
                math.radians(d_inc) ** 2
                + (math.radians(d_azi) * math.sin(i_avg)) ** 2
            )
        )
        cumulative_turn += dogleg
        flagged = abs(d_inc) > float(dinc_jump_deg) + 1e-12 or dogleg > float(
            dogleg_jump_deg
        ) + 1e-12
        if flagged:
            defects.append(
                {
                    "from_idx": prev_idx,
                    "to_idx": i,
                    "from_md": prev.get("md"),
                    "to_md": s.get("md"),
                    "d_inc": d_inc,
                    "d_azi": d_azi,
                    "dogleg_deg": dogleg,
                    "reason": (
                        "dinc_jump"
                        if abs(d_inc) > float(dinc_jump_deg)
                        else "dogleg_jump"
                    ),
                }
            )
        prev = s
        prev_idx = i

    return {
        "n_stations": len(ordered),
        "n_pairs_checked": n_pairs,
        "defect_count": len(defects),
        "defects": defects[:50],
        "cumulative_turn_deg": cumulative_turn,
        "order": "md" if used_md else "time_or_input",
        "dogleg_jump_deg": float(dogleg_jump_deg),
        "dinc_jump_deg": float(dinc_jump_deg),
        "holonomy_ok": len(defects) == 0 and n_pairs >= 0,
        "note": "discrete Inc/Azi consistency only; never invents surveys",
    }


def evaluate_survey(
    survey: dict[str, Any] | None,
    *,
    survey_gate: str = "off",
    total_g_tol: float = DEFAULT_TOTAL_G_TOL,
    magf_lo: float = DEFAULT_MAGF_LO,
    magf_hi: float = DEFAULT_MAGF_HI,
    dogleg_jump_deg: float = DEFAULT_DOGLEG_JUMP_DEG,
    dinc_jump_deg: float = DEFAULT_DINC_JUMP_DEG,
) -> dict[str, Any]:
    """Full survey stalk report for one cycle.

    survey_gate:
      off      — informational only; qc/holonomy still reported if stations exist
      qc_only  — QC pass required for stalk ok
      holonomy — QC + empty defect list required
    """
    gate = (survey_gate or "off").lower().strip()
    if gate not in ("off", "qc_only", "holonomy"):
        gate = "off"

    if not survey or int(survey.get("n_stations") or 0) <= 0:
        return {
            "present": False,
            "survey_gate": gate,
            "n_stations": 0,
            "qc_fail_count": 0,
            "qc_ok": False,
            "holonomy_ok": False,
            "defect_count": 0,
            "defects": [],
            "max_abs_g_minus_1": None,
            "magf_min": None,
            "magf_max": None,
            "stalk_ok": gate == "off",
            "notes": ["survey_missing"],
            "source_path": (survey or {}).get("source_path") if survey else None,
            "cumulative_turn_deg": 0.0,
        }

    stations = list(survey.get("stations") or [])
    qc = qc_survey_stations(
        stations,
        total_g_tol=total_g_tol,
        magf_lo=magf_lo,
        magf_hi=magf_hi,
    )
    hol = discrete_holonomy_defects(
        stations,
        dogleg_jump_deg=dogleg_jump_deg,
        dinc_jump_deg=dinc_jump_deg,
    )

    notes: list[str] = []
    if qc["qc_fail_count"] > 0:
        notes.append(f"survey_qc_fail:{qc['qc_fail_count']}")
    if hol["defect_count"] > 0:
        notes.append(f"survey_holonomy_defects:{hol['defect_count']}")
    if qc["n_with_total_g"] == 0 and qc["n_with_magf"] == 0:
        notes.append("survey_no_g_or_magf_channels")

    if gate == "off":
        stalk_ok = True
    elif gate == "qc_only":
        stalk_ok = bool(qc["qc_ok"])
    else:  # holonomy
        stalk_ok = bool(qc["qc_ok"]) and bool(hol["holonomy_ok"]) and hol["defect_count"] == 0

    if not stalk_ok:
        notes.append(f"survey_gate_{gate}_not_ok")

    return {
        "present": True,
        "survey_gate": gate,
        "n_stations": qc["n_stations"],
        "qc_fail_count": qc["qc_fail_count"],
        "qc_ok": qc["qc_ok"],
        "holonomy_ok": hol["holonomy_ok"] and hol["defect_count"] == 0,
        "defect_count": hol["defect_count"],
        "defects": hol["defects"],
        "max_abs_g_minus_1": qc["max_abs_g_minus_1"],
        "magf_min": qc["magf_min"],
        "magf_max": qc["magf_max"],
        "n_with_total_g": qc["n_with_total_g"],
        "n_with_magf": qc["n_with_magf"],
        "n_pairs_checked": hol["n_pairs_checked"],
        "cumulative_turn_deg": hol["cumulative_turn_deg"],
        "order": hol["order"],
        "stalk_ok": stalk_ok,
        "notes": notes,
        "source_path": survey.get("source_path"),
        "fail_reasons": qc.get("fail_reasons") or [],
    }
