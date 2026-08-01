"""Multi-well rotation group for Job Coherence OS (Mode C).

Pre-registered claim: a free-param config that certifies under the QC firewall
on well A must be re-run under the **same pin thresholds** on wells B…N.
Merit = fraction firewall_certified under rotation — never mean science score.

Pin ε / pack required set are never adapted per well. Explore residue is
reported but never sets ROTATION_PASS alone.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.types import FreeParams, JobThresholds

logger = logging.getLogger(__name__)

ROTATION_ONTOLOGY = "job_rotation_prereg_v1_not_acceptance_for_residue"
MANIFEST_KIND = "job_rotation_manifest"


def _utc_batch_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_rotation_manifest(path: Path | str) -> dict[str, Any]:
    """Load and lightly validate a rotation manifest JSON."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"rotation manifest not found: {p}")
    body = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise ValueError("manifest must be a JSON object")
    wells = body.get("wells")
    if not isinstance(wells, list) or len(wells) < 1:
        raise ValueError("manifest.wells must be a non-empty list")
    for i, w in enumerate(wells):
        if not isinstance(w, dict):
            raise ValueError(f"wells[{i}] must be an object")
        if not w.get("las") and not w.get("las_path"):
            raise ValueError(f"wells[{i}] requires 'las' path")
        if not w.get("well_id"):
            w["well_id"] = f"well_{i}"
    body.setdefault("kind", MANIFEST_KIND)
    body.setdefault("prereg_id", "rotation_v1")
    body.setdefault("ontology", ROTATION_ONTOLOGY)
    return body


def _params_from_manifest(manifest: dict[str, Any], well: dict[str, Any]) -> FreeParams:
    base = dict(manifest.get("free_params") or {})
    # Per-well free params may override pack/align only (still clamped); never pin.
    for k in (
        "align_mode",
        "window_scale",
        "channel_pack",
        "null_policy",
        "survey_gate",
        "regime_mode",
    ):
        if well.get(k) is not None:
            base[k] = well[k]
    return FreeParams(**{k: base[k] for k in base if k in FreeParams.__dataclass_fields__}).clamp()


def _thresholds_from_manifest(manifest: dict[str, Any]) -> JobThresholds:
    thr_d = dict(manifest.get("thresholds") or {})
    # Only known JobThresholds fields; pin config is identical for whole batch
    known = set(JobThresholds.__dataclass_fields__.keys())
    filtered = {k: v for k, v in thr_d.items() if k in known}
    return JobThresholds(**filtered)


