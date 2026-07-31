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
from realm.handoff.package import write_ship_md
from realm.handoff.verify import verify_delivery_receipt, verify_dual_gate_pin

logger = logging.getLogger("handoff_ship")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Commercial ship: optional matrix → DELIVERY → verify → status"
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
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

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
        "ontology": "handoff_ship_not_lambda_eq_gamma",
        "note": "Commercial ship complete; openable PDBs + pin; not enrichment.",
    }
    ship_path = Path(args.releases) / "SHIP.json"
    ship_path.parent.mkdir(parents=True, exist_ok=True)
    ship_path.write_text(json.dumps(ship, indent=2) + "\n", encoding="utf-8")
    ship_md = write_ship_md(ship, Path(args.releases) / "SHIP.md")
    ship["ship_md"] = str(ship_md.resolve())
    ship_path.write_text(json.dumps(ship, indent=2) + "\n", encoding="utf-8")
    # also copy brief ship summary next to matrix
    if matrix_report.parent.is_dir():
        write_ship_md(ship, matrix_report.parent / "SHIP.md")
        (matrix_report.parent / "SHIP.json").write_text(
            json.dumps(ship, indent=2) + "\n", encoding="utf-8"
        )
    logger.info("SHIP.json → %s ok=%s md=%s", ship_path, ship["ok"], ship_md)
    print(json.dumps(ship))
    return 0 if ship["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
