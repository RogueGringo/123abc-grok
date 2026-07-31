#!/usr/bin/env python3
"""Geometry self-check rollup on dual-gate handoff backbone PDBs.

Scans *_bb.pdb under a campaign/package tree and writes PHYSICS_ROLLUP.json.
Informational only — never gates commercial ACCEPTANCE / SHIP.
Never lambda=gamma.
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

from realm.handoff.physics import scan_physics_tree
from realm.handoff.verify import verify_dual_gate_pin

logger = logging.getLogger("handoff_physics")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Physics rollup: geometry self-check on *_bb.pdb trees. "
            "Report-only; not ACCEPTANCE/SHIP."
        )
    )
    p.add_argument(
        "root",
        type=Path,
        nargs="?",
        default=Path("out/campaign_default"),
        help="campaign or package root containing molds/*_bb.pdb",
    )
    p.add_argument(
        "--physics",
        type=str,
        default="geometry",
        help="adapter name (geometry | none)",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    pin = verify_dual_gate_pin()
    if not pin.get("ok"):
        logger.error("dual-gate pin FAIL: %s", pin)
        return 2

    root = Path(args.root)
    if not root.exists():
        logger.error("root missing: %s", root)
        return 3

    rollup = scan_physics_tree(root, adapter=args.physics)
    summary = {
        "ok": rollup.get("ok"),
        "pin_ok": pin.get("ok"),
        "soft_T": pin.get("soft_T"),
        "n_reports": rollup.get("n_reports"),
        "n_ok": rollup.get("n_ok"),
        "n_warn": rollup.get("n_warn"),
        "n_fail": rollup.get("n_fail"),
        "mean_ca_bond": rollup.get("mean_ca_bond"),
        "path": rollup.get("path"),
        "note": "physics rollup informational; not ACCEPTANCE/SHIP",
    }
    print(json.dumps(summary, indent=2))
    # Report-only: WARN/FAIL do not fail CLI unless zero files
    if int(rollup.get("n_reports") or 0) < 1:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