def classify_rotation(
    well_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pre-registered branch from per-well firewall_certified counts."""
    n = len(well_rows)
    n_cert = sum(1 for r in well_rows if r.get("firewall_certified"))
    n_near = sum(1 for r in well_rows if r.get("firewall_near_miss"))
    n_solved = sum(1 for r in well_rows if r.get("solved"))
    if n == 0:
        branch = "ROTATION_FAIL"
    elif n_cert == n:
        branch = "ROTATION_PASS"
    elif n_cert == 0:
        branch = "ROTATION_FAIL"
    else:
        branch = "ROTATION_PARTIAL"
    return {
        "branch": branch,
        "n_wells": n,
        "n_firewall_certified": n_cert,
        "n_solved": n_solved,
        "n_near_miss": n_near,
        "certify_fraction": (n_cert / n) if n else 0.0,
        "near_miss_flag": n_near > 0,
        "verdicts_prereg": {
            "ROTATION_PASS": "all wells firewall_certified",
            "ROTATION_PARTIAL": "≥1 certified and ≥1 not",
            "ROTATION_FAIL": "zero firewall_certified",
            "NEAR_MISS_FLAG": "any well explore-promising ∧ certify-fail",
        },
    }


def run_job_rotation(
    manifest: dict[str, Any] | Path | str,
    *,
    out_root: Path | str,
    batch_id: str | None = None,
    max_rounds: int | None = None,
    max_rows: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute one Job OS OS-mode run per well; write ROTATION_REPORT.

    Pin thresholds are identical across wells (from manifest.thresholds).
    Free params base from manifest.free_params with optional per-well overrides
    for pack/align only — never pin fields.
    """
    if not isinstance(manifest, dict):
        manifest = load_rotation_manifest(manifest)
    else:
        # validate wells
        wells_check = manifest.get("wells") or []
        if len(wells_check) < 1:
            raise ValueError("manifest.wells must be non-empty")

    out_root = Path(out_root)
    bid = batch_id or _utc_batch_id()
    batch_dir = out_root / bid
    batch_dir.mkdir(parents=True, exist_ok=True)
    wells_dir = batch_dir / "wells"
    wells_dir.mkdir(parents=True, exist_ok=True)

    # Freeze manifest copy (no silent edit)
    man_path = batch_dir / "MANIFEST.json"
    man_body = dict(manifest)
    man_body["batch_id"] = bid
    man_body["frozen_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    man_path.write_text(json.dumps(man_body, indent=2) + "\n", encoding="utf-8")

    thr = _thresholds_from_manifest(manifest)
    thr_stamp = thr.to_dict()  # identical for all wells
    stability_k = max(1, int(manifest.get("stability_k") or 1))
    max_r = int(max_rounds if max_rounds is not None else manifest.get("max_rounds") or 6)
    # Live EDR often needs a row cap; pin ε remains batch-identical (not free)
    max_rows_i: int | None
    if max_rows is not None:
        max_rows_i = int(max_rows)
    elif manifest.get("max_rows") is not None:
        max_rows_i = int(manifest["max_rows"])
    else:
        max_rows_i = None
    with_regime = bool(manifest.get("with_regime", False))
    with_science = bool(manifest.get("with_science", False))
    with_dynamical_topology = bool(manifest.get("with_dynamical_topology", False))
    topo_stability = bool(manifest.get("topo_stability", False))

    well_rows: list[dict[str, Any]] = []
    if dry_run:
        for w in manifest["wells"]:
            las = w.get("las") or w.get("las_path")
            well_rows.append(
                {
                    "well_id": w.get("well_id"),
                    "las": str(las),
                    "dry_run": True,
                    "solved": None,
                    "firewall_certified": None,
                    "firewall_near_miss": None,
                    "status": "dry_run",
                }
            )
        classification = classify_rotation([])
        classification["branch"] = "DRY_RUN"
        report = _build_report(
            batch_id=bid,
            batch_dir=batch_dir,
            manifest=man_body,
            thr_stamp=thr_stamp,
            well_rows=well_rows,
            classification=classification,
            dry_run=True,
        )
        _write_report(batch_dir, report)
        return report

    for w in manifest["wells"]:
        well_id = str(w.get("well_id") or "well")
        las = Path(w.get("las") or w.get("las_path"))
        mp = w.get("micropulse") or w.get("micropulse_path")
        survey = w.get("survey") or w.get("survey_path")
        params = _params_from_manifest(manifest, w)
        well_out = wells_dir / well_id
        well_out.mkdir(parents=True, exist_ok=True)
        logger.info(
            "rotation well_id=%s las=%s pack=%s thr_depth_eps=%s",
            well_id,
            las,
            params.channel_pack,
            thr.depth_mono_eps,
        )
        try:
            result = run_job_coherence_loop(
                las_path=las,
                out_root=well_out,
                initial=params,
                thresholds=thr,  # same pin config every well
                max_rounds=max_r,
                micropulse_path=Path(mp) if mp else None,
                survey_path=Path(survey) if survey else None,
                stability_k=stability_k,
                os_mode=True,
                with_regime=with_regime or bool(w.get("with_regime")),
                with_science=with_science or bool(w.get("with_science")),
                with_dynamical_topology=with_dynamical_topology
                or bool(w.get("with_dynamical_topology")),
                topo_stability=topo_stability or bool(w.get("topo_stability")),
                max_rows=max_rows_i,
                run_id=None,
            )
            row = {
                "well_id": well_id,
                "las": str(las.resolve()) if las.is_file() else str(las),
                "micropulse": str(mp) if mp else None,
                "survey": str(survey) if survey else None,
                "run_id": result.get("run_id"),
                "out_root": result.get("out_root"),
                "solved": bool(result.get("solved")),
                "stop_reason": result.get("stop_reason"),
                "n_rounds": result.get("n_rounds"),
                "final_params": result.get("final_params"),
                "firewall_certified": bool(result.get("firewall_certified")),
                "firewall_near_miss": bool(result.get("firewall_near_miss")),
                "firewall_path": result.get("firewall_path"),
                "partner_recipe": result.get("partner_recipe"),
                "explore_looks_promising": (
                    (result.get("firewall") or {}).get("explore") or {}
                ).get("looks_promising"),
                "near_miss_verdict": (
                    (result.get("firewall") or {}).get("near_miss") or {}
                ).get("verdict"),
                "status": "ok",
                "error": None,
                # stamp pin config used (must match batch thr)
                "pin_config_depth_mono_eps": thr.depth_mono_eps,
                "pin_config_max_depth_mono_violations": thr.max_depth_mono_violations,
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("rotation well failed well_id=%s", well_id)
            row = {
                "well_id": well_id,
                "las": str(las),
                "solved": False,
                "firewall_certified": False,
                "firewall_near_miss": False,
                "status": "error",
                "error": str(exc),
                "pin_config_depth_mono_eps": thr.depth_mono_eps,
            }
        well_rows.append(row)

    classification = classify_rotation(well_rows)
    # Pin identity check across successful wells
    eps_set = {
        r.get("pin_config_depth_mono_eps")
        for r in well_rows
        if r.get("pin_config_depth_mono_eps") is not None
    }
    pin_identical = len(eps_set) <= 1

    report = _build_report(
        batch_id=bid,
        batch_dir=batch_dir,
        manifest=man_body,
        thr_stamp=thr_stamp,
        well_rows=well_rows,
        classification=classification,
        dry_run=False,
        pin_identical=pin_identical,
    )
    _write_report(batch_dir, report)
    return report


def _build_report(
    *,
    batch_id: str,
    batch_dir: Path,
    manifest: dict[str, Any],
    thr_stamp: dict[str, Any],
    well_rows: list[dict[str, Any]],
    classification: dict[str, Any],
    dry_run: bool,
    pin_identical: bool = True,
) -> dict[str, Any]:
    return {
        "kind": "job_rotation_report",
        "ontology": ROTATION_ONTOLOGY,
        "prereg_id": manifest.get("prereg_id", "rotation_v1"),
        "batch_id": batch_id,
        "batch_dir": str(batch_dir.resolve()),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "not_acceptance": True,  # residue metrics in wells; branch is operational claim
        "pin_writable": False,
        "pin_thresholds_batch": thr_stamp,
        "pin_identical_across_wells": pin_identical,
        "dry_run": dry_run,
        "classification": classification,
        "branch": classification.get("branch"),
        "wells": well_rows,
        "laws": [
            "Same pin thresholds for every well in the batch.",
            "ROTATION_* branch from firewall_certified counts only.",
            "Science/topo/λ1 are explore residue — never set ROTATION_PASS alone.",
            "Near-miss flag is doctrine tooth (agreement ≠ verification).",
            "Never λ=γ; never retune pin mid-batch.",
        ],
        "bridge": {
            "design": "docs/superpowers/specs/2026-07-31-dual-stalk-ops-bridge-design.md",
            "firewall": "realm/job_os/firewall.py",
            "sister_kernel": "GATE_KERNEL ROTATION GROUP slot",
        },
        "note": (
            "Multi-well rotation prereg v1. Commercial per-well seal remains "
            "pin + fixed-point (FIREWALL certify). This report is the rotation claim."
        ),
    }


def _write_report(batch_dir: Path, report: dict[str, Any]) -> None:
    (batch_dir / "ROTATION_REPORT.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    cls = report.get("classification") or {}
    lines = [
        "# Job OS multi-well rotation report",
        "",
        f"- **batch_id:** `{report.get('batch_id')}`",
        f"- **branch:** `{report.get('branch')}`",
        f"- **prereg_id:** `{report.get('prereg_id')}`",
        f"- **pin_identical:** {report.get('pin_identical_across_wells')}",
        f"- **n_wells:** {cls.get('n_wells')}  "
        f"**certified:** {cls.get('n_firewall_certified')}  "
        f"**near_miss:** {cls.get('n_near_miss')}",
        f"- **certify_fraction:** {cls.get('certify_fraction')}",
        "",
        "## Pre-registered branches",
        "",
        "- ROTATION_PASS — all wells firewall_certified",
        "- ROTATION_PARTIAL — mixed",
        "- ROTATION_FAIL — zero certified",
        "- NEAR_MISS_FLAG — any explore-promising ∧ certify-fail",
        "",
        "Residue metrics (science/topo) never set the branch alone.",
        "",
        "| well_id | solved | fw_certified | near_miss | stop | path |",
        "|---------|:------:|:------------:|:---------:|------|------|",
    ]
    for w in report.get("wells") or []:
        lines.append(
            f"| `{w.get('well_id')}` | {w.get('solved')} | "
            f"{w.get('firewall_certified')} | {w.get('firewall_near_miss')} | "
            f"`{w.get('stop_reason') or w.get('status')}` | "
            f"`{w.get('out_root') or ''}` |"
        )
    lines.append("")
    (batch_dir / "ROTATION_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
