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


def quality_gate(
    export_summary: dict[str, Any] | None,
    verify_report: dict[str, Any] | None,
    *,
    min_ok_fraction: float = 1.0,
    min_openable_pdbs: int = 1,
    require_verify_ok: bool = True,
    require_biopython: bool = False,
) -> dict[str, Any]:
    """Commercial release gate: pin + openable molds + export success rate.

    Does **not** re-rank or chase enrichment. Openable PDBs / manifest are the
    success metric; enrichment stamp is informational only.

    require_biopython: when True, BioPython must open PDBs (ok is True).
    Skipped/unavailable BioPython fails the gate in that mode.
    """
    reasons: list[str] = []
    pin = verify_dual_gate_pin()
    if not pin.get("ok"):
        reasons.append(
            f"dual_gate_pin_failed soft_T={pin.get('soft_T')} expected={pin.get('expected_soft_T')}"
        )

    n_ok = 0
    n_ids = 0
    ok_fraction: float | None = None
    if export_summary:
        n_ok = int(export_summary.get("n_ok") or 0)
        n_ids = int(export_summary.get("n_ids") or 0)
        if n_ids <= 0:
            reasons.append("export_n_ids_zero")
        else:
            ok_fraction = float(n_ok) / float(n_ids)
            if ok_fraction + 1e-12 < float(min_ok_fraction):
                reasons.append(
                    f"ok_fraction {ok_fraction:.3f} < min_ok_fraction {min_ok_fraction}"
                )
        if n_ok < 1:
            reasons.append("export_n_ok_zero")

    n_pdb = 0
    n_remark_ok = False
    bio_status: Any = None
    if verify_report:
        if require_verify_ok and verify_report.get("ok") is not True:
            reasons.append("verify_report_not_ok")
        remarks = verify_report.get("ontology_remarks") or {}
        n_pdb = int(remarks.get("n_pdb") or 0)
        n_remark_ok = remarks.get("ok") is True
        if n_pdb < int(min_openable_pdbs):
            reasons.append(f"n_pdb {n_pdb} < min_openable_pdbs {min_openable_pdbs}")
        if not n_remark_ok and n_pdb > 0:
            reasons.append("ontology_remarks_incomplete")
        bio = verify_report.get("biopython") or {}
        bio_status = bio.get("ok")
        if bio_status is False:
            reasons.append("biopython_open_failed")
        elif require_biopython and bio_status is not True:
            reasons.append(
                f"biopython_required but status={bio_status!r} "
                f"(install BioPython or drop --require-biopython)"
            )

    ok = len(reasons) == 0
    return {
        "ok": ok,
        "reasons": reasons,
        "pin": pin,
        "export": {"n_ok": n_ok, "n_ids": n_ids, "ok_fraction": ok_fraction},
        "n_pdb": n_pdb,
        "biopython_ok": bio_status,
        "require_biopython": bool(require_biopython),
        "min_ok_fraction": float(min_ok_fraction),
        "min_openable_pdbs": int(min_openable_pdbs),
        "ontology": "handoff_quality_gate_not_lambda_eq_gamma",
        "note": "Gate on openable PDBs + dual-gate pin; not enrichment score-chase.",
    }


