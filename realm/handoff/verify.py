"""Verify dual-gate handoff exports and partner packages.

Checks (export or package root):
  - dual-gate LengthPolicy pin (soft_T n=12 = 0.036) when index present
  - ontology REMARK on every *_ca.pdb / *_bb.pdb
  - SHA256SUMS.txt if present
  - optional BioPython open of each PDB

Does **not** re-rank or change production numbers. Never λ=γ.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from realm.handoff.pipeline import biopython_open_check
from realm.validate.length_policy import policy_for

logger = logging.getLogger(__name__)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_dual_gate_pin() -> dict[str, Any]:
    p = policy_for(12, base_beta=0.20)
    ok = (
        abs(float(p.soft_T) - 0.036) < 1e-12
        and float(p.seq_mix) == 0.0
        and abs(float(p.face_weight) - 0.08) < 1e-12
    )
    return {
        "ok": ok,
        "soft_T": float(p.soft_T),
        "seq_mix": float(p.seq_mix),
        "face_weight": float(p.face_weight),
        "expected_soft_T": 0.036,
    }


def verify_ontology_remarks(root: Path) -> dict[str, Any]:
    pdbs = sorted(root.rglob("*.pdb"))
    bad: list[str] = []
    for p in pdbs:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{p}: read_error {exc}")
            continue
        if "not_lambda_eq_gamma" not in text:
            bad.append(str(p.relative_to(root)))
    return {
        "ok": len(bad) == 0 and len(pdbs) > 0,
        "n_pdb": len(pdbs),
        "n_missing_remark": len(bad),
        "missing": bad[:20],
    }


def verify_sha256sums(root: Path) -> dict[str, Any]:
    sums = root / "SHA256SUMS.txt"
    if not sums.is_file():
        return {"ok": None, "skipped": True, "error": "no SHA256SUMS.txt"}
    mismatches: list[str] = []
    checked = 0
    for line in sums.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        digest, rel = parts[0], parts[-1]
        path = root / rel
        if not path.is_file():
            mismatches.append(f"missing:{rel}")
            continue
        got = _sha256_file(path)
        checked += 1
        if got != digest:
            mismatches.append(f"mismatch:{rel}")
    return {
        "ok": len(mismatches) == 0 and checked > 0,
        "n_checked": checked,
        "n_bad": len(mismatches),
        "bad": mismatches[:20],
        "skipped": False,
    }


def verify_biopython_pdbs(root: Path, *, max_files: int = 50) -> dict[str, Any]:
    pdbs = sorted(root.rglob("*.pdb"))[: int(max_files)]
    if not pdbs:
        return {"ok": None, "skipped": True, "n": 0}
    results = [biopython_open_check(p) for p in pdbs]
    if all(r.get("ok") is None for r in results):
        return {
            "ok": None,
            "skipped": True,
            "n": len(pdbs),
            "error": results[0].get("error"),
        }
    n_ok = sum(1 for r in results if r.get("ok") is True)
    n_fail = sum(1 for r in results if r.get("ok") is False)
    return {
        "ok": n_fail == 0 and n_ok > 0,
        "n": len(pdbs),
        "n_ok": n_ok,
        "n_fail": n_fail,
        "skipped": False,
    }


def verify_index_policy(root: Path) -> dict[str, Any]:
    """If index/batch_index present, confirm stamped soft_T matches policy for n_ca."""
    issues: list[str] = []
    checked = 0
    for idx_path in list(root.rglob("index.json")) + list(root.glob("batch_index.json")):
        try:
            data = json.loads(idx_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{idx_path.name}: json {exc}")
            continue
        # single structure index
        if "dual_gate" in data and "length_policy" in (data.get("dual_gate") or {}):
            lp = data["dual_gate"]["length_policy"]
            n_ca = int(lp.get("n_ca") or 0)
            if n_ca >= 6:
                exp = policy_for(n_ca, base_beta=0.20).soft_T
                got = float(lp.get("soft_T", -1))
                checked += 1
                if abs(got - exp) > 1e-9:
                    issues.append(
                        f"{idx_path}: soft_T {got} != policy {exp} for n_ca={n_ca}"
                    )
        # batch summary rows may lack dual_gate; skip
    if checked == 0:
        return {"ok": None, "skipped": True, "n_checked": 0}
    return {"ok": len(issues) == 0, "n_checked": checked, "issues": issues[:10]}


def verify_handoff_tree(
    root: Path | str,
    *,
    require_sha256: bool = False,
    check_biopython: bool = True,
) -> dict[str, Any]:
    """Full verification report for an export or partner package directory."""
    root = Path(root)
    report: dict[str, Any] = {
        "root": str(root.resolve()),
        "pin": verify_dual_gate_pin(),
        "ontology_remarks": verify_ontology_remarks(root),
        "sha256": verify_sha256sums(root),
        "index_policy": verify_index_policy(root),
        "biopython": (
            verify_biopython_pdbs(root) if check_biopython else {"ok": None, "skipped": True}
        ),
        "ontology": "handoff_verify_not_lambda_eq_gamma",
    }
    checks = [
        report["pin"]["ok"] is True,
        report["ontology_remarks"]["ok"] is True,
        report["index_policy"]["ok"] is not False,
    ]
    sha = report["sha256"]
    if require_sha256:
        checks.append(sha.get("ok") is True)
    else:
        checks.append(sha.get("ok") is not False)  # None skip or True pass
    bio = report["biopython"]
    if bio.get("ok") is False:
        checks.append(False)
    report["ok"] = all(checks)
    return report
