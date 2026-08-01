"""ToeStub Job OS tool handlers — firewall_read, job_audit, job_catalog.

job_run / job_rotation handlers land in later tasks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from realm.job_os.audit import audit_job_run, audit_rotation_batch
from realm.job_os.catalog import write_job_os_catalog
from realm.job_os.firewall import build_job_firewall
from toestub.envelope import build_envelope
from toestub.schemas import resolve_path


def tool_firewall_read(run_dir: str, *, include_explore: bool = False) -> dict:
    """Load FIREWALL.json or rebuild from COHERENCE.json; envelope with certified."""
    root = resolve_path(str(run_dir) if run_dir is not None else None)
    if root is None:
        return build_envelope(
            ok=False,
            surface="firewall_read: missing run_dir",
            certified=None,
            error="run_dir is required",
        )

    fw: dict[str, Any] | None = None
    fw_path = root / "FIREWALL.json"
    coh_path = root / "COHERENCE.json"

    if fw_path.is_file():
        try:
            fw = json.loads(fw_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return build_envelope(
                ok=False,
                surface="firewall_read: FIREWALL.json parse error",
                certified=None,
                paths={"run_dir": str(root), "firewall": str(fw_path)},
                error=f"FIREWALL.json parse failed: {exc}",
            )
    elif coh_path.is_file():
        try:
            coh = json.loads(coh_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return build_envelope(
                ok=False,
                surface="firewall_read: COHERENCE.json parse error",
                certified=None,
                paths={"run_dir": str(root), "coherence": str(coh_path)},
                error=f"COHERENCE.json parse failed: {exc}",
            )
        fw = build_job_firewall(
            result=coh,
            ledger=coh.get("ledger"),
            solved=coh.get("solved"),
            run_id=coh.get("run_id"),
        )
    else:
        return build_envelope(
            ok=False,
            surface="firewall_read: no FIREWALL or COHERENCE",
            certified=None,
            paths={"run_dir": str(root)},
            error=f"neither FIREWALL.json nor COHERENCE.json under {root}",
        )

    certified = bool(fw.get("certified")) if fw.get("certified") is not None else None
    near = fw.get("near_miss") or {}
    near_miss = near.get("near_miss") if isinstance(near, dict) else None
    surface = (
        f"firewall certified={certified} near_miss={near_miss} "
        f"run={root.name}"
    )
    explore = (fw.get("explore") if include_explore else None)
    paths: dict[str, Any] = {
        "run_dir": str(root.resolve() if root.exists() else root),
        "firewall": str(fw_path) if fw_path.is_file() else None,
        "coherence": str(coh_path) if coh_path.is_file() else None,
    }
    return build_envelope(
        ok=True,
        surface=surface,
        certified=certified,
        near_miss=bool(near_miss) if near_miss is not None else None,
        paths=paths,
        explore=explore,
        extra={"firewall": fw} if include_explore else None,
    )


def tool_job_audit(path: str, *, write_report: bool = False) -> dict:
    """Audit a Job OS run_dir or rotation batch_dir; optional AUDIT.json write."""
    root = resolve_path(str(path) if path is not None else None)
    if root is None:
        return build_envelope(
            ok=False,
            surface="job_audit: missing path",
            certified=None,
            error="path is required",
        )

    if (root / "ROTATION_REPORT.json").is_file():
        audit = audit_rotation_batch(root)
        branch = audit.get("branch")
        certified = True if branch == "ROTATION_PASS" else (
            False if branch in ("ROTATION_PARTIAL", "ROTATION_FAIL", "DRY_RUN") else None
        )
        near_miss = None
        surface = (
            f"rotation audit ok={audit.get('ok')} branch={branch} "
            f"certified={audit.get('n_firewall_certified')}/{audit.get('n_wells')}"
        )
    else:
        audit = audit_job_run(root)
        branch = None
        certified = audit.get("firewall_certified")
        if certified is not None:
            certified = bool(certified)
        near_miss = audit.get("near_miss")
        surface = (
            f"job audit ok={audit.get('ok')} certified={certified} "
            f"n_fail={audit.get('n_fail')} run={root.name}"
        )

    audit_path: Path | None = None
    if write_report:
        audit_path = root / "AUDIT.json"
        try:
            audit_path.write_text(
                json.dumps(audit, indent=2) + "\n", encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            return build_envelope(
                ok=False,
                surface="job_audit: failed to write AUDIT.json",
                certified=certified if isinstance(certified, bool) else None,
                near_miss=bool(near_miss) if near_miss is not None else None,
                branch=branch,
                paths={"path": str(root)},
                error=f"AUDIT.json write failed: {exc}",
                extra={"findings": audit.get("findings"), "audit": audit},
            )

    paths: dict[str, Any] = {
        "path": str(root.resolve() if root.exists() else root),
    }
    if audit_path is not None:
        paths["audit"] = str(audit_path)
    if (root / "ROTATION_REPORT.json").is_file():
        paths["rotation_report"] = str(root / "ROTATION_REPORT.json")

    return build_envelope(
        ok=bool(audit.get("ok")),
        surface=surface,
        certified=certified if isinstance(certified, bool) else None,
        near_miss=bool(near_miss) if near_miss is not None else None,
        branch=branch,
        paths=paths,
        extra={
            "findings": audit.get("findings"),
            "n_fail": audit.get("n_fail"),
            "n_warn": audit.get("n_warn"),
            "audit": audit,
        },
    )


def tool_job_catalog(out_dir: str) -> dict:
    """Write Job OS INDEX.json/INDEX.md under out_dir; certified always null."""
    root = resolve_path(str(out_dir) if out_dir is not None else None)
    if root is None:
        return build_envelope(
            ok=False,
            surface="job_catalog: missing out_dir",
            certified=None,
            error="out_dir is required",
            extra={"not_acceptance": True},
        )

    try:
        body = write_job_os_catalog(root)
    except Exception as exc:  # noqa: BLE001
        return build_envelope(
            ok=False,
            surface="job_catalog: write failed",
            certified=None,
            paths={"out_dir": str(root)},
            error=str(exc),
            extra={"not_acceptance": True},
        )

    n_runs = int(body.get("n_runs") or 0)
    n_solved = int(body.get("n_solved") or 0)
    surface = f"catalog n_runs={n_runs} n_solved={n_solved} root={root.name}"
    return build_envelope(
        ok=True,
        surface=surface,
        certified=None,
        paths={
            "out_dir": str(root.resolve()),
            "index_json": str((root / "INDEX.json").resolve()),
            "index_md": str((root / "INDEX.md").resolve()),
        },
        extra={
            "not_acceptance": True,
            "n_runs": n_runs,
            "n_solved": n_solved,
            "catalog": body,
        },
    )