def verify_archive_dir(archive_dir: Path | str) -> dict[str, Any]:
    """Verify a dated out/releases/* drop against its ARCHIVE.json digests.

    Does not re-rank. Confirms partner drop integrity after transfer.
    """
    root = Path(archive_dir)
    meta_path = root / "ARCHIVE.json"
    pin = verify_dual_gate_pin()
    if not root.is_dir():
        return {
            "ok": False,
            "error": "not_a_directory",
            "root": str(root),
            "pin": pin,
            "ontology": "handoff_archive_verify_not_lambda_eq_gamma",
        }
    if not meta_path.is_file():
        return {
            "ok": False,
            "error": "missing_ARCHIVE_json",
            "root": str(root.resolve()),
            "pin": pin,
            "ontology": "handoff_archive_verify_not_lambda_eq_gamma",
        }
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"ARCHIVE_json_invalid: {exc}",
            "root": str(root.resolve()),
            "pin": pin,
            "ontology": "handoff_archive_verify_not_lambda_eq_gamma",
        }

    bad: list[str] = []
    checked = 0
    for entry in meta.get("files") or []:
        name = entry.get("name")
        expect = entry.get("sha256")
        if not name or not expect:
            continue
        if name == "ARCHIVE.json":
            # file mutates when its own digest is appended; skip self-hash
            continue
        path = root / name
        if not path.is_file():
            bad.append(f"missing:{name}")
            continue
        got = _sha256_file(path)
        checked += 1
        if got != expect:
            bad.append(f"mismatch:{name}")

    # structural presence
    for required in ("RELEASE.md",):
        if not (root / required).is_file() and not any(
            (e.get("name") == required) for e in (meta.get("files") or [])
        ):
            # soft: only flag if listed but missing already handled
            pass

    has_zip = any(
        str(e.get("name", "")).lower().endswith(".zip") for e in (meta.get("files") or [])
    )
    if not has_zip and not any(p.suffix.lower() == ".zip" for p in root.iterdir() if p.is_file()):
        bad.append("no_zip_in_archive")

    att = verify_attestation(root) if (root / "ATTESTATION.json").is_file() else None
    if att is not None and att.get("ok") is False:
        bad.append("attestation_failed")

    ok = (
        pin.get("ok") is True
        and len(bad) == 0
        and checked > 0
        and meta.get("quality_gate_ok") is not False
    )
    return {
        "ok": ok,
        "root": str(root.resolve()),
        "pin": pin,
        "label": meta.get("label"),
        "n_checked": checked,
        "n_bad": len(bad),
        "bad": bad[:20],
        "quality_gate_ok": meta.get("quality_gate_ok"),
        "ids": meta.get("ids"),
        "zip_sha256": meta.get("zip_sha256"),
        "attestation": att,
        "ontology": "handoff_archive_verify_not_lambda_eq_gamma",
        "note": "Integrity of dated partner drop; not enrichment score-chase.",
    }


def verify_attestation(archive_dir: Path | str) -> dict[str, Any]:
    """Verify ATTESTATION.json digests and dual-gate pin snapshot."""
    root = Path(archive_dir)
    path = root / "ATTESTATION.json"
    pin = verify_dual_gate_pin()
    if not path.is_file():
        return {
            "ok": None,
            "skipped": True,
            "error": "no ATTESTATION.json",
            "pin": pin,
            "ontology": "handoff_attestation_verify_not_lambda_eq_gamma",
        }
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"invalid_json: {exc}",
            "pin": pin,
            "ontology": "handoff_attestation_verify_not_lambda_eq_gamma",
        }

    bad: list[str] = []
    digests = body.get("digests") or {}
    for name, expect in digests.items():
        p = root / name
        if not p.is_file():
            bad.append(f"missing:{name}")
            continue
        got = _sha256_file(p)
        if got != expect:
            bad.append(f"mismatch:{name}")

    apin = body.get("pin") or {}
    if apin.get("ok") is not True:
        bad.append("attestation_pin_not_ok")
    if pin.get("ok") is not True:
        bad.append("live_pin_not_ok")
    if abs(float(apin.get("soft_T", -1)) - 0.036) > 1e-9:
        bad.append("attestation_soft_T_drift")

    # recompute payload_sha256
    payload = json.dumps(
        {
            "pin": body.get("pin"),
            "digests": body.get("digests"),
            "zip_sha256": body.get("zip_sha256"),
            "acceptance": body.get("acceptance"),
            "ids": body.get("ids"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    got_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    expect_payload = body.get("payload_sha256")
    if expect_payload and got_payload != expect_payload:
        bad.append("payload_sha256_mismatch")

    return {
        "ok": len(bad) == 0,
        "n_digests": len(digests),
        "n_bad": len(bad),
        "bad": bad[:20],
        "payload_sha256": expect_payload,
        "acceptance": body.get("acceptance"),
        "pin": pin,
        "ontology": "handoff_attestation_verify_not_lambda_eq_gamma",
        "note": "Checksum seal only; not a cryptographic signature.",
    }
