"""P5 EOW package ship (D): inventory + integrity hashes after SOLVED.

EOW handoff is post fixed-point only:
  - inventory surveys / LAS / PDFs / xlsx checklists from an EOW-like dir
  - write run_dir/eow/PACKAGE_INDEX.json + SHIP.md (with sha256)
  - refuse SHIP unless SOLVED unless force_ship → UNSOLVED_SHIP banner
  - reference PARTNER_RECIPE (already written on SOLVED by the loop)

Never sets SOLVED from package completeness alone.
Never ROP score-chase. Never retune pin for ship.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

UNSOLVED_SHIP_BANNER = "UNSOLVED_SHIP"
REFUSED_STATUS = "REFUSED_NOT_SOLVED"
SHIPPED_STATUS = "SHIPPED"

# File kind classification (EOW-like client drop)
_LAS_SUFFIXES = {".las"}
_PDF_SUFFIXES = {".pdf"}
_XLSX_SUFFIXES = {".xlsx", ".xls", ".xlsm"}
_SURVEY_NAME_HINTS = (
    "survey",
    "svy",
    "station",
    "md_inc",
    "md-inc",
    "inc_azi",
    "wellpath",
    "directional",
)
_CHECKLIST_NAME_HINTS = (
    "check",
    "paper",
    "eow",
    "handoff",
    "deliver",
    "inventory",
    "manifest",
    "signoff",
    "sign-off",
)
_SKIP_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}


class EowShipRefused(RuntimeError):
    """Raised when SHIP is refused (job not SOLVED and force_ship is false)."""

    def __init__(self, message: str, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.detail = detail or {}


def sha256_file(path: Path | str) -> str:
    """Content hash for integrity (source path + content hash on ship)."""
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_eow_file(path: Path) -> str:
    """Classify one file into inventory kind for PACKAGE_INDEX.

    Kinds: survey | las | pdf | checklist | xlsx | other
    """
    name = path.name.lower()
    stem = path.stem.lower()
    suffix = path.suffix.lower()

    if suffix in _LAS_SUFFIXES:
        return "las"
    if any(h in name or h in stem for h in _SURVEY_NAME_HINTS):
        return "survey"
    if suffix in _PDF_SUFFIXES:
        if any(h in name or h in stem for h in _CHECKLIST_NAME_HINTS):
            return "checklist"
        return "pdf"
    if suffix in _XLSX_SUFFIXES:
        if any(h in name or h in stem for h in _CHECKLIST_NAME_HINTS):
            return "checklist"
        return "xlsx"
    if suffix in {".csv", ".txt", ".tsv"} and any(
        h in name or h in stem for h in _CHECKLIST_NAME_HINTS
    ):
        return "checklist"
    if any(h in name or h in stem for h in _CHECKLIST_NAME_HINTS):
        return "checklist"
    return "other"


def inventory_eow_package(eow_package: Path | str) -> dict[str, Any]:
    """Walk an EOW-like directory; return categorized file inventory + hashes.

    Does not copy files; hashes content in place for provenance.
    """
    root = Path(eow_package)
    if not root.exists():
        raise FileNotFoundError(f"EOW package path not found: {root}")
    if not root.is_dir():
        raise ValueError(f"EOW package must be a directory: {root}")

    files: list[dict[str, Any]] = []
    by_kind: dict[str, list[dict[str, Any]]] = {
        "survey": [],
        "las": [],
        "pdf": [],
        "checklist": [],
        "xlsx": [],
        "other": [],
    }

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.lower() in _SKIP_NAMES:
            continue
        # Skip hidden / temp
        if path.name.startswith(".") or path.name.startswith("~"):
            continue
        rel = path.relative_to(root).as_posix()
        kind = classify_eow_file(path)
        entry = {
            "path": rel,
            "abs_path": str(path.resolve()),
            "kind": kind,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        files.append(entry)
        by_kind.setdefault(kind, []).append(entry)

    counts = {k: len(v) for k, v in by_kind.items()}
    return {
        "eow_package": str(root.resolve()),
        "n_files": len(files),
        "counts": counts,
        "files": files,
        "by_kind": {k: [e["path"] for e in v] for k, v in by_kind.items()},
        "ontology": "job_eow_inventory_not_rop_score",
    }


def _partner_recipe_ref(
    partner_recipe_path: Path | str | None,
    run_dir: Path,
) -> dict[str, Any]:
    """Resolve PARTNER_RECIPE path/hash for SHIP (recipe already on SOLVED)."""
    candidates: list[Path] = []
    if partner_recipe_path:
        candidates.append(Path(partner_recipe_path))
    candidates.append(run_dir / "PARTNER_RECIPE.json")

    for cand in candidates:
        if cand.is_file():
            try:
                body = json.loads(cand.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                body = {}
            return {
                "path": str(cand.resolve()),
                "relative": "PARTNER_RECIPE.json",
                "sha256": sha256_file(cand),
                "solved": body.get("solved"),
                "run_id": body.get("run_id"),
                "free_params": body.get("free_params"),
                "present": True,
            }
    return {
        "path": None,
        "relative": "PARTNER_RECIPE.json",
        "sha256": None,
        "solved": None,
        "run_id": None,
        "free_params": None,
        "present": False,
    }


def write_package_index(index: dict[str, Any], path: Path | str) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return dest


def write_eow_ship_md(ship: dict[str, Any], path: Path | str) -> Path:
    """Human-readable EOW SHIP brief (integrity + recipe pointer)."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    inv = ship.get("inventory") or {}
    counts = inv.get("counts") or {}
    recipe = ship.get("partner_recipe") or {}
    banner = ship.get("banner")
    lines = [
        "# SHIP — EOW package handoff (Job Coherence OS P5)",
        "",
    ]
    if banner:
        lines.extend(
            [
                f"> **BANNER: {banner}**",
                ">",
                "> Job OS was **not** SOLVED. This ship is forced via `--force-ship`.",
                "> Do **not** treat as commercial fixed-point acceptance.",
                "",
            ]
        )
    lines.extend(
        [
            f"- **status:** `{ship.get('status')}`",
            f"- **ok / shipped:** **{ship.get('ok')}** / **{ship.get('shipped')}**",
            f"- **solved:** {ship.get('solved')}",
            f"- **force_ship:** {ship.get('force_ship')}",
            f"- **run_id:** `{ship.get('run_id')}`",
            f"- **eow_package:** `{ship.get('eow_package')}`",
            f"- **n_files:** {inv.get('n_files', 0)}",
            f"- **surveys:** {counts.get('survey', 0)}",
            f"- **LAS:** {counts.get('las', 0)}",
            f"- **PDFs:** {counts.get('pdf', 0)}",
            f"- **checklists (xlsx/pdf/…):** {counts.get('checklist', 0)}",
            f"- **other xlsx:** {counts.get('xlsx', 0)}",
            f"- **other:** {counts.get('other', 0)}",
            f"- **PACKAGE_INDEX:** `{ship.get('package_index')}`",
            f"- **PARTNER_RECIPE:** `{recipe.get('path')}` "
            f"(sha256=`{(recipe.get('sha256') or '')[:16]}…` present={recipe.get('present')})",
            "",
            "## Integrity",
            "",
            "Each inventory entry in `PACKAGE_INDEX.json` carries `sha256` of file content.",
            "Source path + content hash is the provenance pin for ship — not a ROP score.",
            "",
            "## Ontology",
            "",
            "- EOW SHIP is post-SOLVED attach (D), not free-param core.",
            "- PARTNER_RECIPE is free-param + pin stamp for re-run fidelity.",
            "- Package completeness alone never sets SOLVED.",
            "- Never retune SOP pin for ship. Never ζ→ROP claim.",
            "",
            "```bash",
            "python job_coherence.py --resume out/job_os/<run_id> "
            "--eow-package <EOW_DIR>",
            "```",
            "",
        ]
    )
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def ship_eow_package(
    *,
    run_dir: Path | str,
    eow_package: Path | str,
    solved: bool,
    force_ship: bool = False,
    partner_recipe_path: Path | str | None = None,
    run_id: str | None = None,
    free_params: dict[str, Any] | None = None,
    raise_on_refuse: bool = False,
) -> dict[str, Any]:
    """Build eow/PACKAGE_INDEX.json + SHIP.md under run_dir after gate check.

    Gate:
      - SOLVED → ship status SHIPPED
      - not SOLVED + force_ship → ship status UNSOLVED_SHIP with banner
      - not SOLVED + not force → refuse (no artifacts written)

    Returns a ship result dict (ok, shipped, status, paths, inventory, …).
    """
    out = Path(run_dir)
    out.mkdir(parents=True, exist_ok=True)
    eow_root = Path(eow_package)

    base: dict[str, Any] = {
        "kind": "eow_ship",
        "ontology": "job_eow_ship_not_rop_score",
        "run_id": run_id or out.name,
        "run_dir": str(out.resolve()),
        "eow_package": str(eow_root.resolve()) if eow_root.exists() else str(eow_root),
        "solved": bool(solved),
        "force_ship": bool(force_ship),
        "ok": False,
        "shipped": False,
        "refused": False,
        "status": None,
        "banner": None,
        "package_index": None,
        "ship_md": None,
        "partner_recipe": None,
        "inventory": None,
        "free_params": free_params,
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "disclaimers": [
            "EOW SHIP is post-SOLVED attach; not ACCEPTANCE alone.",
            "Package completeness never sets SOLVED without pin + glue.",
            "PARTNER_RECIPE is free-param + pin stamp for re-run.",
            "Never ROP score-chase. Never retune pin for ship.",
        ],
    }

    if not solved and not force_ship:
        detail = {
            **base,
            "refused": True,
            "status": REFUSED_STATUS,
            "reason": (
                "EOW SHIP requires job OS SOLVED fixed-point "
                "(or pass --force-ship for UNSOLVED_SHIP banner)"
            ),
        }
        logger.warning("EOW SHIP refused: %s", detail["reason"])
        if raise_on_refuse:
            raise EowShipRefused(detail["reason"], detail=detail)
        return detail

    # Validate package path before writing
    if not eow_root.exists():
        raise FileNotFoundError(f"EOW package path not found: {eow_root}")
    if not eow_root.is_dir():
        raise ValueError(f"EOW package must be a directory: {eow_root}")

    inventory = inventory_eow_package(eow_root)
    recipe_ref = _partner_recipe_ref(partner_recipe_path, out)
    # Prefer free_params from recipe when present
    if recipe_ref.get("free_params") and free_params is None:
        free_params = recipe_ref["free_params"]

    status = SHIPPED_STATUS if solved else UNSOLVED_SHIP_BANNER
    banner = None if solved else UNSOLVED_SHIP_BANNER

    eow_dir = out / "eow"
    eow_dir.mkdir(parents=True, exist_ok=True)

    index_doc = {
        "kind": "eow_package_index",
        "ontology": "job_eow_package_index_not_rop_score",
        "run_id": base["run_id"],
        "run_dir": str(out.resolve()),
        "status": status,
        "banner": banner,
        "solved": bool(solved),
        "force_ship": bool(force_ship),
        "partner_recipe": recipe_ref,
        "free_params": free_params,
        "inventory": inventory,
        "timestamp_utc": base["timestamp_utc"],
        "note": (
            "Integrity hashes (sha256) per file. "
            "Ship is post-SOLVED (or UNSOLVED_SHIP when forced). "
            "Not ROP prediction. Not pin retune."
        ),
    }
    index_path = write_package_index(index_doc, eow_dir / "PACKAGE_INDEX.json")

    ship_doc = {
        **base,
        "ok": True,
        "shipped": True,
        "refused": False,
        "status": status,
        "banner": banner,
        "package_index": str(index_path.resolve()),
        "partner_recipe": recipe_ref,
        "free_params": free_params,
        "inventory": {
            "eow_package": inventory["eow_package"],
            "n_files": inventory["n_files"],
            "counts": inventory["counts"],
            "by_kind": inventory["by_kind"],
        },
        "reason": (
            "fixed_point_ship"
            if solved
            else "force_ship_unsolved_banner"
        ),
    }
    ship_md = write_eow_ship_md(ship_doc, eow_dir / "SHIP.md")
    ship_doc["ship_md"] = str(ship_md.resolve())

    # Persist machine-readable ship summary next to SHIP.md
    ship_json = eow_dir / "SHIP.json"
    ship_json.write_text(json.dumps(ship_doc, indent=2) + "\n", encoding="utf-8")
    ship_doc["ship_json"] = str(ship_json.resolve())

    logger.info(
        "EOW SHIP status=%s n_files=%s recipe_present=%s → %s",
        status,
        inventory["n_files"],
        recipe_ref.get("present"),
        eow_dir,
    )
    return ship_doc
