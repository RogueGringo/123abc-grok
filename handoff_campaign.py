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
from realm.handoff.verify import quality_gate, verify_dual_gate_pin, verify_handoff_tree
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
    p.add_argument(
        "--resume",
        action="store_true",
        help="skip PDB ids that already have a successful index.json under out-dir",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve IDs + print dual-gate pins; do not export",
    )
    p.add_argument(
        "--min-ok-fraction",
        type=float,
        default=1.0,
        help="quality gate: min fraction of IDs that must export OK (default 1.0)",
    )
    p.add_argument(
        "--min-openable-pdbs",
        type=int,
        default=1,
        help="quality gate: min PDB files with ontology REMARK (default 1)",
    )
    p.add_argument(
        "--skip-preflight",
        action="store_true",
        help="skip dual-gate pin preflight (not recommended)",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    ids = resolve_pdb_id_list(args.pdb_ids)
    if not ids:
        logger.error("no PDB ids resolved from %r", args.pdb_ids)
        return 2

    if not args.skip_preflight:
        pin = verify_dual_gate_pin()
        if not pin.get("ok"):
            logger.error("preflight dual-gate pin failed: %s", pin)
            return 4
        logger.info(
            "preflight pin OK soft_T(n=12)=%s seq_mix=%s face_weight=%s",
            pin.get("soft_T"),
            pin.get("seq_mix"),
            pin.get("face_weight"),
        )

    if args.dry_run:
        summary = export_structure_batch(
            ids, {}, out_root=args.out_dir, dry_run=True
        )
        logger.info(
            "dry-run ids=%s pin=%s",
            summary.get("ids"),
            summary.get("dual_gate_pin"),
        )
        (Path(args.out_dir)).mkdir(parents=True, exist_ok=True)
        (Path(args.out_dir) / "dry_run.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        return 0

    knobs = load_knobs(args.knobs)
    if isinstance(knobs, dict) and "best_knobs" in knobs:
        knobs = knobs["best_knobs"]

    logger.info("campaign export ids=%s → %s resume=%s", ids, args.out_dir, args.resume)
    summary = export_structure_batch(
        ids,
        knobs,
        out_root=args.out_dir,
        top_k=int(args.top_k),
        n_zeros=int(args.k),
        include_coutsias=False,
        with_enrichment=bool(args.with_enrichment),
        with_biopython_check=not bool(args.no_biopython_check),
        resume=bool(args.resume),
    )
    logger.info(
        "export n_ok=%s/%s skipped=%s mean_enr=%s",
        summary["n_ok"],
        summary["n_ids"],
        summary.get("n_skipped_resume"),
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
            gate_early = quality_gate(
                summary,
                report,
                min_ok_fraction=float(args.min_ok_fraction),
                min_openable_pdbs=int(args.min_openable_pdbs),
            )
            campaign_fail = {
                "ids": ids,
                "export": {
                    "n_ok": summary["n_ok"],
                    "n_ids": summary["n_ids"],
                    "n_skipped_resume": summary.get("n_skipped_resume"),
                    "manifest": summary.get("manifest"),
                    "enrichment_summary": summary.get("enrichment_summary"),
                    "enrichment_aggregate": summary.get("enrichment_aggregate"),
                    "summary_md": str((Path(args.out_dir) / "SUMMARY.md").resolve()),
                },
                "package": package_meta,
                "verify": report,
                "quality_gate": gate_early,
                "ontology": "handoff_campaign_not_lambda_eq_gamma",
            }
            (Path(args.out_dir) / "campaign_report.json").write_text(
                json.dumps(campaign_fail, indent=2) + "\n", encoding="utf-8"
            )
            return 3

    gate = quality_gate(
        summary,
        report,
        min_ok_fraction=float(args.min_ok_fraction),
        min_openable_pdbs=int(args.min_openable_pdbs),
        require_verify_ok=not args.no_verify,
    )
    logger.info("quality_gate ok=%s reasons=%s", gate.get("ok"), gate.get("reasons"))

    campaign = {
        "ids": ids,
        "export": {
            "n_ok": summary["n_ok"],
            "n_ids": summary["n_ids"],
            "n_skipped_resume": summary.get("n_skipped_resume"),
            "manifest": summary.get("manifest"),
            "enrichment_summary": summary.get("enrichment_summary"),
            "enrichment_aggregate": summary.get("enrichment_aggregate"),
            "summary_md": str((Path(args.out_dir) / "SUMMARY.md").resolve()),
        },
        "package": package_meta,
        "verify": report,
        "quality_gate": gate,
        "ontology": "handoff_campaign_not_lambda_eq_gamma",
    }
    (Path(args.out_dir) / "campaign_report.json").write_text(
        json.dumps(campaign, indent=2) + "\n", encoding="utf-8"
    )
    if not gate.get("ok"):
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
