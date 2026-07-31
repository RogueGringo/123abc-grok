#!/usr/bin/env python3
"""One-command commercial dual-gate ship path.

Optional matrix run, then deliver receipt + verify + status.
Does not change LengthPolicy. Never lambda=gamma.
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

from handoff_deliver import main as deliver_main
from handoff_matrix import main as matrix_main
from handoff_status import main as status_main
from realm.handoff.package import (
    build_partner_receipt_bundle,
    verify_partner_receipt_bundle,
    write_releases_catalog,
    write_ship_md,
)
from realm.handoff.verify import verify_delivery_receipt, verify_dual_gate_pin

logger = logging.getLogger("handoff_ship")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Commercial ship: optional matrix → DELIVERY → verify → status"
    )
    p.add_argument(
        "--verify-bundle",
        type=Path,
        default=None,
        help="verify partner_receipts_*.zip (or extracted dir); skip ship pipeline",
    )
    p.add_argument(
        "--run-matrix",
        action="store_true",
        help="run handoff_matrix before deliver (probe,holdout by default)",
    )
    p.add_argument(
        "--tokens",
        type=str,
        default="probe,holdout",
        help="matrix tokens when --run-matrix (default: probe,holdout)",
    )
    p.add_argument(
        "--out-root",
        type=Path,
        default=Path("out/matrix"),
        help="matrix out root (default: out/matrix)",
    )
    p.add_argument(
        "--releases",
        type=Path,
        default=Path("out/releases"),
        help="releases archive root",
    )
    p.add_argument(
        "--matrix-report",
        type=Path,
        default=None,
        help="matrix_report.json (default: <out-root>/matrix_report.json)",
    )
    p.add_argument("--top-k", type=int, default=2)
    p.add_argument(
        "--require-biopython",
        action="store_true",
        help="matrix quality gate requires BioPython open",
    )
    p.add_argument(
        "--recheck-drops",
        action="store_true",
        help="re-accept each drop when verifying DELIVERY",
    )
    p.add_argument(
        "--label",
        type=str,
        default="commercial-ship",
        help="DELIVERY label",
    )
    p.add_argument(
        "--no-bundle",
        action="store_true",
        help="skip partner receipt zip (proof-only, no mold PDBs)",
    )
    p.add_argument(
        "--attach-known-solutions",
        type=Path,
        default=None,
        help=(
            "optional: copy known-solutions science annex into releases + matrix "
            "out-root (report-only; never gates ship/accept)"
        ),
    )
    p.add_argument(
        "--run-known-solutions",
        action="store_true",
        help=(
            "after commercial ship: run known-solutions science ledger and attach "
            "(report-only; never gates ship/accept)"
        ),
    )
    p.add_argument(
        "--ks-compare-modes",
        type=str,
        default=None,
        help="with --run-known-solutions: e.g. soft,mixed,hard",
    )
    p.add_argument(
        "--ks-skip-expand",
        action="store_true",
        help="with --run-known-solutions: curated probe/holdout only",
    )
    p.add_argument(
        "--ks-n-seeds",
        type=int,
        default=1,
        help="with --run-known-solutions: n_seeds (default 1)",
    )
    p.add_argument(
        "--ks-out-dir",
        type=Path,
        default=None,
        help="with --run-known-solutions: out dir (default: <out-root>/known_solutions_run)",
    )
    p.add_argument(
        "--knobs",
        type=Path,
        default=Path("evolve_result.json"),
        help="knobs for --run-known-solutions",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if args.verify_bundle is not None:
        report = verify_partner_receipt_bundle(args.verify_bundle)
        out = Path(args.verify_bundle)
        if out.is_file():
            out_report = out.parent / "RECEIPT_BUNDLE_VERIFY.json"
        else:
            out_report = out / "RECEIPT_BUNDLE_VERIFY.json"
        out_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        logger.info(
            "bundle verify ok=%s reasons=%s → %s",
            report.get("ok"),
            report.get("reasons"),
            out_report,
        )
        print(
            json.dumps(
                {
                    "ok": report.get("ok"),
                    "soft_T": (report.get("pin") or {}).get("soft_T"),
                    "n_pdb_total": ((report.get("delivery") or {}).get("n_pdb_total")),
                    "reasons": report.get("reasons"),
                    "report": str(out_report.resolve()),
                }
            )
        )
        return 0 if report.get("ok") else 3

    pin = verify_dual_gate_pin()
    if not pin.get("ok"):
        logger.error("dual-gate pin failed: %s", pin)
        return 4

    out_root = Path(args.out_root)
    matrix_report = (
        Path(args.matrix_report)
        if args.matrix_report
        else out_root / "matrix_report.json"
    )

    if args.run_matrix:
        argv_m = [
            "--tokens",
            args.tokens,
            "--out-root",
            str(out_root),
            "--archive-dir",
            str(args.releases),
            "--top-k",
            str(int(args.top_k)),
        ]
        if args.require_biopython:
            argv_m.append("--require-biopython")
        else:
            argv_m.append("--no-biopython-check")
        if args.v:
            argv_m.append("-v")
        logger.info("=== ship: run matrix %s ===", args.tokens)
        rc = matrix_main(argv_m)
        if rc != 0:
            logger.error("matrix failed rc=%s", rc)
            return rc
    elif not matrix_report.is_file():
        logger.error(
            "matrix report missing %s (pass --run-matrix or path)", matrix_report
        )
        return 2

    logger.info("=== ship: write DELIVERY ===")
    rc = deliver_main(
        [
            "--matrix-report",
            str(matrix_report),
            "--releases",
            str(args.releases),
            "--label",
            args.label,
            "--require-shippable",
        ]
    )
    if rc != 0:
        logger.error("deliver failed rc=%s", rc)
        return rc

    delivery = Path(args.releases) / "LATEST_DELIVERY.json"
    if not delivery.is_file():
        delivery = Path(args.releases) / "DELIVERY.json"
    if not delivery.is_file():
        delivery = matrix_report.parent / "DELIVERY.json"

    logger.info("=== ship: verify DELIVERY %s ===", delivery)
    vargv = ["--verify", str(delivery)]
    if args.recheck_drops:
        vargv.append("--recheck-drops")
    rc = deliver_main(vargv)
    if rc != 0:
        logger.error("delivery verify failed rc=%s", rc)
        return rc

    vreport = verify_delivery_receipt(
        delivery,
        require_shippable=True,
        recheck_drops=bool(args.recheck_drops),
    )

    logger.info("=== ship: status ===")
    status_main(
        [
            "--releases",
            str(args.releases),
            "--matrix-report",
            str(matrix_report),
            "--verify-latest",
        ]
    )

    ks_meta = None
    ks_src = args.attach_known_solutions
    # Science stamp AFTER commercial verify — never gates ship ok
    if args.run_known_solutions:
        from realm.validate.known_solutions import (
            run_compare_modes,
            run_known_solutions,
        )

        ks_out = args.ks_out_dir or (out_root / "known_solutions_run")
        logger.info(
            "=== ship: run known-solutions (report-only) → %s ===", ks_out
        )
        if args.ks_compare_modes:
            modes = [
                m.strip()
                for m in str(args.ks_compare_modes).split(",")
                if m.strip()
            ]
            ks_report = run_compare_modes(
                knobs_path=args.knobs,
                out_dir=ks_out,
                modes=modes,
                n_seeds=int(args.ks_n_seeds),
                n_decoys=24,
                skip_expand=bool(args.ks_skip_expand),
                kabsch_set="curated",
                kabsch_max=4,
            )
        else:
            ks_report = run_known_solutions(
                knobs_path=args.knobs,
                out_dir=ks_out,
                n_seeds=int(args.ks_n_seeds),
                n_decoys=24,
                skip_expand=bool(args.ks_skip_expand),
                kabsch_set="curated",
                kabsch_max=4,
            )
        ks_src = Path(ks_report.get("out_dir") or ks_out)
        logger.info(
            "known-solutions status=%s out=%s",
            ks_report.get("status"),
            ks_src,
        )

    if ks_src is not None:
        from realm.validate.known_solutions import attach_report_to_dir

        logger.info("=== ship: attach known-solutions annex %s ===", ks_src)
        ks_meta = attach_report_to_dir(ks_src, args.releases)
        # also beside matrix for partner matrix drop
        if matrix_report.parent.is_dir():
            attach_report_to_dir(ks_src, matrix_report.parent)
        logger.info(
            "known-solutions attach ok=%s pin_ok=%s compare=%s",
            ks_meta.get("ok"),
            ks_meta.get("pin_ok"),
            ks_meta.get("has_decoy_mode_compare"),
        )

    ship = {
        "ok": bool(vreport.get("ok")),
        "shippable": vreport.get("shippable"),
        "soft_T": (vreport.get("pin") or {}).get("soft_T"),
        "n_pdb_total": (vreport.get("matrix_acceptance") or {}).get("n_pdb_total"),
        "n_accepted": (vreport.get("matrix_acceptance") or {}).get("n_accepted"),
        "delivery": str(delivery.resolve()),
        "delivery_md": str(delivery.with_suffix(".md").resolve())
        if delivery.with_suffix(".md").is_file()
        else None,
        "matrix_report": str(matrix_report.resolve()),
        "known_solutions_attach": ks_meta,
        "ontology": "handoff_ship_not_lambda_eq_gamma",
        "note": (
            "Commercial ship complete; openable PDBs + pin; not enrichment. "
            "Optional PARTNER_SCIENCE_ANNEX is informational only."
        ),
    }
    ship_path = Path(args.releases) / "SHIP.json"
    ship_path.parent.mkdir(parents=True, exist_ok=True)
    ship_path.write_text(json.dumps(ship, indent=2) + "\n", encoding="utf-8")
    ship_md = write_ship_md(ship, Path(args.releases) / "SHIP.md")
    ship["ship_md"] = str(ship_md.resolve())
    # also copy brief ship summary next to matrix
    if matrix_report.parent.is_dir():
        write_ship_md(ship, matrix_report.parent / "SHIP.md")
        (matrix_report.parent / "SHIP.json").write_text(
            json.dumps(ship, indent=2) + "\n", encoding="utf-8"
        )

    if ship["ok"] and not args.no_bundle:
        try:
            bundle = build_partner_receipt_bundle(
                releases_dir=args.releases,
                matrix_dir=matrix_report.parent,
                label=args.label,
            )
            ship["partner_receipt_bundle"] = bundle.get("zip_path")
            ship["partner_receipt_bundle_sha256"] = bundle.get("zip_sha256")
            logger.info(
                "partner receipt bundle → %s",
                bundle.get("zip_path"),
            )
            # self-verify bundle after write
            bv = verify_partner_receipt_bundle(bundle["zip_path"])
            ship["partner_receipt_bundle_ok"] = bv.get("ok")
            if not bv.get("ok"):
                logger.error("receipt bundle verify failed: %s", bv.get("reasons"))
                ship["ok"] = False
            else:
                logger.info("partner receipt bundle verify ok")
        except Exception as exc:  # noqa: BLE001
            logger.warning("receipt bundle skipped: %s", exc)

    ship_path.write_text(json.dumps(ship, indent=2) + "\n", encoding="utf-8")
    write_releases_catalog(args.releases)
    logger.info("SHIP.json → %s ok=%s md=%s", ship_path, ship["ok"], ship_md)
    print(json.dumps(ship))
    return 0 if ship["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
