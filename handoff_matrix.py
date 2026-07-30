#!/usr/bin/env python3
"""Run dual-gate handoff matrix: probe + holdout (commercial validation pair).

Exports each token with package/verify/quality_gate/RELEASE/archive, then
optionally verifies each dated archive. Does not change LengthPolicy.
Never lambda=gamma. Enrichment is not a success metric.
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

from handoff_campaign import main as campaign_main
from realm.handoff.verify import verify_archive_dir, verify_dual_gate_pin

logger = logging.getLogger("handoff_matrix")

# Commercial validation pair: probe (train) + holdout (generalization)
DEFAULT_TOKENS = ("probe", "holdout")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Dual-gate handoff matrix: probe + holdout campaigns + archive verify"
    )
    p.add_argument(
        "--tokens",
        type=str,
        default=",".join(DEFAULT_TOKENS),
        help="comma tokens: probe,holdout,default (default: probe,holdout)",
    )
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument(
        "--out-root",
        type=Path,
        default=Path("out/matrix"),
        help="parent for per-token campaign dirs (default: out/matrix)",
    )
    p.add_argument(
        "--archive-dir",
        type=Path,
        default=Path("out/releases"),
        help="dated release archive root",
    )
    p.add_argument("--top-k", type=int, default=2)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--with-enrichment", action="store_true")
    p.add_argument("--no-biopython-check", action="store_true")
    p.add_argument(
        "--require-biopython",
        action="store_true",
        help="pass through: quality gate requires BioPython open",
    )
    p.add_argument("--no-archive", action="store_true")
    p.add_argument(
        "--no-verify-archives",
        action="store_true",
        help="skip ARCHIVE.json integrity check after each token",
    )
    p.add_argument("--resume", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    tokens = [t.strip().lower() for t in str(args.tokens).split(",") if t.strip()]
    if not tokens:
        logger.error("no tokens")
        return 2

    pin = verify_dual_gate_pin()
    if not pin.get("ok"):
        logger.error("dual-gate pin failed: %s", pin)
        return 4

    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    overall_ok = True

    for tok in tokens:
        camp_dir = out_root / f"campaign_{tok}"
        pkg_dir = out_root / f"campaign_{tok}_pkg"
        label = f"matrix-{tok}"
        logger.info("=== matrix token=%s → %s ===", tok, camp_dir)
        argv_c = [
            "--pdb-ids",
            tok,
            "--knobs",
            str(args.knobs),
            "--out-dir",
            str(camp_dir),
            "--package-dir",
            str(pkg_dir),
            "--top-k",
            str(int(args.top_k)),
            "-k",
            str(int(args.k)),
            "--release-label",
            label,
            "--archive-dir",
            str(args.archive_dir),
        ]
        if args.with_enrichment:
            argv_c.append("--with-enrichment")
        if args.no_biopython_check:
            argv_c.append("--no-biopython-check")
        if args.require_biopython:
            argv_c.append("--require-biopython")
        if args.resume:
            argv_c.append("--resume")
        if args.dry_run:
            argv_c.append("--dry-run")
        if not args.no_archive and not args.dry_run:
            argv_c.append("--archive")
        if args.v:
            argv_c.append("-v")

        rc = campaign_main(argv_c)
        row: dict = {"token": tok, "campaign_rc": rc, "out_dir": str(camp_dir)}
        if rc != 0:
            overall_ok = False
            row["ok"] = False
            rows.append(row)
            logger.error("token %s failed rc=%s", tok, rc)
            continue

        if args.dry_run:
            row["ok"] = True
            rows.append(row)
            continue

        report_path = camp_dir / "campaign_report.json"
        if report_path.is_file():
            camp = json.loads(report_path.read_text(encoding="utf-8"))
            row["n_ok"] = (camp.get("export") or {}).get("n_ok")
            row["n_ids"] = (camp.get("export") or {}).get("n_ids")
            row["n_pdb"] = ((camp.get("verify") or {}).get("ontology_remarks") or {}).get(
                "n_pdb"
            )
            row["quality_gate"] = (camp.get("quality_gate") or {}).get("ok")
            arch = camp.get("archive") or {}
            row["archive_dir"] = arch.get("archive_dir")
            if (
                not args.no_verify_archives
                and not args.no_archive
                and arch.get("archive_dir")
            ):
                av = verify_archive_dir(arch["archive_dir"])
                row["archive_verify"] = av.get("ok")
                row["archive_checked"] = av.get("n_checked")
                if not av.get("ok"):
                    overall_ok = False
                    logger.error("archive verify failed for %s: %s", tok, av.get("bad"))
        row["ok"] = bool(row.get("quality_gate", True)) and row.get(
            "archive_verify", True
        ) is not False
        if not row["ok"]:
            overall_ok = False
        rows.append(row)

    matrix = {
        "tokens": tokens,
        "pin": pin,
        "rows": rows,
        "ok": overall_ok,
        "ontology": "handoff_matrix_not_lambda_eq_gamma",
        "note": "probe+holdout commercial pair; openable PDBs + pin; not enrichment chase.",
    }
    matrix_path = out_root / "matrix_report.json"
    matrix_path.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
    logger.info("matrix ok=%s → %s", overall_ok, matrix_path)
    for r in rows:
        logger.info(
            "  %s ok=%s n_ok=%s/%s n_pdb=%s archive=%s",
            r.get("token"),
            r.get("ok"),
            r.get("n_ok"),
            r.get("n_ids"),
            r.get("n_pdb"),
            r.get("archive_verify"),
        )
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
