#!/usr/bin/env python3
"""One-shot dual-gate handoff campaign: export → package → verify.

Does not change LengthPolicy production numbers. Never λ=γ.
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

from realm.handoff.package import build_partner_package
from realm.handoff.pipeline import export_structure_batch, resolve_pdb_id_list
from realm.handoff.verify import verify_handoff_tree
from realm.validate.report import load_knobs

logger = logging.getLogger("handoff_campaign")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Dual-gate handoff campaign: export + partner package + verify"
    )
    p.add_argument(
        "--pdb-ids",
        type=str,
        default="probe",
        help="IDs or tokens default|probe|holdout (default: probe)",
    )
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("--out-dir", type=Path, default=Path("out/handoff_campaign"))
    p.add_argument("--package-dir", type=Path, default=None)
    p.add_argument("--top-k", type=int, default=4)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--with-enrichment", action="store_true")
    p.add_argument("--no-biopython-check", action="store_true")
    p.add_argument("--no-package", action="store_true")
    p.add_argument("--no-verify", action="store_true")
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    knobs = load_knobs(args.knobs)
    if isinstance(knobs, dict) and "best_knobs" in knobs:
        knobs = knobs["best_knobs"]

    ids = resolve_pdb_id_list(args.pdb_ids)
    if not ids:
        logger.error("no PDB ids resolved from %r", args.pdb_ids)
        return 2

    logger.info("campaign export ids=%s → %s", ids, args.out_dir)
    summary = export_structure_batch(
        ids,
        knobs,
        out_root=args.out_dir,
        top_k=int(args.top_k),
        n_zeros=int(args.k),
        include_coutsias=False,
        with_enrichment=bool(args.with_enrichment),
        with_biopython_check=not bool(args.no_biopython_check),
    )
    logger.info(
        "export n_ok=%s/%s mean_enr=%s",
        summary["n_ok"],
        summary["n_ids"],
        (summary.get("enrichment_aggregate") or {}).get("mean_enrichment"),
    )
    if summary["n_ok"] == 0:
        return 1

    package_meta = None
    verify_root = Path(args.out_dir)
    if not args.no_package:
        package_meta = build_partner_package(
            args.out_dir,
            dest_dir=args.package_dir,
        )
        verify_root = Path(package_meta["package_dir"])
        logger.info("package zip=%s", package_meta.get("zip_path"))

    report = None
    if not args.no_verify:
        report = verify_handoff_tree(
            verify_root,
            require_sha256=not args.no_package,
            check_biopython=not args.no_biopython_check,
        )
        (Path(args.out_dir) / "verify_report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        logger.info(
            "verify ok=%s pin=%s remarks=%s sha=%s bio=%s",
            report.get("ok"),
            report["pin"].get("ok"),
            report["ontology_remarks"].get("ok"),
            report["sha256"].get("ok"),
            report["biopython"].get("ok"),
        )
        if not report.get("ok"):
            return 3

    campaign = {
        "ids": ids,
        "export": {
            "n_ok": summary["n_ok"],
            "n_ids": summary["n_ids"],
            "manifest": summary.get("manifest"),
            "enrichment_summary": summary.get("enrichment_summary"),
            "enrichment_aggregate": summary.get("enrichment_aggregate"),
        },
        "package": package_meta,
        "verify": report,
        "ontology": "handoff_campaign_not_lambda_eq_gamma",
    }
    (Path(args.out_dir) / "campaign_report.json").write_text(
        json.dumps(campaign, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
