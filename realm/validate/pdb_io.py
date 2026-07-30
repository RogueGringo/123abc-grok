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


def parse_ca_trace(
    pdb_text: str,
    chain: str | None = None,
    *,
    with_resnames: bool = False,
) -> np.ndarray | tuple[np.ndarray, list[str]]:
    """Parse CA coordinates from PDB text. Optional chain filter.

    Only the first MODEL block is used (NMR ensembles would otherwise stack).
    If ``with_resnames`` is True, also return residue names (columns 17–20).
    """
    rows = []
    resnames: list[str] = []
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
        # skip alternate locations other than primary (blank or A)
        alt = line[16].strip() if len(line) > 16 else ""
        if alt not in ("", "A"):
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
        if with_resnames:
            resnames.append(line[17:20].strip() or "UNK")
    if len(rows) < 3:
        raise PdbIOError(f"need ≥3 CA atoms, got {len(rows)}")
    xyz = np.asarray(rows, dtype=float)
    if with_resnames:
        return xyz, resnames
    return xyz


def load_ca(path: Path | str, chain: str | None = None) -> np.ndarray:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_ca_trace(text, chain=chain)


def chain_ca_counts(pdb_text: str) -> dict[str, int]:
    """Count CA atoms per chain in the first MODEL only."""
    counts: dict[str, int] = {}
    saw_model = False
    for line in pdb_text.splitlines():
        if line.startswith("MODEL"):
            if saw_model:
                break
            saw_model = True
            continue
        if line.startswith("ENDMDL") and saw_model:
            break
        if not (line.startswith("ATOM") or line.startswith("HETATM")):
            continue
        if len(line) < 22 or line[12:16].strip() != "CA":
            continue
        alt = line[16].strip() if len(line) > 16 else ""
        if alt not in ("", "A"):
            continue
        ch = line[21].strip() or "_"
        counts[ch] = counts.get(ch, 0) + 1
    return counts


def load_ca_cyclic_band(
    path: Path | str,
    lo: int = 6,
    hi: int = 40,
    chain: str | None = None,
    *,
    with_resnames: bool = False,
) -> tuple[np.ndarray, str] | tuple[np.ndarray, list[str], str]:
    """Load CA trace preferring a chain with length in [lo, hi] (cyclic peptide band).

    When ``with_resnames`` is True returns ``(xyz, resnames, chain_id)``.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")

    def _load(ch: str | None) -> tuple[np.ndarray, list[str] | None, str]:
        label = ch if ch is not None else "ALL"
        if with_resnames:
            xyz, names = parse_ca_trace(text, chain=ch, with_resnames=True)  # type: ignore[misc]
            return xyz, names, label  # type: ignore[return-value]
        xyz = parse_ca_trace(text, chain=ch)
        return xyz, None, label  # type: ignore[return-value]

    if chain is not None:
        xyz, names, label = _load(chain)
        return (xyz, names, label) if with_resnames else (xyz, label)  # type: ignore[return-value]
    counts = chain_ca_counts(text)
    # prefer shortest chain inside band
    band = [(ch, n) for ch, n in counts.items() if lo <= n <= hi]
    if band:
        band.sort(key=lambda x: x[1])
        ch = band[0][0]
        use = None if ch == "_" else ch
        xyz, names, label = _load(use)
        if label == "ALL" and ch == "_":
            label = "_"
        elif use is not None:
            label = use
        return (xyz, names, label) if with_resnames else (xyz, label)  # type: ignore[return-value]
    # fallback: full first-model parse
    xyz, names, label = _load(None)
    return (xyz, names, "ALL") if with_resnames else (xyz, "ALL")  # type: ignore[return-value]
