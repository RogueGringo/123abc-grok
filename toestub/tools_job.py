"""ToeStub Job OS tool handlers — firewall_read, job_audit, job_catalog, job_run, job_rotation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from realm.job_os.audit import audit_job_run, audit_rotation_batch
from realm.job_os.catalog import write_job_os_catalog
from realm.job_os.firewall import build_job_firewall
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.rotation import run_job_rotation
from realm.job_os.types import FreeParams, JobThresholds
from toestub.envelope import build_envelope
from toestub.schemas import (
    check_allow_roots,
    get_allow_roots,
    get_repo_root,
    resolve_path,
    validate_free_params,
    validate_pin_config,
    ToeStubValidationError,
)


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


def tool_job_run(
    *,
    las_path: str,
    micropulse_path: str | None = None,
    survey_path: str | None = None,
    out_root: str | None = None,
    max_rounds: int = 6,
    stability_k: int = 1,
    free_params: dict | None = None,
    pin_config: dict | None = None,
    with_regime: bool = False,
    with_science: bool = False,
    with_dynamical_topology: bool = False,
    max_rows: int | None = None,
    eow_package: str | None = None,
    include_explore: bool = False,
) -> dict:
    """Run Job OS coherence loop (os_mode=True); envelope with firewall cert.

    free_params never enter JobThresholds; pin only via explicit pin_config.
    Validation errors and kernel exceptions become ok=False envelopes.
    """
    try:
        free = validate_free_params(free_params)
        pin = validate_pin_config(pin_config)
    except ToeStubValidationError as exc:
        return build_envelope(
            ok=False,
            surface="job_run: free/pin validation failed",
            certified=None,
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        return build_envelope(
            ok=False,
            surface="job_run: free/pin validation failed",
            certified=None,
            error=str(exc),
        )

    las = resolve_path(str(las_path) if las_path is not None else None)
    mp = resolve_path(str(micropulse_path) if micropulse_path is not None else None)
    survey = resolve_path(str(survey_path) if survey_path is not None else None)
    eow = resolve_path(str(eow_package) if eow_package is not None else None)
    if out_root is None or str(out_root).strip() == "":
        out = get_repo_root() / "out" / "job_os"
    else:
        out = resolve_path(str(out_root))
        if out is None:
            out = get_repo_root() / "out" / "job_os"

    allow = get_allow_roots()
    try:
        if las is not None:
            check_allow_roots(las, allow)
        if mp is not None:
            check_allow_roots(mp, allow)
        if survey is not None:
            check_allow_roots(survey, allow)
        if out is not None:
            check_allow_roots(out, allow)
        if eow is not None:
            check_allow_roots(eow, allow)
    except ToeStubValidationError as exc:
        return build_envelope(
            ok=False,
            surface="job_run: path not under allow_roots",
            certified=None,
            error=str(exc),
        )

    if las is None or not las.is_file():
        return build_envelope(
            ok=False,
            surface="job_run: LAS missing or not a file",
            certified=None,
            paths={"las_path": str(las) if las is not None else None},
            error=f"las_path required and must exist as a file (got {las})",
        )

    # FreeParams from free only; JobThresholds from pin only (never free keys).
    initial = FreeParams(**free)
    thresholds = JobThresholds(**pin)

    try:
        result = run_job_coherence_loop(
            las_path=las,
            micropulse_path=mp,
            survey_path=survey,
            out_root=out,
            initial=initial,
            thresholds=thresholds,
            max_rounds=int(max_rounds),
            stability_k=int(stability_k),
            os_mode=True,
            with_regime=bool(with_regime),
            with_science=bool(with_science),
            with_dynamical_topology=bool(with_dynamical_topology),
            max_rows=int(max_rows) if max_rows is not None else None,
            eow_package=eow,
        )
    except Exception as exc:  # noqa: BLE001
        return build_envelope(
            ok=False,
            surface="job_run: loop failed",
            certified=None,
            paths={
                "las_path": str(las),
                "out_root": str(out),
            },
            error=str(exc),
        )

    run_root = Path(str(result.get("out_root") or out))
    coh_path = run_root / "COHERENCE.json"
    fw_path = run_root / "FIREWALL.json"
    recipe_path = run_root / "PARTNER_RECIPE.json"
    # Prefer kernel-reported firewall_path when present
    fw_reported = result.get("firewall_path")
    if fw_reported:
        fw_path = Path(str(fw_reported))

    certified = result.get("firewall_certified")
    if certified is not None:
        certified = bool(certified)
    near_miss = result.get("firewall_near_miss")
    if near_miss is not None:
        near_miss = bool(near_miss)

    stop = result.get("stop_reason") or result.get("status")
    surface = (
        f"job_run certified={certified} near_miss={near_miss} "
        f"solved={result.get('solved')} stop={stop} run={run_root.name}"
    )

    paths: dict[str, Any] = {
        "out_root": str(run_root.resolve() if run_root.exists() else run_root),
        "las_path": str(las),
        "coherence": str(coh_path) if coh_path.is_file() else None,
        "firewall": str(fw_path) if fw_path.is_file() else (
            str(fw_path) if fw_path.exists() else None
        ),
        "partner_recipe": str(recipe_path) if recipe_path.is_file() else None,
    }
    rid = result.get("run_id")
    if rid is not None:
        paths["run_id"] = str(rid)

    # Ensure firewall path string even if is_file check races
    if paths.get("firewall") is None and result.get("firewall_path"):
        paths["firewall"] = str(result["firewall_path"])

    explore = None
    extra: dict[str, Any] | None = None
    if include_explore:
        fw = result.get("firewall")
        if isinstance(fw, dict):
            explore = fw.get("explore")
        extra = {
            "firewall": fw,
            "solved": result.get("solved"),
            "stop_reason": result.get("stop_reason"),
        }

    return build_envelope(
        ok=True,
        surface=surface,
        certified=certified if isinstance(certified, bool) else None,
        near_miss=near_miss if isinstance(near_miss, bool) else None,
        paths=paths,
        explore=explore,
        extra=extra,
    )


def tool_job_rotation(
    *,
    manifest_path: str | None = None,
    manifest: dict | None = None,
    out_root: str | None = None,
    dry_run: bool = False,
    max_rows: int | None = None,
    include_explore: bool = False,
) -> dict:
    """Run multi-well Job OS rotation; envelope with ROTATION_* branch.

    Exactly one of manifest_path or manifest is required. Kernel accepts
    dict or path. certified is True only when branch == ROTATION_PASS.
    """
    has_path = manifest_path is not None and str(manifest_path).strip() != ""
    has_body = manifest is not None
    if has_path == has_body:
        # both or neither
        return build_envelope(
            ok=False,
            surface="job_rotation: require exactly one of manifest_path or manifest",
            certified=None,
            error="exactly one of manifest_path or manifest is required",
        )

    if out_root is None or str(out_root).strip() == "":
        out = get_repo_root() / "out" / "rotation"
    else:
        out = resolve_path(str(out_root))
        if out is None:
            out = get_repo_root() / "out" / "rotation"

    allow = get_allow_roots()
    try:
        if out is not None:
            check_allow_roots(out, allow)
    except ToeStubValidationError as exc:
        return build_envelope(
            ok=False,
            surface="job_rotation: path not under allow_roots",
            certified=None,
            error=str(exc),
        )

    kernel_manifest: dict[str, Any] | Path
    if has_body:
        if not isinstance(manifest, dict):
            return build_envelope(
                ok=False,
                surface="job_rotation: manifest must be a dict",
                certified=None,
                error=f"manifest must be a dict, got {type(manifest).__name__}",
            )
        kernel_manifest = manifest
        # Optional allow_roots check on well LAS paths
        try:
            for w in (manifest.get("wells") or []):
                if not isinstance(w, dict):
                    continue
                las_raw = w.get("las") or w.get("las_path")
                if las_raw is None:
                    continue
                las_p = resolve_path(str(las_raw))
                if las_p is not None:
                    check_allow_roots(las_p, allow)
        except ToeStubValidationError as exc:
            return build_envelope(
                ok=False,
                surface="job_rotation: path not under allow_roots",
                certified=None,
                error=str(exc),
            )
    else:
        man_p = resolve_path(str(manifest_path))
        if man_p is None or not man_p.is_file():
            return build_envelope(
                ok=False,
                surface="job_rotation: manifest_path missing or not a file",
                certified=None,
                paths={"manifest_path": str(man_p) if man_p is not None else None},
                error=f"manifest_path required and must exist as a file (got {man_p})",
            )
        try:
            check_allow_roots(man_p, allow)
        except ToeStubValidationError as exc:
            return build_envelope(
                ok=False,
                surface="job_rotation: path not under allow_roots",
                certified=None,
                error=str(exc),
            )
        kernel_manifest = man_p

    try:
        report = run_job_rotation(
            kernel_manifest,
            out_root=out,
            dry_run=bool(dry_run),
            max_rows=int(max_rows) if max_rows is not None else None,
        )
    except Exception as exc:  # noqa: BLE001
        return build_envelope(
            ok=False,
            surface="job_rotation: kernel failed",
            certified=None,
            paths={"out_root": str(out)},
            error=str(exc),
        )

    branch = report.get("branch")
    certified = branch == "ROTATION_PASS"
    classification = report.get("classification") or {}
    near_miss = classification.get("near_miss_flag")
    if near_miss is not None:
        near_miss = bool(near_miss)

    batch_dir = Path(str(report.get("batch_dir") or out))
    rot_report = batch_dir / "ROTATION_REPORT.json"
    n_cert = classification.get("n_firewall_certified")
    n_wells = classification.get("n_wells")
    surface = (
        f"job_rotation branch={branch} certified={certified} "
        f"n_cert={n_cert}/{n_wells} batch={batch_dir.name}"
    )

    paths: dict[str, Any] = {
        "out_root": str(out.resolve() if out.exists() else out),
        "batch_dir": str(batch_dir.resolve() if batch_dir.exists() else batch_dir),
        "rotation_report": str(rot_report) if rot_report.is_file() else str(rot_report),
        "manifest": str(batch_dir / "MANIFEST.json")
        if (batch_dir / "MANIFEST.json").is_file()
        else None,
    }
    bid = report.get("batch_id")
    if bid is not None:
        paths["batch_id"] = str(bid)

    explore = None
    extra: dict[str, Any] | None = None
    if include_explore:
        explore = {
            "classification": classification,
            "wells": report.get("wells"),
            "pin_identical_across_wells": report.get("pin_identical_across_wells"),
            "dry_run": report.get("dry_run"),
        }
        extra = {
            "report": report,
            "branch": branch,
        }

    return build_envelope(
        ok=True,
        surface=surface,
        certified=bool(certified),
        near_miss=near_miss if isinstance(near_miss, bool) else None,
        branch=str(branch) if branch is not None else None,
        paths=paths,
        explore=explore,
        extra=extra,
    )
