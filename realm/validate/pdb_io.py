"""RCSB fetch + CA backbone parse for cyclic peptide deep dive."""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class PdbIOError(RuntimeError):
    pass


def fetch_pdb(pdb_id: str, cache_dir: Path | str = Path("data/pdb")) -> Path:
    """Download PDB file to cache; return path."""
    pid = pdb_id.strip().upper()
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / f"{pid}.pdb"
    if dest.is_file() and dest.stat().st_size > 100:
        return dest
    url = f"https://files.rcsb.org/download/{pid}.pdb"
    try:
        logger.info("Fetching %s", url)
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        raise PdbIOError(f"RCSB HTTP {exc.code} for {pid}") from exc
    except Exception as exc:  # noqa: BLE001
        raise PdbIOError(f"RCSB fetch failed for {pid}: {exc}") from exc
    dest.write_bytes(data)
    return dest


def parse_ca_trace(pdb_text: str, chain: str | None = None) -> np.ndarray:
    """Parse CA coordinates from PDB text. Optional chain filter.

    Only the first MODEL block is used (NMR ensembles would otherwise stack).
    """
    rows = []
    in_model = False
    saw_model = False
    for line in pdb_text.splitlines():
        if line.startswith("MODEL"):
            if saw_model:
                break  # finished first model
            saw_model = True
            in_model = True
            continue
        if line.startswith("ENDMDL"):
            if in_model or saw_model:
                break
            continue
        if not (line.startswith("ATOM") or line.startswith("HETATM")):
            continue
        if len(line) < 54:
            continue
        name = line[12:16].strip()
        if name != "CA":
            continue
        ch = line[21].strip() if len(line) > 21 else ""
        if chain is not None and ch != chain:
            continue
        try:
            x = float(line[30:38])
            y = float(line[38:46])
            z = float(line[46:54])
        except ValueError:
            continue
        rows.append([x, y, z])
    if len(rows) < 3:
        raise PdbIOError(f"need ≥3 CA atoms, got {len(rows)}")
    return np.asarray(rows, dtype=float)


def load_ca(path: Path | str, chain: str | None = None) -> np.ndarray:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_ca_trace(text, chain=chain)
