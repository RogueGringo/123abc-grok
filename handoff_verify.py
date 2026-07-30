#!/usr/bin/env python3
"""Standalone dual-gate handoff package / export verifier CLI.

Partner-facing: check pin, ontology REMARKs, SHA256, optional BioPython open.
Does not re-rank. Never λ=γ.
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

from realm.handoff.verify import (
    quality_gate,
    verify_archive_dir,
    verify_dual_gate_pin,
    verify_handoff_tree,
)

logger = logging.getLogger("handoff_verify")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Verify dual-gate handoff export, partner package, or release archive"
    )
    p.add_argument(
        "root",
        type=Path,
        nargs="?",
        default=None,
        help="export, package, or archive directory (required unless --pin-only)",
    )
    p.add_argument(
        "--pin-only",
        action="store_true",
        help="only check LengthPolicy production pin (soft_T n=12 = 0.036)",
    )
    p.add_argument(
        "--archive",
        action="store_true",
        help="treat root as dated out/releases/* drop; verify ARCHIVE.json digests",
    )
    p.add_argument(
        "--require-sha256",
        action="store_true",
        help="fail if SHA256SUMS.txt missing or mismatched (package mode)",
    )
    p.add_argument(
        "--no-biopython",
        action="store_true",
        help="skip BioPython open checks",
    )
    p.add_argument(
        "--min-openable-pdbs",
        type=int,
        default=1,
        help="quality gate: minimum PDB files with ontology REMARK (default 1)",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="write JSON report path (default: <root>/verify_report.json)",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if args.pin_only:
        pin = verify_dual_gate_pin()
        print(json.dumps(pin, indent=2))
        return 0 if pin.get("ok") else 2

    if args.root is None:
        p.error("root directory required unless --pin-only")

    root = Path(args.root)
    if not root.is_dir():
        logger.error("not a directory: %s", root)
        return 2

    if args.archive or (root / "ARCHIVE.json").is_file():
        report = verify_archive_dir(root)
        out_path = Path(args.report) if args.report else root / "archive_verify.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        logger.info(
            "archive verify ok=%s checked=%s bad=%s → %s",
            report.get("ok"),
            report.get("n_checked"),
            report.get("n_bad"),
            out_path,
        )
        if report.get("bad"):
            for b in report["bad"]:
                logger.warning("archive: %s", b)
        return 0 if report.get("ok") else 3

    report = verify_handoff_tree(
        root,
        require_sha256=bool(args.require_sha256),
        check_biopython=not bool(args.no_biopython),
    )
    gate = quality_gate(
        None,
        report,
        min_ok_fraction=0.0,
        min_openable_pdbs=int(args.min_openable_pdbs),
        require_verify_ok=True,
    )
    report["quality_gate"] = gate
    report["ok"] = bool(report.get("ok")) and bool(gate.get("ok"))

    out_path = args.report
    if out_path is None:
        out_path = root / "verify_report.json"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    logger.info(
        "verify ok=%s pin=%s remarks=%s sha=%s bio=%s gate=%s → %s",
        report.get("ok"),
        (report.get("pin") or {}).get("ok"),
        (report.get("ontology_remarks") or {}).get("ok"),
        (report.get("sha256") or {}).get("ok"),
        (report.get("biopython") or {}).get("ok"),
        gate.get("ok"),
        out_path,
    )
    if gate.get("reasons"):
        for r in gate["reasons"]:
            logger.warning("gate: %s", r)

    return 0 if report.get("ok") else 3


if __name__ == "__main__":
    sys.exit(main())
