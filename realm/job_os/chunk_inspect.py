"""Out-of-core chunk inspect for Job OS (Stalk D / RLM pattern).

Transfer from: ACADEMIC/2512.24601v1.pdf (Recursive Language Models) —
prompt/data as external env; peek/slice programmatically; recursive budget.

Here: stream LAS rows in depth/time chunks, per-chunk pin/observe stats,
aggregate without requiring full-array science on huge files.

Never retunes pin. Aggregates feed the same Job OS observe path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from realm.job_os.ingest_las import parse_las
from realm.job_os.pin import verify_job_pin
from realm.kb_geometry.science_annex import attach_science_theory

KB_SOURCE = "ACADEMIC/2512.24601v1.pdf (RLM) — out-of-core inspect pattern"
TRANSFER_NOTE = (
    "LAS path as external store; chunked peek/aggregate; no required LLM"
)


def iter_las_chunks(
    series: dict[str, Any],
    *,
    chunk_rows: int = 500,
    max_chunks: int = 32,
) -> Iterator[dict[str, Any]]:
    """Yield shallow row-slices of a parsed series (views as new lists)."""
    n = int(series.get("n_rows") or 0)
    chunk_rows = max(1, int(chunk_rows))
    max_chunks = max(1, int(max_chunks))
    if n <= 0:
        return
    depths = list(series.get("depths") or [])
    channels = series.get("channels") or {}
    n_chunks = min(max_chunks, (n + chunk_rows - 1) // chunk_rows)
    for ci in range(n_chunks):
        lo = ci * chunk_rows
        hi = min(n, lo + chunk_rows)
        if lo >= n:
            break
        ch_slice: dict[str, list[Any]] = {}
        for name, arr in channels.items():
            a = list(arr)
            # only slice surface-aligned channels
            if len(a) == n:
                ch_slice[name] = a[lo:hi]
            else:
                ch_slice[name] = a  # presence-only fiber, pass through
        yield {
            "chunk_index": ci,
            "lo": lo,
            "hi": hi,
            "n_rows": hi - lo,
            "depths": depths[lo:hi] if len(depths) == n else depths,
            "channels": ch_slice,
            "units": series.get("units") or {},
            "curve_names": series.get("curve_names") or [],
            "null_value": series.get("null_value"),
            "source_path": series.get("source_path"),
            "depth_key": series.get("depth_key"),
            "wrap": series.get("wrap"),
            "channel_pack": series.get("channel_pack"),
            "pack_required": series.get("pack_required"),
            "parent_n_rows": n,
        }


def inspect_chunk(
    chunk: dict[str, Any],
    *,
    pack: str = "surface_min",
    depth_mono_eps: float = 1e-6,
    max_depth_mono_violations: int = 0,
) -> dict[str, Any]:
    """Pin + lightweight stats for one chunk (no free-param negotiate)."""
    pin = verify_job_pin(
        chunk,
        pack=pack,
        depth_mono_eps=float(depth_mono_eps),
        max_depth_mono_violations=int(max_depth_mono_violations),
    )
    channels = chunk.get("channels") or {}
    n_ch = len(channels)
    n_null = 0
    for arr in channels.values():
        if not isinstance(arr, list):
            continue
        for x in arr:
            if x is None:
                n_null += 1
    return {
        "chunk_index": chunk.get("chunk_index"),
        "lo": chunk.get("lo"),
        "hi": chunk.get("hi"),
        "n_rows": chunk.get("n_rows"),
        "pin_ok": bool(pin.get("ok")),
        "pin_hard_ok": bool(pin.get("hard_ok", pin.get("ok"))),
        "pin_pack_ok": bool(pin.get("pack_ok", True)),
        "n_channels": n_ch,
        "n_null_cells": n_null,
        "pin": {
            "ok": pin.get("ok"),
            "hard_ok": pin.get("hard_ok"),
            "pack_ok": pin.get("pack_ok"),
            "reasons": pin.get("reasons"),
        },
    }


def aggregate_chunk_inspect(
    chunk_reports: list[dict[str, Any]],
    *,
    parent_n_rows: int,
    chunk_rows: int,
    max_chunks: int,
    source_path: str | None = None,
) -> dict[str, Any]:
    """Merge per-chunk pin stats into one inspect report."""
    n = len(chunk_reports)
    n_pin_ok = sum(1 for c in chunk_reports if c.get("pin_ok"))
    n_hard_fail = sum(1 for c in chunk_reports if not c.get("pin_hard_ok"))
    covered = sum(int(c.get("n_rows") or 0) for c in chunk_reports)
    report = {
        "kind": "chunk_inspect",
        "enabled": True,
        "kb_source": KB_SOURCE,
        "transfer_note": TRANSFER_NOTE,
        "not_acceptance": True,
        "ontology": "job_chunk_inspect_not_lambda_eq_gamma",
        "source_path": source_path,
        "parent_n_rows": int(parent_n_rows),
        "chunk_rows": int(chunk_rows),
        "max_chunks": int(max_chunks),
        "n_chunks": n,
        "rows_covered": int(covered),
        "coverage_frac": float(covered / parent_n_rows) if parent_n_rows else 0.0,
        "n_chunks_pin_ok": int(n_pin_ok),
        "n_chunks_hard_fail": int(n_hard_fail),
        "all_hard_ok": n_hard_fail == 0 and n > 0,
        "chunks": chunk_reports,
        "disclaimers": [
            "Chunk inspect is out-of-core measurement; not ACCEPTANCE.",
            "Never retunes QC pin.",
            "Full-job SOLVED still requires cycle fixed-point under pin.",
        ],
    }
    return attach_science_theory(report, split="unspecified")


def run_las_chunk_inspect(
    las_path: Path | str,
    *,
    chunk_rows: int = 500,
    max_chunks: int = 32,
    pack: str = "surface_min",
    depth_mono_eps: float = 1e-6,
    max_depth_mono_violations: int = 0,
    out_path: Path | str | None = None,
) -> dict[str, Any]:
    """Parse LAS once, walk chunks, write optional JSON report."""
    series = parse_las(las_path)
    parent_n = int(series.get("n_rows") or 0)
    reports: list[dict[str, Any]] = []
    for chunk in iter_las_chunks(
        series, chunk_rows=chunk_rows, max_chunks=max_chunks
    ):
        reports.append(
            inspect_chunk(
                chunk,
                pack=pack,
                depth_mono_eps=depth_mono_eps,
                max_depth_mono_violations=max_depth_mono_violations,
            )
        )
    agg = aggregate_chunk_inspect(
        reports,
        parent_n_rows=parent_n,
        chunk_rows=chunk_rows,
        max_chunks=max_chunks,
        source_path=str(series.get("source_path") or las_path),
    )
    # If full file fits in one chunk, note equivalence
    if parent_n <= chunk_rows:
        agg["notes"] = list(agg.get("notes") or []) + ["single_chunk_full_file"]
    if out_path is not None:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(agg, indent=2) + "\n", encoding="utf-8")
        agg["report_path"] = str(p.resolve())
    return agg
