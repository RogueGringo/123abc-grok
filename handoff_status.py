#!/usr/bin/env python3
"""Ops status for dual-gate handoff commercial delivery stack.

Reports: dual-gate pin, LATEST release, releases catalog, optional matrix.
Does not re-rank. Never lambda=gamma.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.handoff.package import scan_release_drops, write_releases_catalog
from realm.handoff.verify import verify_archive_dir, verify_dual_gate_pin

logger = logging.getLogger("handoff_status")


def build_status(
    *,
    releases_dir: Path,
    matrix_report: Path | None = None,
    verify_latest: bool = False,
    rebuild_catalog: bool = True,
) -> dict:
    pin = verify_dual_gate_pin()
    catalog_path = None
    if rebuild_catalog and releases_dir.is_dir():
        catalog_path = write_releases_catalog(releases_dir)

    latest = None
    latest_path = releases_dir / "LATEST.json"
    if latest_path.is_file():
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            latest = {"error": str(exc)}

    drops = scan_release_drops(releases_dir) if releases_dir.is_dir() else []
    archive_verify = None
    acceptance = None
    attestation = None
    if latest and latest.get("archive_dir"):
        adir = Path(latest["archive_dir"])
        acc_path = adir / "ACCEPTANCE.json"
        if acc_path.is_file():
            try:
                acceptance = json.loads(acc_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                acceptance = {"error": str(exc)}
        att_path = adir / "ATTESTATION.json"
        if att_path.is_file():
            try:
                attestation = json.loads(att_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                attestation = {"error": str(exc)}
        if verify_latest:
            archive_verify = verify_archive_dir(adir)

    matrix = None
    if matrix_report and Path(matrix_report).is_file():
        try:
            matrix = json.loads(Path(matrix_report).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            matrix = {"error": str(exc)}

    ok = pin.get("ok") is True
    if archive_verify is not None and archive_verify.get("ok") is not True:
        ok = False
    if matrix is not None and matrix.get("ok") is False:
        ok = False
    if isinstance(acceptance, dict) and acceptance.get("accepted") is False:
        ok = False
    matrix_acceptance = None
    if isinstance(matrix, dict) and matrix.get("acceptance"):
        matrix_acceptance = matrix.get("acceptance")
        if matrix_acceptance.get("ok") is False:
            ok = False
    elif matrix_report:
        ma_path = Path(matrix_report).parent / "matrix_acceptance.json"
        if ma_path.is_file():
            try:
                matrix_acceptance = json.loads(ma_path.read_text(encoding="utf-8"))
                if matrix_acceptance.get("ok") is False:
                    ok = False
            except Exception as exc:  # noqa: BLE001
                matrix_acceptance = {"error": str(exc)}

    return {
        "ok": ok,
        "pin": pin,
        "releases_dir": str(releases_dir.resolve()) if releases_dir.exists() else str(releases_dir),
        "n_drops": len(drops),
        "latest": latest,
        "acceptance": (
            {
                "accepted": acceptance.get("accepted"),
                "n_pdb": (acceptance.get("criteria") or {})
                .get("openable_pdbs", {})
                .get("n_pdb"),
                "label": acceptance.get("label"),
                "path": str(
                    Path(latest["archive_dir"]) / "ACCEPTANCE.json"
                )
                if latest and latest.get("archive_dir")
                else None,
            }
            if isinstance(acceptance, dict) and "error" not in acceptance
            else acceptance
        ),
        "attestation": (
            {
                "payload_sha256": attestation.get("payload_sha256"),
                "n_digests": len(attestation.get("digests") or {}),
                "acceptance": attestation.get("acceptance"),
                "pin_ok": (attestation.get("pin") or {}).get("ok"),
            }
            if isinstance(attestation, dict) and "error" not in attestation
            else attestation
        ),
        "archive_verify": archive_verify,
        "catalog_index": str(catalog_path.resolve()) if catalog_path else None,
        "drops_head": drops[:8],
        "matrix": (
            {
                "ok": matrix.get("ok") if isinstance(matrix, dict) else None,
                "tokens": matrix.get("tokens") if isinstance(matrix, dict) else None,
                "rows": matrix.get("rows") if isinstance(matrix, dict) else None,
                "acceptance": matrix_acceptance,
                "path": str(Path(matrix_report).resolve()) if matrix_report else None,
            }
            if matrix is not None
            else None
        ),
        "matrix_acceptance": matrix_acceptance,
        "ontology": "handoff_status_not_lambda_eq_gamma",
        "note": "Ops view only; acceptance metric is openable PDBs + pin.",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Dual-gate handoff ops status (pin, LATEST, catalog, matrix)"
    )
    p.add_argument(
        "--releases",
        type=Path,
        default=Path("out/releases"),
        help="releases root (default: out/releases)",
    )
    p.add_argument(
        "--matrix-report",
        type=Path,
        default=None,
        help="optional matrix_report.json path",
    )
    p.add_argument(
        "--verify-latest",
        action="store_true",
        help="run ARCHIVE.json integrity check on LATEST drop",
    )
    p.add_argument(
        "--no-rebuild-catalog",
        action="store_true",
        help="do not rewrite INDEX.json/INDEX.md",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="write status JSON (default: <releases>/STATUS.json)",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    matrix_path = args.matrix_report
    if matrix_path is None:
        cand = Path("out/matrix/matrix_report.json")
        if cand.is_file():
            matrix_path = cand

    status = build_status(
        releases_dir=Path(args.releases),
        matrix_report=matrix_path,
        verify_latest=bool(args.verify_latest),
        rebuild_catalog=not bool(args.no_rebuild_catalog),
    )

    out = Path(args.report) if args.report else Path(args.releases) / "STATUS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    pin = status.get("pin") or {}
    logger.info(
        "status ok=%s pin soft_T=%s drops=%s latest=%s → %s",
        status.get("ok"),
        pin.get("soft_T"),
        status.get("n_drops"),
        (status.get("latest") or {}).get("label"),
        out,
    )
    if status.get("matrix"):
        logger.info(
            "matrix ok=%s tokens=%s",
            status["matrix"].get("ok"),
            status["matrix"].get("tokens"),
        )
    if status.get("matrix_acceptance"):
        ma = status["matrix_acceptance"] or {}
        logger.info(
            "matrix_acceptance ok=%s n_accepted=%s n_pdb_total=%s",
            ma.get("ok"),
            ma.get("n_accepted"),
            ma.get("n_pdb_total"),
        )
    if status.get("archive_verify"):
        logger.info(
            "latest archive verify ok=%s checked=%s",
            status["archive_verify"].get("ok"),
            status["archive_verify"].get("n_checked"),
        )

    if status.get("acceptance"):
        logger.info(
            "latest acceptance accepted=%s n_pdb=%s",
            (status.get("acceptance") or {}).get("accepted"),
            (status.get("acceptance") or {}).get("n_pdb"),
        )
    if status.get("attestation"):
        logger.info(
            "latest attestation digests=%s payload=%s",
            (status.get("attestation") or {}).get("n_digests"),
            ((status.get("attestation") or {}).get("payload_sha256") or "")[:16],
        )

    # human one-liner to stdout for scripting
    print(
        json.dumps(
            {
                "ok": status.get("ok"),
                "soft_T": pin.get("soft_T"),
                "n_drops": status.get("n_drops"),
                "latest_label": (status.get("latest") or {}).get("label"),
                "accepted": (status.get("acceptance") or {}).get("accepted"),
                "n_pdb": (status.get("acceptance") or {}).get("n_pdb"),
                "report": str(out.resolve()),
            }
        )
    )
    return 0 if status.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
