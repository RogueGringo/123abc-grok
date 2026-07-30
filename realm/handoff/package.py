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

    _copy_named(release_src, "RELEASE.md")
    _copy_named(report_src, "campaign_report.json")
    _copy_named(summary_src, "SUMMARY.md")
    _copy_named(verify_src, "verify_report.json")
    if zip_src and Path(zip_src).is_file():
        zname = Path(zip_src).name
        _copy_named(zip_src, zname)

    meta = {
        "archive_dir": str(dest.resolve()),
        "created_utc": stamp,
        "label": safe,
        "n_files": len(copied),
        "files": copied,
        "ids": list(campaign.get("ids") or []),
        "quality_gate_ok": (campaign.get("quality_gate") or {}).get("ok"),
        "zip_sha256": pkg.get("zip_sha256"),
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
    logger.info("archived release → %s files=%d", dest, meta["n_files"])
    return meta


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
