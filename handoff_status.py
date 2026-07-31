#!/usr/bin/env python3
"""Ops status for dual-gate handoff commercial delivery stack.

Reports: dual-gate pin, LATEST release, releases catalog, optional matrix.
Does not re-rank. Never lambda=gamma.
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

from realm.handoff.package import scan_release_drops, write_releases_catalog
from realm.handoff.verify import verify_archive_dir, verify_dual_gate_pin

logger = logging.getLogger("handoff_status")


def _load_known_solutions(
    ks_dir: Path | None,
    releases_dir: Path,
    matrix_report: Path | None,
) -> dict | None:
    """Optional science stamp summary. Never affects commercial ok."""
    candidates: list[Path] = []
    if ks_dir is not None:
        candidates.append(Path(ks_dir))
    candidates.extend(
        [
            Path("out/known_solutions"),
            Path("out/ks_compare_multiseed"),
            Path("out/ks_compare_curated"),
            releases_dir / "known_solutions",
        ]
    )
    if matrix_report:
        parent = Path(matrix_report).parent
        candidates.append(parent / "known_solutions_run")
        candidates.append(parent / "known_solutions")

    root = None
    for c in candidates:
        if (c / "LATEST").is_file() or (c / "PARTNER_SCIENCE_ANNEX.json").is_file():
            root = c
            break
        if (c / "INDEX.json").is_file():
            root = c
            break
    if root is None:
        # releases root may have annex attached flat
        if (releases_dir / "PARTNER_SCIENCE_ANNEX.json").is_file():
            annex = {}
            try:
                annex = json.loads(
                    (releases_dir / "PARTNER_SCIENCE_ANNEX.json").read_text(
                        encoding="utf-8"
                    )
                )
            except Exception as exc:  # noqa: BLE001
                return {"error": str(exc), "path": str(releases_dir)}
            return {
                "attached_at_releases": True,
                "path": str(releases_dir.resolve()),
                "pin": annex.get("pin"),
                "has_compare": (releases_dir / "DECOY_MODE_COMPARE.json").is_file(),
                "mean_enrichment_by_tag": annex.get("mean_enrichment_by_tag"),
                "note": "Science annex on releases; not ACCEPTANCE.",
            }
        return None

    stamp = root
    if (root / "LATEST").is_file():
        try:
            stamp = Path((root / "LATEST").read_text(encoding="utf-8").strip())
        except Exception:  # noqa: BLE001
            stamp = root

    out: dict = {
        "root": str(root.resolve()) if root.exists() else str(root),
        "stamp": str(stamp.resolve()) if stamp.exists() else str(stamp),
        "note": "Science evidence only; never gates commercial accept/ship.",
    }
    pin_p = stamp / "pin.json"
    if pin_p.is_file():
        try:
            out["pin"] = json.loads(pin_p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            out["pin_error"] = str(exc)
    annex_p = stamp / "PARTNER_SCIENCE_ANNEX.json"
    if not annex_p.is_file():
        annex_p = root / "PARTNER_SCIENCE_ANNEX.json"
    if annex_p.is_file():
        try:
            annex = json.loads(annex_p.read_text(encoding="utf-8"))
            out["annex_kind"] = annex.get("kind")
            out["mean_enrichment_by_tag"] = annex.get("mean_enrichment_by_tag")
            out["counts"] = annex.get("counts")
            if annex.get("decoy_mode_compare"):
                out["decoy_mode_compare"] = annex.get("decoy_mode_compare")
        except Exception as exc:  # noqa: BLE001
            out["annex_error"] = str(exc)
    cmp_p = stamp / "DECOY_MODE_COMPARE.json"
    if not cmp_p.is_file():
        cmp_p = root / "DECOY_MODE_COMPARE.json"
    if cmp_p.is_file():
        try:
            cmp_ = json.loads(cmp_p.read_text(encoding="utf-8"))
            out["has_compare"] = True
            out["compare_deltas_vs_soft"] = cmp_.get("deltas_vs_soft")
            out["compare_modes"] = list((cmp_.get("by_mode") or {}).keys())
            # slim all_ok per mode
            out["compare_all_enr"] = {
                m: (b.get("all_ok") or {}).get("mean_enrichment")
                for m, b in (cmp_.get("by_mode") or {}).items()
            }
        except Exception as exc:  # noqa: BLE001
            out["compare_error"] = str(exc)
    else:
        out["has_compare"] = False
    idx_p = root / "INDEX.json"
    if idx_p.is_file():
        try:
            idx = json.loads(idx_p.read_text(encoding="utf-8"))
            out["index_n_stamps"] = idx.get("n_stamps")
        except Exception:  # noqa: BLE001
            pass
    return out


def build_status(
    *,
    releases_dir: Path,
    matrix_report: Path | None = None,
    verify_latest: bool = False,
    rebuild_catalog: bool = True,
    known_solutions_dir: Path | None = None,
) -> dict:
    pin = verify_dual_gate_pin()
    catalog_path = None
    if rebuild_catalog and releases_dir.is_dir():
        catalog_path = write_releases_catalog(releases_dir)

    latest = None
    latest_path = releases_dir / "LATEST.json"
    if latest_path.is_file():
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            latest = {"error": str(exc)}

    drops = scan_release_drops(releases_dir) if releases_dir.is_dir() else []
    archive_verify = None
    acceptance = None
    attestation = None
    if latest and latest.get("archive_dir"):
        adir = Path(latest["archive_dir"])
        acc_path = adir / "ACCEPTANCE.json"
        if acc_path.is_file():
            try:
                acceptance = json.loads(acc_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                acceptance = {"error": str(exc)}
        att_path = adir / "ATTESTATION.json"
        if att_path.is_file():
            try:
                attestation = json.loads(att_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                attestation = {"error": str(exc)}
        if verify_latest:
            archive_verify = verify_archive_dir(adir)

    matrix = None
    if matrix_report and Path(matrix_report).is_file():
        try:
            matrix = json.loads(Path(matrix_report).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            matrix = {"error": str(exc)}

    ok = pin.get("ok") is True
    if archive_verify is not None and archive_verify.get("ok") is not True:
        ok = False
    if matrix is not None and matrix.get("ok") is False:
        ok = False
    if isinstance(acceptance, dict) and acceptance.get("accepted") is False:
        ok = False
    matrix_acceptance = None
    if isinstance(matrix, dict) and matrix.get("acceptance"):
        matrix_acceptance = matrix.get("acceptance")
        if matrix_acceptance.get("ok") is False:
            ok = False
    elif matrix_report:
        ma_path = Path(matrix_report).parent / "matrix_acceptance.json"
        if ma_path.is_file():
            try:
                matrix_acceptance = json.loads(ma_path.read_text(encoding="utf-8"))
                if matrix_acceptance.get("ok") is False:
                    ok = False
            except Exception as exc:  # noqa: BLE001
                matrix_acceptance = {"error": str(exc)}

    return {
        "ok": ok,
        "pin": pin,
        "releases_dir": str(releases_dir.resolve()) if releases_dir.exists() else str(releases_dir),
        "n_drops": len(drops),
        "latest": latest,
        "acceptance": (
            {
                "accepted": acceptance.get("accepted"),
                "n_pdb": (acceptance.get("criteria") or {})
                .get("openable_pdbs", {})
                .get("n_pdb"),
                "label": acceptance.get("label"),
                "path": str(
                    Path(latest["archive_dir"]) / "ACCEPTANCE.json"
                )
                if latest and latest.get("archive_dir")
                else None,
            }
            if isinstance(acceptance, dict) and "error" not in acceptance
            else acceptance
        ),
        "attestation": (
            {
                "payload_sha256": attestation.get("payload_sha256"),
                "n_digests": len(attestation.get("digests") or {}),
                "acceptance": attestation.get("acceptance"),
                "pin_ok": (attestation.get("pin") or {}).get("ok"),
            }
            if isinstance(attestation, dict) and "error" not in attestation
            else attestation
        ),
        "archive_verify": archive_verify,
        "catalog_index": str(catalog_path.resolve()) if catalog_path else None,
        "drops_head": drops[:8],
        "matrix": (
            {
                "ok": matrix.get("ok") if isinstance(matrix, dict) else None,
                "tokens": matrix.get("tokens") if isinstance(matrix, dict) else None,
                "rows": matrix.get("rows") if isinstance(matrix, dict) else None,
                "acceptance": matrix_acceptance,
                "path": str(Path(matrix_report).resolve()) if matrix_report else None,
            }
            if matrix is not None
            else None
        ),
        "matrix_acceptance": matrix_acceptance,
        "delivery": _load_delivery(releases_dir, matrix_report),
        "known_solutions": _load_known_solutions(
            known_solutions_dir, releases_dir, matrix_report
        ),
        "ontology": "handoff_status_not_lambda_eq_gamma",
        "note": (
            "Ops view only; acceptance metric is openable PDBs + pin. "
            "known_solutions is informational science evidence only."
        ),
    }


def _load_delivery(
    releases_dir: Path,
    matrix_report: Path | None,
) -> dict | None:
    candidates: list[Path] = [
        releases_dir / "LATEST_DELIVERY.json",
        releases_dir / "DELIVERY.json",
    ]
    if matrix_report:
        candidates.insert(0, Path(matrix_report).parent / "DELIVERY.json")
    for p in candidates:
        if p.is_file():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                md = p.with_suffix(".md")
                return {
                    "shippable": d.get("shippable"),
                    "n_pdb_total": (d.get("matrix_acceptance") or {}).get(
                        "n_pdb_total"
                    ),
                    "n_accepted": (d.get("matrix_acceptance") or {}).get("n_accepted"),
                    "payload_sha256": d.get("payload_sha256"),
                    "path": str(p.resolve()),
                    "delivery_md": str(md.resolve()) if md.is_file() else None,
                }
            except Exception as exc:  # noqa: BLE001
                return {"error": str(exc), "path": str(p)}
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Dual-gate handoff ops status (pin, LATEST, catalog, matrix)"
    )
    p.add_argument(
        "--releases",
        type=Path,
        default=Path("out/releases"),
        help="releases root (default: out/releases)",
    )
    p.add_argument(
        "--matrix-report",
        type=Path,
        default=None,
        help="optional matrix_report.json path",
    )
    p.add_argument(
        "--verify-latest",
        action="store_true",
        help="run ARCHIVE.json integrity check on LATEST drop",
    )
    p.add_argument(
        "--no-rebuild-catalog",
        action="store_true",
        help="do not rewrite INDEX.json/INDEX.md",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="write status JSON (default: <releases>/STATUS.json)",
    )
    p.add_argument(
        "--known-solutions",
        type=Path,
        default=None,
        help=(
            "optional known-solutions out dir (stamp parent with LATEST); "
            "auto-detects common out/ paths if omitted"
        ),
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    matrix_path = args.matrix_report
    if matrix_path is None:
        cand = Path("out/matrix/matrix_report.json")
        if cand.is_file():
            matrix_path = cand

    status = build_status(
        releases_dir=Path(args.releases),
        matrix_report=matrix_path,
        verify_latest=bool(args.verify_latest),
        rebuild_catalog=not bool(args.no_rebuild_catalog),
        known_solutions_dir=args.known_solutions,
    )

    out = Path(args.report) if args.report else Path(args.releases) / "STATUS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    pin = status.get("pin") or {}
    logger.info(
        "status ok=%s pin soft_T=%s drops=%s latest=%s → %s",
        status.get("ok"),
        pin.get("soft_T"),
        status.get("n_drops"),
        (status.get("latest") or {}).get("label"),
        out,
    )
    if status.get("matrix"):
        logger.info(
            "matrix ok=%s tokens=%s",
            status["matrix"].get("ok"),
            status["matrix"].get("tokens"),
        )
    if status.get("matrix_acceptance"):
        ma = status["matrix_acceptance"] or {}
        logger.info(
            "matrix_acceptance ok=%s n_accepted=%s n_pdb_total=%s",
            ma.get("ok"),
            ma.get("n_accepted"),
            ma.get("n_pdb_total"),
        )
    if status.get("known_solutions"):
        ks = status["known_solutions"] or {}
        logger.info(
            "known_solutions has_compare=%s modes=%s all_enr=%s (science only)",
            ks.get("has_compare"),
            ks.get("compare_modes"),
            ks.get("compare_all_enr"),
        )
    if status.get("delivery"):
        logger.info(
            "delivery shippable=%s n_pdb_total=%s payload=%s",
            (status.get("delivery") or {}).get("shippable"),
            (status.get("delivery") or {}).get("n_pdb_total"),
            ((status.get("delivery") or {}).get("payload_sha256") or "")[:16],
        )
    if status.get("archive_verify"):
        logger.info(
            "latest archive verify ok=%s checked=%s",
            status["archive_verify"].get("ok"),
            status["archive_verify"].get("n_checked"),
        )

    if status.get("acceptance"):
        logger.info(
            "latest acceptance accepted=%s n_pdb=%s",
            (status.get("acceptance") or {}).get("accepted"),
            (status.get("acceptance") or {}).get("n_pdb"),
        )
    if status.get("attestation"):
        logger.info(
            "latest attestation digests=%s payload=%s",
            (status.get("attestation") or {}).get("n_digests"),
            ((status.get("attestation") or {}).get("payload_sha256") or "")[:16],
        )

    # human one-liner to stdout for scripting
    print(
        json.dumps(
            {
                "ok": status.get("ok"),
                "soft_T": pin.get("soft_T"),
                "n_drops": status.get("n_drops"),
                "latest_label": (status.get("latest") or {}).get("label"),
                "accepted": (status.get("acceptance") or {}).get("accepted"),
                "n_pdb": (status.get("acceptance") or {}).get("n_pdb"),
                "shippable": (status.get("delivery") or {}).get("shippable"),
                "report": str(out.resolve()),
            }
        )
    )
    return 0 if status.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
