"""Package dual-gate handoff outputs for external partners.

Builds a self-contained directory (and optional zip) with:
  - PDB CA/bb files (and decorated if present)
  - manifest.tsv / enrichment_summary.tsv when available
  - PARTNER_README.md (how to open / ontology disclaimer)
  - SHA256SUMS.txt

Does **not** re-rank or change dual-gate LengthPolicy numbers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def write_acceptance_json(
    campaign: dict[str, Any],
    path: Path | str,
    *,
    label: str | None = None,
) -> Path:
    """Partner acceptance record: pin + openable PDBs + gate (not enrichment).

    Machine-readable criteria for handoff delivery. Never lambda=gamma.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    exp = campaign.get("export") or {}
    pkg = campaign.get("package") or {}
    ver = campaign.get("verify") or {}
    gate = campaign.get("quality_gate") or {}
    pin = (ver.get("pin") or gate.get("pin") or {})
    remarks = ver.get("ontology_remarks") or {}
    bio = ver.get("biopython") or {}
    sha = ver.get("sha256") or {}
    n_pdb = int(remarks.get("n_pdb") or gate.get("n_pdb") or 0)
    n_ok = int(exp.get("n_ok") or 0)
    n_ids = int(exp.get("n_ids") or 0)

    pin_ok = pin.get("ok") is True and abs(float(pin.get("soft_T", pin.get("expected_soft_T", -1)) or -1) - 0.036) < 1e-9
    openable_ok = n_pdb >= 1 and remarks.get("ok") is not False
    gate_ok = gate.get("ok") is True
    sha_ok = sha.get("ok") is not False  # True or skipped None
    # overall accept: pin + gate + openable; bio only if required in gate
    accepted = bool(pin_ok and gate_ok and openable_ok and n_ok >= 1)

    record = {
        "label": label or "dual-gate-handoff",
        "accepted": accepted,
        "created_utc": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "criteria": {
            "dual_gate_pin": {
                "required": True,
                "expected_soft_T_n12": 0.036,
                "soft_T": pin.get("soft_T"),
                "seq_mix": pin.get("seq_mix"),
                "face_weight": pin.get("face_weight"),
                "ok": pin_ok,
            },
            "structures_exported": {
                "required": True,
                "n_ok": n_ok,
                "n_ids": n_ids,
                "ok": n_ok >= 1 and (n_ids == 0 or n_ok == n_ids or gate_ok),
            },
            "openable_pdbs": {
                "required": True,
                "n_pdb": n_pdb,
                "ontology_remark_ok": remarks.get("ok"),
                "ok": openable_ok,
                "note": "Primary commercial success metric",
            },
            "quality_gate": {
                "required": True,
                "ok": gate_ok,
                "reasons": gate.get("reasons") or [],
                "require_biopython": gate.get("require_biopython"),
            },
            "package_sha256": {
                "required": False,
                "ok": sha.get("ok"),
                "n_checked": sha.get("n_checked"),
            },
            "biopython_open": {
                "required": bool(gate.get("require_biopython")),
                "ok": bio.get("ok"),
                "skipped": bio.get("skipped"),
            },
        },
        "not_acceptance_criteria": [
            "mean_enrichment",
            "top20_count",
            "lambda_eq_gamma",
            "RH_claims",
        ],
        "ids": list(campaign.get("ids") or []),
        "package": {
            "package_dir": pkg.get("package_dir"),
            "zip_path": pkg.get("zip_path"),
            "zip_sha256": pkg.get("zip_sha256"),
        },
        "ontology": "handoff_acceptance_not_lambda_eq_gamma",
        "verify_cli": "python handoff_verify.py <package_dir> --require-sha256",
        "note": "Accept on openable PDBs + dual-gate pin + quality_gate; never enrichment score-chase.",
    }
    dest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    logger.info("ACCEPTANCE.json accepted=%s → %s", accepted, dest)
    return dest


