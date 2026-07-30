#!/usr/bin/env python3
"""Re-stamp RELEASE.md and/or archive an existing dual-gate campaign.

Ops path: after handoff_campaign.py, re-label, re-archive, or re-verify
without re-export. Does not change LengthPolicy. Never lambda=gamma.
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

from realm.handoff.package import (
    archive_partner_release,
    write_acceptance_json,
    write_release_md,
)
from realm.handoff.verify import quality_gate, verify_dual_gate_pin, verify_handoff_tree

logger = logging.getLogger("handoff_release")


def load_campaign(campaign_dir: Path) -> dict:
    report = campaign_dir / "campaign_report.json"
    if not report.is_file():
        raise FileNotFoundError(f"missing campaign_report.json under {campaign_dir}")
    data = json.loads(report.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("campaign_report.json must be an object")
    return data


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Re-stamp RELEASE / archive an existing dual-gate campaign"
    )
    p.add_argument(
        "campaign_dir",
        type=Path,
        help="directory with campaign_report.json (and optional package/zip)",
    )
    p.add_argument(
        "--release-label",
        type=str,
        default=None,
        help="label for RELEASE.md / archive folder",
    )
    p.add_argument(
        "--no-release",
        action="store_true",
        help="do not rewrite RELEASE.md",
    )
    p.add_argument(
        "--archive",
        action="store_true",
        help="write dated snapshot under --archive-dir",
    )
    p.add_argument(
        "--archive-dir",
        type=Path,
        default=Path("out/releases"),
        help="archive root (default: out/releases)",
    )
    p.add_argument(
        "--reverify",
        action="store_true",
        help="re-run verify on package_dir (or campaign_dir) and update report",
    )
    p.add_argument(
        "--require-sha256",
        action="store_true",
        help="with --reverify, require SHA256SUMS",
    )
    p.add_argument("--no-biopython", action="store_true")
    p.add_argument(
        "--skip-preflight",
        action="store_true",
        help="skip dual-gate pin preflight",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    camp = Path(args.campaign_dir)
    if not camp.is_dir():
        logger.error("not a directory: %s", camp)
        return 2

    if not args.skip_preflight:
        pin = verify_dual_gate_pin()
        if not pin.get("ok"):
            logger.error("preflight dual-gate pin failed: %s", pin)
            return 4
        logger.info("preflight pin OK soft_T(n=12)=%s", pin.get("soft_T"))

    try:
        campaign = load_campaign(camp)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        logger.error("%s", exc)
        return 2

    label = args.release_label or "restamp"

    if args.reverify:
        pkg = campaign.get("package") or {}
        root = pkg.get("package_dir") or str(camp)
        report = verify_handoff_tree(
            root,
            require_sha256=bool(args.require_sha256),
            check_biopython=not bool(args.no_biopython),
        )
        campaign["verify"] = report
        gate = quality_gate(
            campaign.get("export"),
            report,
            min_ok_fraction=0.0,
            min_openable_pdbs=1,
            require_verify_ok=True,
        )
        campaign["quality_gate"] = gate
        (camp / "verify_report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        logger.info(
            "reverify ok=%s gate=%s n_pdb=%s",
            report.get("ok"),
            gate.get("ok"),
            (report.get("ontology_remarks") or {}).get("n_pdb"),
        )
        if not report.get("ok") or not gate.get("ok"):
            (camp / "campaign_report.json").write_text(
                json.dumps(campaign, indent=2) + "\n", encoding="utf-8"
            )
            return 3

    if not args.no_release:
        rel = write_release_md(campaign, camp / "RELEASE.md", label=label)
        campaign["release_md"] = str(rel.resolve())
        acc = write_acceptance_json(campaign, camp / "ACCEPTANCE.json", label=label)
        campaign["acceptance_json"] = str(acc.resolve())
        pkg = campaign.get("package") or {}
        pkg_dir = pkg.get("package_dir")
        if pkg_dir and Path(pkg_dir).is_dir():
            for name, src in (("RELEASE.md", rel), ("ACCEPTANCE.json", acc)):
                (Path(pkg_dir) / name).write_text(
                    src.read_text(encoding="utf-8"), encoding="utf-8"
                )
            logger.info("RELEASE.md + ACCEPTANCE.json copied into package dir")

    if args.archive:
        # only archive when gate ok (or no gate yet)
        gate = campaign.get("quality_gate") or {}
        if gate and gate.get("ok") is False:
            logger.error("refusing to archive: quality_gate failed")
            (camp / "campaign_report.json").write_text(
                json.dumps(campaign, indent=2) + "\n", encoding="utf-8"
            )
            return 5
        arch = archive_partner_release(
            campaign,
            archive_root=args.archive_dir,
            label=label,
            campaign_dir=camp,
        )
        campaign["archive"] = arch
        logger.info("archive_dir=%s", arch.get("archive_dir"))

    (camp / "campaign_report.json").write_text(
        json.dumps(campaign, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
