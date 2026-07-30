#!/usr/bin/env python3
"""Write dual-gate commercial DELIVERY receipt for partner ship.

Binds matrix_acceptance + LATEST + dual-gate pin into one shippable JSON.
Does not re-rank. Never lambda=gamma. Enrichment is not a criterion.
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

from realm.handoff.package import write_delivery_receipt
from realm.handoff.verify import verify_dual_gate_pin

logger = logging.getLogger("handoff_deliver")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Write commercial DELIVERY.json receipt (pin + matrix + LATEST)"
    )
    p.add_argument(
        "--matrix-report",
        type=Path,
        default=Path("out/matrix/matrix_report.json"),
        help="matrix_report.json (default: out/matrix/matrix_report.json)",
    )
    p.add_argument(
        "--matrix-acceptance",
        type=Path,
        default=None,
        help="matrix_acceptance.json (default: sibling of matrix-report)",
    )
    p.add_argument(
        "--releases",
        type=Path,
        default=Path("out/releases"),
        help="releases root for LATEST.json",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output path (default: <matrix dir>/DELIVERY.json and releases/DELIVERY.json)",
    )
    p.add_argument(
        "--label",
        type=str,
        default="commercial-probe-holdout",
        help="receipt label",
    )
    p.add_argument(
        "--require-shippable",
        action="store_true",
        help="exit non-zero if receipt is not shippable",
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

    matrix_report = None
    matrix_path = Path(args.matrix_report)
    if matrix_path.is_file():
        matrix_report = json.loads(matrix_path.read_text(encoding="utf-8"))
    else:
        logger.warning("matrix report missing: %s", matrix_path)

    ma_path = args.matrix_acceptance
    if ma_path is None and matrix_path.is_file():
        ma_path = matrix_path.parent / "matrix_acceptance.json"
    matrix_acceptance = None
    if ma_path and Path(ma_path).is_file():
        matrix_acceptance = json.loads(Path(ma_path).read_text(encoding="utf-8"))
    elif matrix_report and matrix_report.get("acceptance"):
        matrix_acceptance = matrix_report["acceptance"]

    latest = None
    latest_path = Path(args.releases) / "LATEST.json"
    if latest_path.is_file():
        latest = json.loads(latest_path.read_text(encoding="utf-8"))

    outs: list[Path] = []
    if args.out:
        outs.append(Path(args.out))
    else:
        if matrix_path.parent.exists():
            outs.append(matrix_path.parent / "DELIVERY.json")
        outs.append(Path(args.releases) / "DELIVERY.json")
        outs.append(Path(args.releases) / "LATEST_DELIVERY.json")

    # de-dupe while preserving order
    seen: set[str] = set()
    uniq: list[Path] = []
    for o in outs:
        key = str(o.resolve()) if o.parent.exists() else str(o)
        if key not in seen:
            seen.add(key)
            uniq.append(o)

    primary = None
    for o in uniq:
        primary = write_delivery_receipt(
            path=o,
            pin=pin,
            matrix_acceptance=matrix_acceptance,
            latest=latest,
            matrix_report=matrix_report,
            label=args.label,
        )

    if primary is None:
        logger.error("no output path")
        return 2

    receipt = json.loads(primary.read_text(encoding="utf-8"))
    logger.info(
        "delivery shippable=%s n_pdb_total=%s drops=%s → %s",
        receipt.get("shippable"),
        (receipt.get("matrix_acceptance") or {}).get("n_pdb_total"),
        len(receipt.get("drops") or []),
        primary,
    )
    print(
        json.dumps(
            {
                "ok": receipt.get("shippable"),
                "shippable": receipt.get("shippable"),
                "soft_T": (receipt.get("pin") or {}).get("soft_T"),
                "n_pdb_total": (receipt.get("matrix_acceptance") or {}).get(
                    "n_pdb_total"
                ),
                "n_accepted": (receipt.get("matrix_acceptance") or {}).get("n_accepted"),
                "payload_sha256": receipt.get("payload_sha256"),
                "receipt": str(primary.resolve()),
            }
        )
    )
    if args.require_shippable and not receipt.get("shippable"):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