def write_release_md(
    campaign: dict[str, Any],
    path: Path | str,
    *,
    label: str | None = None,
) -> Path:
    """Partner-facing RELEASE notes from a campaign_report dict.

    Success metric: openable PDBs + dual-gate pin + quality_gate.
    Does not re-rank. Never lambda=gamma.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    exp = campaign.get("export") or {}
    pkg = campaign.get("package") or {}
    ver = campaign.get("verify") or {}
    gate = campaign.get("quality_gate") or {}
    pin = (ver.get("pin") or gate.get("pin") or {})
    remarks = ver.get("ontology_remarks") or {}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title = label or "dual-gate handoff release"

    lines = [
        f"# RELEASE - {title}",
        "",
        f"Generated: {stamp}",
        "",
        "## Dual-gate pin (locked)",
        "",
        f"- soft_T(n=12): **{pin.get('soft_T', pin.get('expected_soft_T', 0.036))}** (expect 0.036)",
        f"- seq_mix: **{pin.get('seq_mix', 0.0)}**",
        f"- face_weight: **{pin.get('face_weight', 0.08)}**",
        f"- pin ok: **{pin.get('ok')}**",
        "",
        "## Delivery metrics (not enrichment score-chase)",
        "",
        f"- Structures OK: **{exp.get('n_ok')}** / {exp.get('n_ids')}",
        f"- Openable PDBs (ontology REMARK): **{remarks.get('n_pdb', gate.get('n_pdb'))}**",
        f"- Quality gate: **{gate.get('ok')}**"
        + (f" reasons={gate.get('reasons')}" if gate.get("reasons") else ""),
        f"- Verify tree: **{ver.get('ok')}**",
        f"- SHA256 package check: **{(ver.get('sha256') or {}).get('ok')}**",
        "",
        "## Package",
        "",
        f"- package_dir: `{pkg.get('package_dir')}`",
        f"- zip: `{pkg.get('zip_path')}`",
        f"- zip_sha256: `{pkg.get('zip_sha256')}`",
        f"- SUMMARY: `{exp.get('summary_md')}`",
        f"- has_summary_md: {pkg.get('has_summary_md')}",
        "",
    ]
    # Informational enrichment stamp only -- never a release success metric
    agg = exp.get("enrichment_aggregate") or {}
    if agg.get("n_with_enrichment"):
        lines.extend(
            [
                "## Enrichment stamp (informational only)",
                "",
                f"- n_with_enrichment: {agg.get('n_with_enrichment')}",
                f"- mean_enrichment: {agg.get('mean_enrichment')}",
                f"- top20_count: {agg.get('top20_count')}",
                "",
                "Not used for quality_gate / partner acceptance.",
                "",
            ]
        )
    lines.extend(
        [
            "## IDs",
            "",
            ", ".join(str(i) for i in (campaign.get("ids") or [])) or "(none)",
            "",
            "## Ontology",
            "",
            "Crit projection molds only. **Never** lambda=gamma / RH claims.",
            "LengthPolicy production numbers were not modified by this release.",
            "",
            "Verify:",
            "",
            "```bash",
            "python handoff_verify.py <package_dir> --require-sha256",
            "```",
            "",
        ]
    )
    dest.write_text("\n".join(lines), encoding="utf-8")
    logger.info("RELEASE notes → %s", dest)
    return dest


def archive_partner_release(
    campaign: dict[str, Any],
    *,
    archive_root: Path | str = "out/releases",
    label: str | None = None,
    campaign_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Snapshot zip + RELEASE + reports into a dated folder under archive_root.

    Does not re-rank. Partner delivery path for immutable handoff drops.
    """
    root = Path(archive_root)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = "".join(
        c if c.isalnum() or c in ("-", "_") else "-"
        for c in (label or "handoff")
    ).strip("-") or "handoff"
    dest = root / f"{stamp}_{safe}"
    dest.mkdir(parents=True, exist_ok=False)

    copied: list[dict[str, str]] = []
    pkg = campaign.get("package") or {}
    exp = campaign.get("export") or {}

    def _copy_named(src: Path | str | None, name: str) -> None:
        if not src:
            return
        p = Path(src)
        if not p.is_file():
            return
        target = dest / name
        shutil.copy2(p, target)
        copied.append(
            {
                "name": name,
                "source": str(p.resolve()),
                "sha256": _sha256_file(target),
            }
        )

    # Prefer paths on campaign dict; fall back to campaign_dir siblings
    camp = Path(campaign_dir) if campaign_dir else None
    release_src = campaign.get("release_md")
    if not release_src and camp and (camp / "RELEASE.md").is_file():
        release_src = camp / "RELEASE.md"
    report_src = None
    if camp and (camp / "campaign_report.json").is_file():
        report_src = camp / "campaign_report.json"
    summary_src = exp.get("summary_md")
    if not summary_src and camp and (camp / "SUMMARY.md").is_file():
        summary_src = camp / "SUMMARY.md"
    zip_src = pkg.get("zip_path")
    verify_src = None
    if camp and (camp / "verify_report.json").is_file():
        verify_src = camp / "verify_report.json"

    accept_src = campaign.get("acceptance_json")
    if not accept_src and camp and (camp / "ACCEPTANCE.json").is_file():
        accept_src = camp / "ACCEPTANCE.json"

    _copy_named(release_src, "RELEASE.md")
    _copy_named(accept_src, "ACCEPTANCE.json")
    _copy_named(report_src, "campaign_report.json")
    _copy_named(summary_src, "SUMMARY.md")
    _copy_named(verify_src, "verify_report.json")
    if zip_src and Path(zip_src).is_file():
        zname = Path(zip_src).name
        _copy_named(zip_src, zname)

    # Integrity attestation (checksum seal; not a cryptographic signature)
    att_path = write_attestation_json(
        dest,
        label=safe,
        zip_sha256=pkg.get("zip_sha256"),
        ids=list(campaign.get("ids") or []),
        quality_gate_ok=(campaign.get("quality_gate") or {}).get("ok"),
    )
    copied.append(
        {
            "name": "ATTESTATION.json",
            "source": str(att_path.resolve()),
            "sha256": _sha256_file(att_path),
        }
    )

    meta = {
        "archive_dir": str(dest.resolve()),
        "created_utc": stamp,
        "label": safe,
        "n_files": len(copied),
        "files": copied,
        "ids": list(campaign.get("ids") or []),
        "quality_gate_ok": (campaign.get("quality_gate") or {}).get("ok"),
        "zip_sha256": pkg.get("zip_sha256"),
        "attestation": str(att_path.resolve()),
        "ontology": "handoff_archive_not_lambda_eq_gamma",
        "note": "Immutable partner drop: openable PDBs + pin; not enrichment chase.",
    }
    (dest / "ARCHIVE.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    # append ARCHIVE.json checksum
    meta["files"].append(
        {
            "name": "ARCHIVE.json",
            "source": str((dest / "ARCHIVE.json").resolve()),
            "sha256": _sha256_file(dest / "ARCHIVE.json"),
        }
    )
    meta["n_files"] = len(meta["files"])
    (dest / "ARCHIVE.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    latest = write_latest_pointer(meta, root)
    meta["latest_pointer"] = str(latest.resolve())
    catalog = write_releases_catalog(root)
    meta["catalog_index"] = str(catalog.resolve())
    logger.info(
        "archived release → %s files=%d latest=%s catalog=%s",
        dest,
        meta["n_files"],
        latest,
        catalog,
    )
    return meta


def write_attestation_json(
    archive_dir: Path | str,
    *,
    label: str | None = None,
    zip_sha256: str | None = None,
    ids: list[str] | None = None,
    quality_gate_ok: bool | None = None,
) -> Path:
    """Write ATTESTATION.json: SHA256 seal over partner drop artifacts + pin.

    Not a cryptographic signature — integrity attestation for transfer.
    Does not re-rank. Never lambda=gamma.
    """
    root = Path(archive_dir)
    root.mkdir(parents=True, exist_ok=True)
    # pin snapshot (live policy; must match locked production)
    try:
        from realm.validate.length_policy import policy_for

        pol = policy_for(12, base_beta=0.20)
        pin = {
            "soft_T": float(pol.soft_T),
            "seq_mix": float(pol.seq_mix),
            "face_weight": float(pol.face_weight),
            "expected_soft_T": 0.036,
            "ok": abs(float(pol.soft_T) - 0.036) < 1e-12 and float(pol.seq_mix) == 0.0,
        }
    except Exception as exc:  # noqa: BLE001
        pin = {"ok": False, "error": str(exc)}

    watch = [
        "RELEASE.md",
        "ACCEPTANCE.json",
        "SUMMARY.md",
        "campaign_report.json",
        "verify_report.json",
    ]
    digests: dict[str, str] = {}
    for name in watch:
        p = root / name
        if p.is_file():
            digests[name] = _sha256_file(p)
    for p in sorted(root.glob("*.zip")):
        digests[p.name] = _sha256_file(p)

    acceptance = None
    acc_path = root / "ACCEPTANCE.json"
    if acc_path.is_file():
        try:
            acceptance = json.loads(acc_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            acceptance = None

    body = {
        "label": label or "handoff",
        "created_utc": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "pin": pin,
        "ids": list(ids or []),
        "quality_gate_ok": quality_gate_ok,
        "zip_sha256": zip_sha256,
        "digests": digests,
        "acceptance": {
            "accepted": (acceptance or {}).get("accepted"),
            "n_pdb": ((acceptance or {}).get("criteria") or {})
            .get("openable_pdbs", {})
            .get("n_pdb"),
        },
        "ontology": "handoff_attestation_not_lambda_eq_gamma",
        "note": (
            "SHA256 seal over release artifacts + dual-gate pin snapshot. "
            "Not a digital signature. Verify with verify_attestation()."
        ),
    }
    # canonical payload digest (stable key order via json dumps sort_keys)
    payload = json.dumps(
        {
            "pin": body["pin"],
            "digests": body["digests"],
            "zip_sha256": body["zip_sha256"],
            "acceptance": body["acceptance"],
            "ids": body["ids"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    body["payload_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    dest = root / "ATTESTATION.json"
    dest.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    logger.info("ATTESTATION.json payload_sha256=%s → %s", body["payload_sha256"][:16], dest)
    return dest


def write_delivery_receipt(
    *,
    path: Path | str,
    pin: dict[str, Any],
    matrix_acceptance: dict[str, Any] | None = None,
    latest: dict[str, Any] | None = None,
    matrix_report: dict[str, Any] | None = None,
    label: str | None = None,
) -> Path:
    """Partner ship receipt: pin + matrix accept + drop pointers + payload seal.

    Single JSON a partner can file as commercial delivery proof.
    Does not re-rank. Never lambda=gamma. Enrichment is not a criterion.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    drops: list[dict[str, Any]] = []
    tokens = (matrix_acceptance or {}).get("tokens") or {}
    for tok, info in tokens.items():
        adir = info.get("archive_dir")
        row: dict[str, Any] = {
            "token": tok,
            "accepted": info.get("accepted"),
            "n_pdb": info.get("n_pdb"),
            "archive_dir": adir,
            "reasons": info.get("reasons") or [],
        }
        if adir and Path(adir).is_dir():
            arch_meta = Path(adir) / "ARCHIVE.json"
            att_path = Path(adir) / "ATTESTATION.json"
            if arch_meta.is_file():
                try:
                    am = json.loads(arch_meta.read_text(encoding="utf-8"))
                    row["zip_sha256"] = am.get("zip_sha256")
                    row["label"] = am.get("label")
                except Exception:  # noqa: BLE001
                    pass
            if att_path.is_file():
                try:
                    at = json.loads(att_path.read_text(encoding="utf-8"))
                    row["payload_sha256"] = at.get("payload_sha256")
                except Exception:  # noqa: BLE001
                    pass
        drops.append(row)

    pin_ok = pin.get("ok") is True and abs(
        float(pin.get("soft_T", pin.get("expected_soft_T", -1)) or -1) - 0.036
    ) < 1e-9
    matrix_ok = (matrix_acceptance or {}).get("ok") is True if matrix_acceptance else None
    shippable = bool(pin_ok) and (matrix_ok is not False) and (
        matrix_ok is True
        or (
            matrix_acceptance is None
            and latest is not None
            and latest.get("accepted") is True
        )
    )
    if matrix_acceptance is not None:
        shippable = bool(pin_ok and matrix_ok)

    body = {
        "label": label or "dual-gate-commercial-delivery",
        "created_utc": stamp,
        "shippable": shippable,
        "pin": {
            "soft_T": pin.get("soft_T"),
            "seq_mix": pin.get("seq_mix"),
            "face_weight": pin.get("face_weight"),
            "expected_soft_T": 0.036,
            "ok": pin_ok,
        },
        "matrix_acceptance": {
            "ok": (matrix_acceptance or {}).get("ok"),
            "n_tokens": (matrix_acceptance or {}).get("n_tokens"),
            "n_accepted": (matrix_acceptance or {}).get("n_accepted"),
            "n_pdb_total": (matrix_acceptance or {}).get("n_pdb_total"),
        }
        if matrix_acceptance
        else None,
        "latest": {
            "archive_dir": (latest or {}).get("archive_dir"),
            "label": (latest or {}).get("label"),
            "accepted": (latest or {}).get("accepted"),
            "n_pdb": (latest or {}).get("n_pdb"),
            "zip_sha256": (latest or {}).get("zip_sha256"),
            "payload_sha256": (latest or {}).get("payload_sha256"),
        }
        if latest
        else None,
        "drops": drops,
        "matrix_tokens": (matrix_report or {}).get("tokens") if matrix_report else None,
        "acceptance_criteria": [
            "dual_gate_pin soft_T(n=12)=0.036",
            "openable_pdbs_with_ontology_remark",
            "quality_gate",
            "archive_integrity_and_attestation",
        ],
        "not_acceptance_criteria": [
            "mean_enrichment",
            "top20_count",
            "lambda_eq_gamma",
            "RH_claims",
        ],
        "ontology": "handoff_delivery_receipt_not_lambda_eq_gamma",
        "verify_cli": "python handoff_accept.py --from-matrix <matrix_report.json>",
        "status_cli": "python handoff_status.py --verify-latest",
        "note": "Commercial ship receipt; openable PDBs + pin; not enrichment score-chase.",
    }
    payload = json.dumps(
        {
            "pin": body["pin"],
            "matrix_acceptance": body["matrix_acceptance"],
            "drops": body["drops"],
            "latest": body["latest"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    body["payload_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    dest.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    md_path = write_delivery_md(body, dest.with_suffix(".md"))
    body["delivery_md"] = str(md_path.resolve())
    # re-stamp JSON with md path (does not affect payload_sha256)
    dest.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "DELIVERY receipt shippable=%s payload=%s → %s (+ %s)",
        shippable,
        body["payload_sha256"][:16],
        dest,
        md_path.name,
    )
    return dest


def write_delivery_md(receipt: dict[str, Any], path: Path | str) -> Path:
    """Human-readable partner companion for DELIVERY.json."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pin = receipt.get("pin") or {}
    ma = receipt.get("matrix_acceptance") or {}
    latest = receipt.get("latest") or {}
    lines = [
        f"# DELIVERY - {receipt.get('label') or 'dual-gate commercial'}",
        "",
        f"Generated: {receipt.get('created_utc')}",
        f"Shippable: **{receipt.get('shippable')}**",
        "",
        "## Dual-gate pin (locked)",
        "",
        f"- soft_T(n=12): **{pin.get('soft_T')}** (expect 0.036)",
        f"- seq_mix: **{pin.get('seq_mix')}**",
        f"- face_weight: **{pin.get('face_weight')}**",
        f"- pin ok: **{pin.get('ok')}**",
        "",
        "## Matrix acceptance",
        "",
        f"- ok: **{ma.get('ok')}**",
        f"- tokens accepted: **{ma.get('n_accepted')}** / {ma.get('n_tokens')}",
        f"- openable PDBs total: **{ma.get('n_pdb_total')}**",
        "",
        "## Drops",
        "",
        "| token | accepted | n_pdb | label |",
        "|-------|----------|-------|-------|",
    ]
    for d in receipt.get("drops") or []:
        lines.append(
            f"| {d.get('token')} | {d.get('accepted')} | {d.get('n_pdb')} | "
            f"{d.get('label') or ''} |"
        )
    lines.extend(
        [
            "",
            "## Latest pointer",
            "",
            f"- label: `{latest.get('label')}`",
            f"- accepted: **{latest.get('accepted')}** n_pdb={latest.get('n_pdb')}",
            f"- archive: `{latest.get('archive_dir')}`",
            f"- zip_sha256: `{latest.get('zip_sha256')}`",
            "",
            f"payload_sha256: `{receipt.get('payload_sha256')}`",
            "",
            "## Acceptance criteria",
            "",
        ]
    )
    for c in receipt.get("acceptance_criteria") or []:
        lines.append(f"- {c}")
    lines.extend(["", "## Not acceptance criteria", ""])
    for c in receipt.get("not_acceptance_criteria") or []:
        lines.append(f"- {c}")
    lines.extend(
        [
            "",
            "Ontology: Crit projection molds only -- **not** lambda=gamma.",
            "",
            "Verify:",
            "",
            "```bash",
            "python handoff_deliver.py --verify DELIVERY.json",
            "python handoff_ship.py --out-root out/matrix",
            "```",
            "",
        ]
    )
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def write_ship_md(ship: dict[str, Any], path: Path | str) -> Path:
    """One-page ops summary for a successful commercial ship."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SHIP - dual-gate commercial handoff",
        "",
        f"- ok / shippable: **{ship.get('ok')}** / **{ship.get('shippable')}**",
        f"- soft_T(n=12): **{ship.get('soft_T')}** (locked 0.036)",
        f"- matrix tokens accepted: **{ship.get('n_accepted')}**",
        f"- openable PDBs total: **{ship.get('n_pdb_total')}**",
        f"- DELIVERY: `{ship.get('delivery')}`",
        f"- matrix_report: `{ship.get('matrix_report')}`",
        "",
        "Ontology: Crit projection molds only -- **not** lambda=gamma.",
        "Success metric: openable PDBs + dual-gate pin (not enrichment).",
        "",
        "```bash",
        "python handoff_deliver.py --verify out/releases/LATEST_DELIVERY.json",
        "python handoff_accept.py --from-matrix out/matrix/matrix_report.json",
        "```",
        "",
    ]
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def build_partner_receipt_bundle(
    *,
    releases_dir: Path | str,
    matrix_dir: Path | str | None = None,
    zip_path: Path | str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Zip commercial proof artifacts (receipts only — not mold PDBs).

    Lightweight partner email/upload bundle: DELIVERY, SHIP, INDEX, LATEST,
    matrix_acceptance. Full PDB packages stay in per-drop archives.
    """
    root = Path(releases_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = "".join(
        c if c.isalnum() or c in ("-", "_") else "-"
        for c in (label or "receipts")
    ).strip("-") or "receipts"
    zpath = Path(zip_path) if zip_path else root / f"partner_receipts_{stamp}_{safe}.zip"

    names = [
        "LATEST_DELIVERY.json",
        "LATEST_DELIVERY.md",
        "DELIVERY.json",
        "DELIVERY.md",
        "DELIVERY_VERIFY.json",
        "SHIP.json",
        "SHIP.md",
        "LATEST.json",
        "INDEX.json",
        "INDEX.md",
        "STATUS.json",
    ]
    files: list[Path] = []
    for name in names:
        p = root / name
        if p.is_file():
            files.append(p)

    mdir = Path(matrix_dir) if matrix_dir else None
    if mdir and mdir.is_dir():
        for name in (
            "matrix_acceptance.json",
            "matrix_report.json",
            "DELIVERY.json",
            "DELIVERY.md",
            "SHIP.json",
            "SHIP.md",
        ):
            p = mdir / name
            if p.is_file() and p not in files:
                files.append(p)

    if not files:
        raise FileNotFoundError(f"no receipt artifacts under {root}")

    readme = "\n".join(
        [
            "# Dual-gate partner receipt bundle",
            "",
            "Commercial **proof** package (no mold PDBs).",
            "",
            "## Contents",
            "",
            "- `LATEST_DELIVERY.json` / `.md` — ship receipt (pin + openable PDB totals)",
            "- `SHIP.json` / `.md` — ops ship summary",
            "- `INDEX.json` / `.md` — catalog of full drops (PDB zips live in archive dirs)",
            "- `matrix_acceptance.json` — probe/holdout partner-accept rollup",
            "",
            "## Acceptance criteria",
            "",
            "- dual-gate pin soft_T(n=12) = 0.036",
            "- openable PDBs with ontology REMARK",
            "- quality_gate + archive attestation",
            "",
            "## Not acceptance criteria",
            "",
            "- mean_enrichment, top20, lambda=gamma, RH claims",
            "",
            "## Verify",
            "",
            "```bash",
            "python handoff_deliver.py --verify LATEST_DELIVERY.json",
            "```",
            "",
            "Full mold packages: see per-drop `*_pkg.zip` under releases archive dirs.",
            "",
            "Ontology: Crit projection molds only -- **not** lambda=gamma.",
            "",
        ]
    )
    readme_path = root / "_RECEIPT_BUNDLE_README.md"
    readme_path.write_text(readme, encoding="utf-8")
    files.append(readme_path)

    mdir_res = mdir.resolve() if mdir and mdir.exists() else None

    def _under_matrix(f: Path) -> bool:
        if mdir_res is None:
            return False
        try:
            f.resolve().relative_to(mdir_res)
            return True
        except ValueError:
            return False

    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            # flatten matrix files with prefix if under matrix_dir
            arc = f"matrix/{f.name}" if _under_matrix(f) else f.name
            zf.write(f, arcname=arc)

    meta = {
        "zip_path": str(zpath.resolve()),
        "zip_sha256": _sha256_file(zpath),
        "n_files": len(files),
        "files": [f.name for f in files],
        "created_utc": stamp,
        "label": safe,
        "ontology": "handoff_partner_receipt_bundle_not_lambda_eq_gamma",
        "note": "Proof-only zip; mold PDBs not included. Openable PDB counts in DELIVERY.",
        "verify_cli": "python handoff_deliver.py --verify LATEST_DELIVERY.json",
    }
    (root / "PARTNER_RECEIPT_BUNDLE.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    logger.info(
        "partner receipt bundle files=%d zip=%s sha=%s",
        meta["n_files"],
        zpath,
        meta["zip_sha256"][:16],
    )
    return meta


def write_latest_pointer(
    archive_meta: dict[str, Any],
    archive_root: Path | str,
) -> Path:
    """Write LATEST.json (+ LATEST_<label>.json) under archive_root for ops."""
    root = Path(archive_root)
    root.mkdir(parents=True, exist_ok=True)
    # pull acceptance summary from drop if present
    accepted = None
    n_pdb = None
    payload_sha = None
    adir = archive_meta.get("archive_dir")
    if adir:
        acc_p = Path(adir) / "ACCEPTANCE.json"
        if acc_p.is_file():
            try:
                acc = json.loads(acc_p.read_text(encoding="utf-8"))
                accepted = acc.get("accepted")
                n_pdb = (acc.get("criteria") or {}).get("openable_pdbs", {}).get("n_pdb")
            except Exception:  # noqa: BLE001
                pass
        att_p = Path(adir) / "ATTESTATION.json"
        if att_p.is_file():
            try:
                att = json.loads(att_p.read_text(encoding="utf-8"))
                payload_sha = att.get("payload_sha256")
                if accepted is None:
                    accepted = (att.get("acceptance") or {}).get("accepted")
                if n_pdb is None:
                    n_pdb = (att.get("acceptance") or {}).get("n_pdb")
            except Exception:  # noqa: BLE001
                pass
    pointer = {
        "archive_dir": archive_meta.get("archive_dir"),
        "label": archive_meta.get("label"),
        "created_utc": archive_meta.get("created_utc"),
        "zip_sha256": archive_meta.get("zip_sha256"),
        "quality_gate_ok": archive_meta.get("quality_gate_ok"),
        "ids": archive_meta.get("ids"),
        "n_files": archive_meta.get("n_files"),
        "accepted": accepted,
        "n_pdb": n_pdb,
        "payload_sha256": payload_sha,
        "ontology": "handoff_latest_pointer_not_lambda_eq_gamma",
        "verify_cli": "python handoff_verify.py --archive <archive_dir>",
        "accept_cli": "python handoff_accept.py --latest",
        "ship_cli": "python handoff_ship.py --out-root out/matrix",
    }
    dest = root / "LATEST.json"
    dest.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
    label = archive_meta.get("label") or "handoff"
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in str(label))
    labeled = root / f"LATEST_{safe}.json"
    labeled.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
    logger.info("LATEST pointer → %s (also %s)", dest, labeled.name)
    return dest


def scan_release_drops(archive_root: Path | str) -> list[dict[str, Any]]:
    """List dated release directories under archive_root (newest first)."""
    root = Path(archive_root)
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        arch = child / "ARCHIVE.json"
        if not arch.is_file():
            continue
        try:
            meta = json.loads(arch.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            meta = {}
        rows.append(
            {
                "name": child.name,
                "archive_dir": str(child.resolve()),
                "label": meta.get("label"),
                "created_utc": meta.get("created_utc"),
                "quality_gate_ok": meta.get("quality_gate_ok"),
                "zip_sha256": meta.get("zip_sha256"),
                "n_ids": len(meta.get("ids") or []),
                "ids": meta.get("ids"),
                "n_files": meta.get("n_files"),
            }
        )
    # sort by created_utc then name, newest first
    rows.sort(key=lambda r: (r.get("created_utc") or "", r.get("name") or ""), reverse=True)
    return rows


def write_releases_catalog(archive_root: Path | str) -> Path:
    """Write INDEX.json + INDEX.md catalog of all release drops."""
    root = Path(archive_root)
    root.mkdir(parents=True, exist_ok=True)
    drops = scan_release_drops(root)
    latest_path = root / "LATEST.json"
    latest = None
    if latest_path.is_file():
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            latest = None
    delivery = None
    for name in ("LATEST_DELIVERY.json", "DELIVERY.json"):
        dp = root / name
        if dp.is_file():
            try:
                delivery = json.loads(dp.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                delivery = {"path": str(dp)}
            break
    ship = None
    sp = root / "SHIP.json"
    if sp.is_file():
        try:
            ship = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            ship = {"path": str(sp)}
    bundle_meta = None
    bp = root / "PARTNER_RECEIPT_BUNDLE.json"
    if bp.is_file():
        try:
            bundle_meta = json.loads(bp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            bundle_meta = None

    catalog = {
        "archive_root": str(root.resolve()),
        "n_drops": len(drops),
        "latest": latest,
        "delivery": {
            "shippable": (delivery or {}).get("shippable"),
            "n_pdb_total": ((delivery or {}).get("matrix_acceptance") or {}).get(
                "n_pdb_total"
            ),
            "payload_sha256": (delivery or {}).get("payload_sha256"),
        }
        if delivery
        else None,
        "ship": {
            "ok": (ship or {}).get("ok"),
            "shippable": (ship or {}).get("shippable"),
            "n_pdb_total": (ship or {}).get("n_pdb_total"),
        }
        if ship
        else None,
        "partner_receipt_bundle": bundle_meta,
        "drops": drops,
        "ontology": "handoff_releases_catalog_not_lambda_eq_gamma",
        "note": "Catalog of immutable dual-gate partner drops; not enrichment chase.",
        "verify_cli": "python handoff_verify.py --archive <archive_dir>",
        "status_cli": "python handoff_status.py --releases <archive_root>",
        "ship_cli": "python handoff_ship.py --out-root out/matrix",
    }
    idx = root / "INDEX.json"
    idx.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Dual-gate handoff releases catalog",
        "",
        f"- Archive root: `{root}`",
        f"- Drops: **{len(drops)}**",
        f"- Latest: `{((latest or {}).get('archive_dir'))}`",
        f"- DELIVERY shippable: **{(delivery or {}).get('shippable')}**",
        f"- SHIP ok: **{(ship or {}).get('ok')}** openable PDBs: "
        f"**{(ship or {}).get('n_pdb_total') or ((delivery or {}).get('matrix_acceptance') or {}).get('n_pdb_total')}**",
        "",
        "Ontology: Crit projection molds only -- **not** lambda=gamma.",
        "",
        "Proof bundle (no PDBs): `partner_receipts_*.zip` / `PARTNER_RECEIPT_BUNDLE.json`",
        "",
        "| created_utc | label | n_ids | gate | archive |",
        "|-------------|-------|-------|------|---------|",
    ]
    for d in drops:
        lines.append(
            f"| {d.get('created_utc')} | {d.get('label')} | {d.get('n_ids')} | "
            f"{d.get('quality_gate_ok')} | `{d.get('name')}` |"
        )
    lines.append("")
    lines.append("Verify drop: `python handoff_verify.py --archive <archive_dir>`")
    lines.append("Verify delivery: `python handoff_deliver.py --verify LATEST_DELIVERY.json`")
    lines.append("Ship: `python handoff_ship.py --out-root out/matrix`")
    lines.append("")
    (root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("releases catalog → %s drops=%d", idx, len(drops))
    return idx


PARTNER_README = """# Geometric mold handoff package

Generated: {timestamp}
Source directory: `{source}`
Ontology: **Crit projection molds** (ζ substrate scaffolding only).  
**Never** interpret as λ=γ spectral matching or RH claims.

## Contents

| Path | Description |
|------|-------------|
| `molds/` or `<PDB>/molds/` | CA-only (`*_ca.pdb`) and idealized backbone (`*_bb.pdb`) |
| `manifest.tsv` | Per-mold paths, rank scores, soft_T, REMARK check |
| `enrichment_summary.tsv` | Optional dual-gate enrichment stamp (if campaign used `--with-enrichment`) |
| `SUMMARY.md` | Human-readable campaign summary (export batch root) |
| `RELEASE.md` | Partner release notes (pin, openable PDB count, zip SHA) when campaign copied it |
| `ACCEPTANCE.json` | Machine-readable accept/reject: pin + openable PDBs + gate (not enrichment) |
| `ATTESTATION.json` | SHA256 seal over artifacts + pin snapshot (not a digital signature) |
| `batch_index.json` / `index.json` | Machine-readable index + LengthPolicy snapshot |
| `SHA256SUMS.txt` | Checksums of packaged files |

Verify a package with:

```bash
python handoff_verify.py . --require-sha256
```

## How to open

- **PyMOL / ChimeraX / VMD**: load `*_bb.pdb` (N–CA–C–O idealized) or `*_ca.pdb`.
- **BioPython**:
  ```python
  from Bio.PDB import PDBParser
  s = PDBParser(QUIET=True).get_structure("m", "path/to/000_crit_bb.pdb")
  ```
- REMARK lines carry `ONTOLOGY … not_lambda_eq_gamma` and rank metadata.

## Ranking note

Molds are selected with a **locked dual-gate LengthPolicy** (projection-primary Kabsch
softmin + optional sheaf defect). Soft_T / defect_beta are stamped in `index.json`
under `dual_gate.length_policy` and must not be “tuned” in the package without a
new scientific campaign.

## Checksums

```bash
sha256sum -c SHA256SUMS.txt
```

## Contact / provenance

Package built by `realm.handoff.package` from a dual-gate handoff export.
"""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_files(source: Path) -> list[Path]:
    """Files to include (PDB, tsv, json indexes). Skip huge caches."""
    include_suffix = {".pdb", ".tsv", ".json", ".md", ".txt"}
    skip_names = {"__pycache__"}
    out: list[Path] = []
    for p in sorted(source.rglob("*")):
        if not p.is_file():
            continue
        if any(part in skip_names for part in p.parts):
            continue
        if p.suffix.lower() not in include_suffix and p.name not in (
            "manifest.tsv",
            "enrichment_summary.tsv",
            "batch_index.json",
            "index.json",
        ):
            continue
        # skip physics noise if desired? keep small physics json
        out.append(p)
    return out


def build_partner_package(
    source_dir: Path | str,
    *,
    dest_dir: Path | str | None = None,
    zip_path: Path | str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Copy handoff export into a partner package with README + checksums + zip.

    Parameters
    ----------
    source_dir
        Output of ``handoff_export.py --mode dual-gate`` (single or batch root).
    dest_dir
        Package folder (default: ``<source>_package``).
    zip_path
        If set, also write a zip archive.
    """
    src = Path(source_dir).resolve()
    if not src.is_dir():
        raise FileNotFoundError(f"source handoff dir missing: {src}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = label or f"handoff_package_{stamp}"
    dest = Path(dest_dir) if dest_dir else src.parent / name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    files = _collect_files(src)
    if not files:
        raise RuntimeError(f"no packageable files under {src}")

    copied: list[str] = []
    for f in files:
        rel = f.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        copied.append(str(rel).replace("\\", "/"))

    readme = PARTNER_README.format(
        timestamp=stamp,
        source=str(src),
    )
    (dest / "PARTNER_README.md").write_text(readme, encoding="utf-8")
    copied.append("PARTNER_README.md")

    # checksums (paths relative to package root)
    lines = []
    for rel in sorted(copied):
        p = dest / rel
        if p.is_file() and p.name != "SHA256SUMS.txt":
            lines.append(f"{_sha256_file(p)}  {rel}")
    (dest / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    has_summary = (dest / "SUMMARY.md").is_file()
    meta = {
        "label": name,
        "created_utc": stamp,
        "source_dir": str(src),
        "package_dir": str(dest.resolve()),
        "n_files": len(lines) + 1,
        "has_summary_md": has_summary,
        "ontology": "partner_package_not_lambda_eq_gamma",
        "note": "Dual-gate export packaging only; ranking policy not modified.",
        "verify_cli": "python handoff_verify.py <package_dir> --require-sha256",
    }
    (dest / "package_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

    zpath = Path(zip_path) if zip_path else dest.with_suffix(".zip")
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in dest.rglob("*"):
            if p.is_file():
                zf.write(p, arcname=str(p.relative_to(dest)).replace("\\", "/"))
    meta["zip_path"] = str(zpath.resolve())
    meta["zip_sha256"] = _sha256_file(zpath)
    (dest / "package_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

    logger.info(
        "partner package %s files=%d zip=%s",
        dest,
        meta["n_files"],
        meta.get("zip_path"),
    )
    return meta
