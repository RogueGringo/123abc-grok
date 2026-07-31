#!/usr/bin/env python3
"""Science stamp golden path for dual-gate known solutions.

Runs known-solutions ledger (optional decoy-mode compare), optionally attaches
into releases/matrix, and refreshes ops status. Report-only: never gates
commercial ACCEPTANCE / SHIP / partner receipt.

Pin soft_T(n=12)=0.036 locked. Never λ=γ.
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

from realm.handoff.verify import verify_dual_gate_pin
from realm.validate.known_solutions import (
    attach_report_to_dir,
    run_compare_modes,
    run_known_solutions,
)

logger = logging.getLogger("handoff_science")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Science stamp: known-solutions report/compare + optional attach + status. "
            "Never gates commercial ship/accept."
        )
    )
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("out/known_solutions"),
        help="known-solutions output root",
    )
    p.add_argument("--n-decoys", type=int, default=24)
    p.add_argument("--n-seeds", type=int, default=1)
    p.add_argument(
        "--compare-modes",
        type=str,
        default="soft,mixed,hard",
        help="comma modes (empty string = single soft run)",
    )
    p.add_argument("--skip-expand", action="store_true")
    p.add_argument("--full-seeds", action="store_true")
    p.add_argument(
        "--kabsch-set",
        type=str,
        default="curated",
        choices=("curated", "probe", "holdout", "all", "none"),
    )
    p.add_argument("--kabsch-max", type=int, default=4)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="universe + pin only",
    )
    p.add_argument(
        "--attach-releases",
        type=Path,
        default=None,
        help="copy annex/compare into this releases root (e.g. out/releases)",
    )
    p.add_argument(
        "--attach-matrix",
        type=Path,
        default=None,
        help="copy annex/compare into matrix out-root",
    )
    p.add_argument(
        "--pdf",
        action="store_true",
        default=None,
        help="write PARTNER_SCIENCE_ONEPAGER.pdf (default: on when attaching)",
    )
    p.add_argument(
        "--no-pdf",
        action="store_true",
        help="skip PDF even when attaching",
    )
    p.add_argument(
        "--status",
        action="store_true",
        help="run handoff_status with this science stamp after report",
    )
    p.add_argument(
        "--releases",
        type=Path,
        default=Path("out/releases"),
        help="releases root for --status",
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

    modes = [m.strip() for m in str(args.compare_modes or "").split(",") if m.strip()]
    if args.dry_run:
        report = run_known_solutions(
            knobs_path=args.knobs,
            out_dir=args.out_dir,
            dry_run=True,
            skip_expand=bool(args.skip_expand),
        )
        stamp_dir = Path(report.get("out_dir") or args.out_dir)
        summary: dict = {
            "status": report.get("status"),
            "pin_ok": pin.get("ok"),
            "soft_T": pin.get("soft_T"),
            "universe": (report.get("id_universe") or {}).get("n_total"),
            "out": str(stamp_dir),
            "note": "dry-run; science only",
        }
        want_pdf = bool(args.pdf) or (
            not args.no_pdf
            and (args.attach_releases is not None or args.attach_matrix is not None)
        )
        if want_pdf or args.pdf:
            try:
                from realm.validate.known_solutions_pdf import write_partner_science_pdf

                summary["pdf"] = str(write_partner_science_pdf(stamp_dir))
            except Exception as exc:  # noqa: BLE001
                summary["pdf_error"] = str(exc)
        if args.attach_releases is not None:
            summary["attach_releases"] = attach_report_to_dir(
                stamp_dir, args.attach_releases
            ).get("ok")
        if args.attach_matrix is not None:
            summary["attach_matrix"] = attach_report_to_dir(
                stamp_dir, args.attach_matrix
            ).get("ok")
        if args.status:
            from handoff_status import build_status

            st = build_status(
                releases_dir=Path(args.releases),
                known_solutions_dir=Path(args.out_dir),
                rebuild_catalog=False,
            )
            status_path = Path(args.releases) / "STATUS.json"
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
            summary["status_ok"] = st.get("ok")
            summary["status_report"] = str(status_path.resolve())
            summary["status_has_pdf"] = (st.get("known_solutions") or {}).get(
                "has_science_pdf"
            )
        print(json.dumps(summary))
        return 0

    if not args.knobs.is_file():
        logger.error("knobs not found: %s", args.knobs)
        return 2

    if modes and modes != ["soft"]:
        rollup = run_compare_modes(
            knobs_path=args.knobs,
            out_dir=args.out_dir,
            modes=modes,
            n_decoys=args.n_decoys,
            n_seeds=args.n_seeds,
            skip_expand=bool(args.skip_expand),
            full_seeds=bool(args.full_seeds),
            kabsch_set=args.kabsch_set,
            kabsch_max=args.kabsch_max,
        )
        stamp_dir = Path(rollup.get("out_dir") or args.out_dir)
        summary = {
            "status": rollup.get("status"),
            "pin_ok": pin.get("ok"),
            "soft_T": pin.get("soft_T"),
            "modes": rollup.get("modes"),
            "compare_all_enr": {
                m: ((b.get("all_ok") or {}).get("mean_enrichment"))
                for m, b in ((rollup.get("compare") or {}).get("by_mode") or {}).items()
            },
            "deltas_vs_soft": (rollup.get("compare") or {}).get("deltas_vs_soft"),
            "out": str(stamp_dir),
            "note": "science stamp only; not ACCEPTANCE/SHIP",
        }
    else:
        report = run_known_solutions(
            knobs_path=args.knobs,
            out_dir=args.out_dir,
            n_decoys=args.n_decoys,
            n_seeds=args.n_seeds,
            skip_expand=bool(args.skip_expand),
            full_seeds=bool(args.full_seeds),
            kabsch_set=args.kabsch_set,
            kabsch_max=args.kabsch_max,
            decoy_mode="soft",
        )
        stamp_dir = Path(report.get("out_dir") or args.out_dir)
        agg = report.get("aggregates") or {}
        summary = {
            "status": report.get("status"),
            "pin_ok": pin.get("ok"),
            "soft_T": pin.get("soft_T"),
            "n_ok": agg.get("n_ok"),
            "n_attempted": agg.get("n_attempted"),
            "mean_enrichment_all": (agg.get("all_ok") or {}).get("mean_enrichment"),
            "out": str(stamp_dir),
            "note": "science stamp only; not ACCEPTANCE/SHIP",
        }

    want_pdf = bool(args.pdf) or (
        not args.no_pdf
        and (args.attach_releases is not None or args.attach_matrix is not None)
    )
    if want_pdf:
        from realm.validate.known_solutions_pdf import write_partner_science_pdf

        try:
            pdf_path = write_partner_science_pdf(stamp_dir)
            summary["pdf"] = str(pdf_path)
            logger.info("science PDF → %s", pdf_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("science PDF: %s", exc)
            summary["pdf_error"] = str(exc)

    attach_meta = {}
    if args.attach_releases is not None:
        attach_meta["releases"] = attach_report_to_dir(stamp_dir, args.attach_releases)
        logger.info(
            "attached to releases ok=%s compare=%s",
            attach_meta["releases"].get("ok"),
            attach_meta["releases"].get("has_decoy_mode_compare"),
        )
    if args.attach_matrix is not None:
        attach_meta["matrix"] = attach_report_to_dir(stamp_dir, args.attach_matrix)
        logger.info(
            "attached to matrix ok=%s",
            attach_meta["matrix"].get("ok"),
        )
    if attach_meta:
        summary["attach"] = {
            k: {"ok": v.get("ok"), "has_compare": v.get("has_decoy_mode_compare")}
            for k, v in attach_meta.items()
        }

    if args.status:
        from handoff_status import build_status

        st = build_status(
            releases_dir=Path(args.releases),
            known_solutions_dir=Path(args.out_dir),
            rebuild_catalog=True,
        )
        status_path = Path(args.releases) / "STATUS.json"
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
        summary["status_ok"] = st.get("ok")
        summary["status_report"] = str(status_path.resolve())
        summary["status_ks_compare"] = (st.get("known_solutions") or {}).get(
            "compare_all_enr"
        )
        logger.info(
            "status commercial_ok=%s science_compare=%s → %s",
            st.get("ok"),
            summary.get("status_ks_compare"),
            status_path,
        )

    print(json.dumps(summary, indent=2))
    # science path never fails commercial: only pin/config/empty fail
    if summary.get("status") in ("PIN_FAIL", "EMPTY_UNIVERSE", "FAIL"):
        return 2 if summary.get("status") == "PIN_FAIL" else 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
