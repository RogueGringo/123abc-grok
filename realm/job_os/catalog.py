"""Catalog Job Coherence OS runs under an out parent (INDEX.md + INDEX.json).

Scans for RUN.json / COHERENCE.json / TREND_ROLLUP / EOW ship stamps.
Informational index only — not ACCEPTANCE.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def scan_job_os_runs(root: Path | str) -> list[dict[str, Any]]:
    """List run directories under root (or root itself if it is a run)."""
    root = Path(root)
    if not root.is_dir():
        return []

    candidates: list[Path] = []
    if (root / "RUN.json").is_file() or (root / "COHERENCE.json").is_file():
        candidates.append(root)
    for child in sorted(root.iterdir(), reverse=True):
        if child.is_dir() and (
            (child / "RUN.json").is_file() or (child / "COHERENCE.json").is_file()
        ):
            candidates.append(child)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for run_dir in candidates:
        key = str(run_dir.resolve())
        if key in seen:
            continue
        seen.add(key)
        rows.append(_summarize_run(run_dir))
    return rows


def _summarize_run(run_dir: Path) -> dict[str, Any]:
    run: dict[str, Any] = {}
    coh: dict[str, Any] = {}
    trend: dict[str, Any] = {}
    chunk: dict[str, Any] = {}
    if (run_dir / "RUN.json").is_file():
        try:
            run = json.loads((run_dir / "RUN.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            run = {}
    if (run_dir / "COHERENCE.json").is_file():
        try:
            coh = json.loads((run_dir / "COHERENCE.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            coh = {}
    if (run_dir / "TREND_ROLLUP.json").is_file():
        try:
            trend = json.loads(
                (run_dir / "TREND_ROLLUP.json").read_text(encoding="utf-8")
            )
        except Exception:  # noqa: BLE001
            trend = {}
    if (run_dir / "CHUNK_INSPECT.json").is_file():
        try:
            chunk = json.loads(
                (run_dir / "CHUNK_INSPECT.json").read_text(encoding="utf-8")
            )
        except Exception:  # noqa: BLE001
            chunk = {}

    eow_status = coh.get("eow_ship_status") or run.get("eow_ship_status")
    if eow_status is None and (run_dir / "eow" / "SHIP.json").is_file():
        try:
            eow_status = json.loads(
                (run_dir / "eow" / "SHIP.json").read_text(encoding="utf-8")
            ).get("status")
        except Exception:  # noqa: BLE001
            eow_status = "present"

    fw: dict[str, Any] = {}
    if (run_dir / "FIREWALL.json").is_file():
        try:
            fw = json.loads((run_dir / "FIREWALL.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            fw = {}
    if not fw:
        fw = coh.get("firewall") or run.get("firewall") or {}
    fw_certified = coh.get("firewall_certified")
    if fw_certified is None:
        fw_certified = run.get("firewall_certified")
    if fw_certified is None and fw:
        fw_certified = fw.get("certified")
    fw_near = coh.get("firewall_near_miss")
    if fw_near is None and fw:
        fw_near = (fw.get("near_miss") or {}).get("near_miss")

    return {
        "run_id": run.get("run_id") or coh.get("run_id") or run_dir.name,
        "path": str(run_dir.resolve()),
        "status": run.get("status") or ("solved" if coh.get("solved") else "unknown"),
        "solved": bool(coh.get("solved")),
        "stop_reason": coh.get("stop_reason"),
        "n_rounds": coh.get("n_rounds"),
        "final_params": coh.get("final_params") or run.get("final_params"),
        "las_path": coh.get("las_path") or run.get("las_path"),
        "micropulse_path": coh.get("micropulse_path") or run.get("micropulse_path"),
        "with_regime": coh.get("with_regime") or run.get("with_regime"),
        "with_science": coh.get("with_science") or run.get("with_science"),
        "lambda_1_trend": trend.get("lambda_1_trend"),
        "lambda_1_delta": trend.get("lambda_1_delta"),
        "chunk_n": chunk.get("n_chunks"),
        "chunk_coverage": chunk.get("coverage_frac"),
        "eow_ship_status": eow_status,
        "partner_recipe": bool((run_dir / "PARTNER_RECIPE.json").is_file()),
        "has_trend_rollup": bool(trend),
        "firewall_certified": bool(fw_certified) if fw_certified is not None else None,
        "firewall_near_miss": bool(fw_near) if fw_near is not None else None,
        "has_firewall": bool(fw) or (run_dir / "FIREWALL.json").is_file(),
        "not_acceptance": True,
    }


def write_job_os_catalog(root: Path | str) -> dict[str, Any]:
    """Write INDEX.json + INDEX.md under root; return catalog body."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    runs = scan_job_os_runs(root)
    body = {
        "kind": "job_os_catalog",
        "ontology": "job_os_catalog_not_acceptance",
        "not_acceptance": True,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root.resolve()),
        "n_runs": len(runs),
        "n_solved": sum(1 for r in runs if r.get("solved")),
        "runs": runs,
        "note": (
            "Job OS run index only. Commercial success remains openable PDBs / "
            "glue+QC pin — not this catalog score."
        ),
    }
    (root / "INDEX.json").write_text(
        json.dumps(body, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Job Coherence OS catalog",
        "",
        f"- **root:** `{root}`",
        f"- **runs:** {body['n_runs']} (solved: {body['n_solved']})",
        f"- **generated:** {body['generated_utc']}",
        "",
        "Not ACCEPTANCE. Pin + fixed-point remain the commercial gates.",
        "",
        "| run_id | solved | fw_cert | near_miss | stop | rounds | λ1 | EOW | recipe |",
        "|--------|:------:|:-------:|:---------:|------|-------:|----|-----|:------:|",
    ]
    for r in runs:
        lines.append(
            f"| `{r.get('run_id')}` | {r.get('solved')} | "
            f"{r.get('firewall_certified')} | {r.get('firewall_near_miss')} | "
            f"`{r.get('stop_reason')}` | {r.get('n_rounds')} | "
            f"`{r.get('lambda_1_trend')}` | `{r.get('eow_ship_status')}` | "
            f"{r.get('partner_recipe')} |"
        )
    lines.append("")
    (root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    return body
