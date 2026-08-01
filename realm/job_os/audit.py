"""Partner audit of Job OS runs — re-check firewall / pin seal without re-ingest.

Does not retune pin. Does not re-score science. Reads artifacts only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from realm.job_os.firewall import assert_firewall_invariants, build_job_firewall


def audit_job_run(run_dir: Path | str) -> dict[str, Any]:
    """Audit a single Job OS run directory.

    Checks:
      - FIREWALL.json / COHERENCE firewall presence and invariants
      - pin_writable never true
      - certified ⇔ solved (when both present)
      - near-miss never certified
      - PARTNER_RECIPE only expected when solved (warn if mismatch)
    """
    root = Path(run_dir)
    findings: list[dict[str, Any]] = []
    ok = True

    def _fail(code: str, msg: str) -> None:
        nonlocal ok
        ok = False
        findings.append({"level": "fail", "code": code, "message": msg})

    def _warn(code: str, msg: str) -> None:
        findings.append({"level": "warn", "code": code, "message": msg})

    def _info(code: str, msg: str) -> None:
        findings.append({"level": "info", "code": code, "message": msg})

    if not root.is_dir():
        return {
            "kind": "job_os_audit",
            "ok": False,
            "run_dir": str(root),
            "findings": [{"level": "fail", "code": "no_dir", "message": f"not a directory: {root}"}],
        }

    coh: dict[str, Any] = {}
    run: dict[str, Any] = {}
    fw: dict[str, Any] = {}
    if (root / "COHERENCE.json").is_file():
        try:
            coh = json.loads((root / "COHERENCE.json").read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            _fail("coherence_parse", str(exc))
    else:
        _fail("coherence_missing", "COHERENCE.json missing")

    if (root / "RUN.json").is_file():
        try:
            run = json.loads((root / "RUN.json").read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            _warn("run_parse", str(exc))

    if (root / "FIREWALL.json").is_file():
        try:
            fw = json.loads((root / "FIREWALL.json").read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            _fail("firewall_parse", str(exc))
    elif coh.get("firewall"):
        fw = dict(coh["firewall"])
        _warn("firewall_file_missing", "using COHERENCE.firewall embed")
    else:
        # Rebuild from COHERENCE if possible (older runs)
        if coh:
            fw = build_job_firewall(result=coh, ledger=coh.get("ledger"), solved=coh.get("solved"))
            _warn("firewall_rebuilt", "FIREWALL.json absent; rebuilt from COHERENCE")
        else:
            _fail("firewall_missing", "no FIREWALL.json or COHERENCE firewall")

    if fw:
        for v in assert_firewall_invariants(fw):
            _fail("firewall_invariant", v)
        if fw.get("pin_writable") is True:
            _fail("pin_writable", "firewall.pin_writable must be false")
        if (fw.get("explore") or {}).get("not_acceptance") is not True:
            _fail("explore_acceptance", "explore must be not_acceptance")

    solved = bool(coh.get("solved")) if coh else bool(run.get("status") == "solved")
    certified = fw.get("certified") if fw else coh.get("firewall_certified")
    near = (fw.get("near_miss") or {}) if fw else {}
    if near.get("near_miss") and certified:
        _fail("near_miss_certified", "near-miss cannot be certified")
    if certified is not None and bool(certified) != bool(solved):
        # Allow unsolved with certified false; fail only hard disagreement
        if bool(certified) and not solved:
            _fail("certify_without_solved", "firewall certified but COHERENCE.solved is false")
        elif solved and not bool(certified):
            _warn(
                "solved_not_certified",
                "solved true but firewall.certified false — check rebuild path",
            )

    recipe = (root / "PARTNER_RECIPE.json").is_file()
    if solved and not recipe:
        _warn("recipe_missing", "SOLVED without PARTNER_RECIPE.json")
    if recipe and not solved:
        _warn("recipe_without_solved", "PARTNER_RECIPE present but not solved")

    if (root / "TREND_ROLLUP.json").is_file():
        try:
            tr = json.loads((root / "TREND_ROLLUP.json").read_text(encoding="utf-8"))
            if tr.get("not_acceptance") is not True:
                _warn("trend_acceptance", "TREND_ROLLUP should be not_acceptance")
        except Exception as exc:  # noqa: BLE001
            _warn("trend_parse", str(exc))

    aliases = ((fw.get("explore") or {}).get("fields") or {}).get("alias_applied")
    if aliases:
        _info("aliases", f"n_aliases={len(aliases)}")

    return {
        "kind": "job_os_audit",
        "ontology": "job_os_partner_audit_v1",
        "ok": ok,
        "run_dir": str(root.resolve()),
        "run_id": coh.get("run_id") or run.get("run_id") or root.name,
        "solved": solved,
        "firewall_certified": certified,
        "near_miss": near.get("near_miss"),
        "near_miss_verdict": near.get("verdict"),
        "partner_recipe": recipe,
        "pin_writable": fw.get("pin_writable") if fw else None,
        "n_fail": sum(1 for f in findings if f["level"] == "fail"),
        "n_warn": sum(1 for f in findings if f["level"] == "warn"),
        "findings": findings,
        "note": "Artifact audit only — does not re-ingest or retune pin.",
    }


def audit_rotation_batch(batch_dir: Path | str) -> dict[str, Any]:
    """Audit a rotation batch: ROTATION_REPORT + each well run."""
    root = Path(batch_dir)
    findings: list[dict[str, Any]] = []
    ok = True
    report: dict[str, Any] = {}
    if (root / "ROTATION_REPORT.json").is_file():
        try:
            report = json.loads((root / "ROTATION_REPORT.json").read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            ok = False
            findings.append({"level": "fail", "code": "report_parse", "message": str(exc)})
    else:
        ok = False
        findings.append(
            {"level": "fail", "code": "report_missing", "message": "ROTATION_REPORT.json missing"}
        )

    if report.get("pin_writable") is True:
        ok = False
        findings.append(
            {"level": "fail", "code": "pin_writable", "message": "rotation pin_writable true"}
        )
    if report and not report.get("pin_identical_across_wells", True):
        ok = False
        findings.append(
            {
                "level": "fail",
                "code": "pin_not_identical",
                "message": "pin thresholds not identical across wells",
            }
        )

    well_audits: list[dict[str, Any]] = []
    for w in report.get("wells") or []:
        out = w.get("out_root")
        if not out:
            continue
        wa = audit_job_run(out)
        well_audits.append(
            {
                "well_id": w.get("well_id"),
                "ok": wa.get("ok"),
                "solved": wa.get("solved"),
                "firewall_certified": wa.get("firewall_certified"),
                "n_fail": wa.get("n_fail"),
            }
        )
        if not wa.get("ok"):
            ok = False
            findings.append(
                {
                    "level": "fail",
                    "code": "well_audit_fail",
                    "message": f"well {w.get('well_id')} failed audit",
                    "well_id": w.get("well_id"),
                }
            )

    branch = report.get("branch")
    n_cert = (report.get("classification") or {}).get("n_firewall_certified")
    n_wells = (report.get("classification") or {}).get("n_wells")
    if branch == "ROTATION_PASS" and n_cert is not None and n_wells is not None:
        if int(n_cert) != int(n_wells):
            ok = False
            findings.append(
                {
                    "level": "fail",
                    "code": "branch_mismatch",
                    "message": f"ROTATION_PASS but certified {n_cert}/{n_wells}",
                }
            )

    return {
        "kind": "job_rotation_audit",
        "ontology": "job_os_partner_audit_v1",
        "ok": ok,
        "batch_dir": str(root.resolve()),
        "branch": branch,
        "pin_identical": report.get("pin_identical_across_wells"),
        "n_wells": n_wells,
        "n_firewall_certified": n_cert,
        "wells": well_audits,
        "n_fail": sum(1 for f in findings if f["level"] == "fail"),
        "findings": findings,
        "note": "Rotation batch audit — pin sealed; branch from firewall_certified.",
    }
