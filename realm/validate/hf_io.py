"""Hugging Face Hub data plane — demo/metadata only, not pLM critical path."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CPSEA_REPO = "YZY010418/CPSea2"


def hf_available() -> bool:
    try:
        import huggingface_hub  # noqa: F401

        return True
    except ImportError:
        return False


def download_cpsea_demo(cache_dir: Path | str = Path("data/hf")) -> Path:
    """Download a small CPSea demo metadata file; never the full multi-GB dump."""
    if not hf_available():
        raise RuntimeError(
            "huggingface_hub not installed; pip install huggingface_hub or use RCSB only"
        )
    from huggingface_hub import hf_hub_download, list_repo_files

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    files = list_repo_files(CPSEA_REPO, repo_type="dataset")
    # Prefer tiny demo metadata
    candidates = [
        f
        for f in files
        if "demo" in f.lower() and ("meta" in f.lower() or f.endswith(".tsv") or f.endswith(".csv"))
    ]
    if not candidates:
        candidates = [f for f in files if "PDB" in f and "meta" in f.lower()][:5]
    if not candidates:
        raise RuntimeError(f"no demo/metadata files found in {CPSEA_REPO}")
    # shortest path often the smallest demo
    candidates.sort(key=len)
    fname = candidates[0]
    logger.info("HF download %s / %s", CPSEA_REPO, fname)
    path = hf_hub_download(
        repo_id=CPSEA_REPO,
        filename=fname,
        repo_type="dataset",
        local_dir=str(cache),
    )
    return Path(path)


def list_cpsea_demo_pdb_ids(demo_path: Path | str, limit: int = 20) -> list[str]:
    """Best-effort parse of PDB-like ids from demo TSV/CSV text."""
    text = Path(demo_path).read_text(encoding="utf-8", errors="replace")
    ids: list[str] = []
    import re

    for m in re.finditer(r"\b([0-9][A-Za-z0-9]{3})\b", text):
        pid = m.group(1).upper()
        if pid not in ids:
            ids.append(pid)
        if len(ids) >= limit:
            break
    return ids
