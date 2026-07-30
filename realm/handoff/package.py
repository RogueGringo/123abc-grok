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
