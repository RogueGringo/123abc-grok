#!/usr/bin/env python3
"""Partner single-command acceptance of dual-gate handoff package or archive.

Exit 0 only if dual-gate pin, ACCEPTANCE, and integrity checks pass.
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

from realm.handoff.verify import accept_partner_drop

logger = logging.getLogger("handoff_accept")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Partner accept dual-gate handoff package or release archive"
    )
    p.add_argument(
        "root",
        type=Path,
        nargs="?",
        default=None,
        help="package dir, archive dir, or omit with --latest",
    )
    p.add_argument(
        "--latest",
        action="store_true",
        help="accept LATEST drop under --releases (default out/releases)",
    )
    p.add_argument(
        "--releases",
        type=Path,
        default=Path("out/releases"),
        help="releases root for --latest",
    )
    p.add_argument(
        "--require-attestation",
        action="store_true",
        help="require valid ATTESTATION.json (typical for archive drops)",
    )
    p.add_argument(
        "--require-sha256",
        action="store_true",
        help="require SHA256SUMS for package mode",
    )
    p.add_argument(
        "--allow-missing-acceptance",
        action="store_true",
        help="do not require ACCEPTANCE.json (not recommended)",
    )
    p.add_argument("--check-biopython", action="store_true")
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="write accept report JSON (default: <root>/ACCEPT_REPORT.json)",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    root = args.root
    if args.latest:
        latest = Path(args.releases) / "LATEST.json"
        if not latest.is_file():
            logger.error("no LATEST.json under %s", args.releases)
            return 2
        ptr = json.loads(latest.read_text(encoding="utf-8"))
        root = Path(ptr["archive_dir"])
        # archives should have attestation
        if not args.require_attestation:
            args.require_attestation = True
        logger.info("accepting LATEST → %s", root)
    if root is None:
        p.error("root required unless --latest")

    root = Path(root)
    if not root.is_dir():
        logger.error("not a directory: %s", root)
        return 2

    # auto-enable attestation for archive drops
    require_att = bool(args.require_attestation) or (root / "ARCHIVE.json").is_file()

    report = accept_partner_drop(
        root,
        require_acceptance=not bool(args.allow_missing_acceptance),
        require_attestation=require_att,
        require_sha256=bool(args.require_sha256),
        check_biopython=bool(args.check_biopython),
    )

    out = Path(args.report) if args.report else root / "ACCEPT_REPORT.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    logger.info(
        "accept ok=%s mode=%s n_pdb=%s pin=%s reasons=%s → %s",
        report.get("ok"),
        report.get("mode"),
        report.get("n_pdb"),
        (report.get("pin") or {}).get("soft_T"),
        report.get("reasons"),
        out,
    )
    print(
        json.dumps(
            {
                "ok": report.get("ok"),
                "accepted": report.get("accepted"),
                "mode": report.get("mode"),
                "n_pdb": report.get("n_pdb"),
                "soft_T": (report.get("pin") or {}).get("soft_T"),
                "reasons": report.get("reasons"),
                "report": str(out.resolve()),
            }
        )
    )
    return 0 if report.get("ok") else 3


if __name__ == "__main__":
    sys.exit(main())
