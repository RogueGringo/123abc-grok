"""ID universe for known-solutions report: curated ∪ RCSB expand ∪ CPSea2 demo.

Tag priority on collision: probe > holdout > rcsb_expand > cpsea2_demo > cli_override.
Ontology: experimental public natives as known solutions; never λ=γ.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Higher = wins on collision
_TAG_PRIORITY = {
    "curated_probe": 50,
    "curated_holdout": 40,
    "rcsb_expand": 30,
    "cpsea2_demo": 20,
    "cli_override": 10,
}

DEFAULT_RCSB_EXPAND_LIST = Path("data/known_solutions/rcsb_expand.txt")


def _load_curated() -> tuple[list[str], list[str], list[str]]:
    from pdb_batch import DEFAULT_CYCLIC_IDS, HOLDOUT_IDS, PROBE_IDS

    return list(DEFAULT_CYCLIC_IDS), list(PROBE_IDS), list(HOLDOUT_IDS)


def load_id_list_file(path: Path | str) -> list[str]:
    """Parse PDB ids from a text file (# comments, whitespace-separated)."""
    p = Path(path)
    if not p.is_file():
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        for tok in line.replace(",", " ").split():
            pid = tok.strip().upper()
            if len(pid) == 4 and pid[0].isdigit() and pid not in seen:
                seen.add(pid)
                ids.append(pid)
    return ids


def load_cpsea2_demo_ids(*, limit: int = 40, cache_dir: Path | str = Path("data/hf")) -> dict[str, Any]:
    """Optional HF CPSea2 demo IDs. Never loads full multi-GB dump."""
    from realm.validate import hf_io

    if not hf_io.hf_available():
        return {
            "ok": False,
            "ids": [],
            "error": "huggingface_hub_unavailable",
            "status": "hf_unavailable",
        }
    try:
        demo = hf_io.download_cpsea_demo(cache_dir=cache_dir)
        ids = hf_io.list_cpsea_demo_pdb_ids(demo, limit=int(limit))
        return {
            "ok": True,
            "ids": ids,
            "error": None,
            "status": "ok",
            "demo_path": str(demo),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("CPSea2 demo load failed: %s", exc)
        return {
            "ok": False,
            "ids": [],
            "error": str(exc),
            "status": "hf_error",
        }


def resolve_universe(
    *,
    skip_expand: bool = False,
    allow_hf: bool = False,
    rcsb_list: Path | str | None = None,
    extra_ids: list[str] | None = None,
    only_ids: bool = False,
    max_expand: int | None = None,
    cpsea_limit: int = 40,
    cache_dir: Path | str = Path("data/hf"),
) -> dict[str, Any]:
    """Build tagged unique ID universe for known-solutions ranking.

    only_ids: if True, universe is solely extra_ids (cli_override); curated/expand omitted.
    max_expand: cap on rcsb_expand + cpsea2_demo entries after merge (None = no cap).
    """
    _default, probe, holdout = _load_curated()
    entries: dict[str, dict[str, Any]] = {}

    def _add(pid: str, tag: str, source: str) -> None:
        pid = pid.strip().upper()
        if len(pid) != 4 or not pid[0].isdigit():
            return
        pri = _TAG_PRIORITY.get(tag, 0)
        if pid not in entries:
            entries[pid] = {
                "id": pid,
                "tag": tag,
                "source": source,
                "also_in": [],
                "priority": pri,
            }
            return
        cur = entries[pid]
        if pri > int(cur["priority"]):
            cur["also_in"].append(cur["tag"])
            cur["tag"] = tag
            cur["source"] = source
            cur["priority"] = pri
        elif tag != cur["tag"] and tag not in cur["also_in"]:
            cur["also_in"].append(tag)

    rcsb_path = Path(rcsb_list) if rcsb_list else DEFAULT_RCSB_EXPAND_LIST
    rcsb_ids: list[str] = []
    rcsb_status = "skipped"
    cpsea_meta: dict[str, Any] = {
        "ok": False,
        "ids": [],
        "status": "skipped",
        "error": None,
    }

    if only_ids:
        for pid in extra_ids or []:
            _add(str(pid), "cli_override", "cli --only-ids")
        rcsb_status = "skipped_only_ids"
    else:
        for pid in probe:
            _add(pid, "curated_probe", "pdb_batch.PROBE_IDS")
        for pid in holdout:
            _add(pid, "curated_holdout", "pdb_batch.HOLDOUT_IDS")

        if not skip_expand:
            rcsb_ids = load_id_list_file(rcsb_path)
            rcsb_status = (
                "ok"
                if rcsb_ids
                else ("missing_list" if not rcsb_path.is_file() else "empty_list")
            )
            for pid in rcsb_ids:
                _add(pid, "rcsb_expand", str(rcsb_path))

        if allow_hf and not skip_expand:
            cpsea_meta = load_cpsea2_demo_ids(limit=cpsea_limit, cache_dir=cache_dir)
            for pid in cpsea_meta.get("ids") or []:
                _add(str(pid), "cpsea2_demo", "hf:YZY010418/CPSea2")

        for pid in extra_ids or []:
            _add(str(pid), "cli_override", "cli --ids")

    # Stable order: probe, holdout, then expand alpha, then rest
    order_rank = {
        "curated_probe": 0,
        "curated_holdout": 1,
        "rcsb_expand": 2,
        "cpsea2_demo": 3,
        "cli_override": 4,
    }
    universe = sorted(
        entries.values(),
        key=lambda e: (order_rank.get(e["tag"], 9), e["id"]),
    )

    expand_capped = 0
    if max_expand is not None and int(max_expand) >= 0 and not only_ids:
        cap = int(max_expand)
        kept: list[dict[str, Any]] = []
        n_exp = 0
        for e in universe:
            if e["tag"] in ("rcsb_expand", "cpsea2_demo"):
                if n_exp >= cap:
                    expand_capped += 1
                    continue
                n_exp += 1
            kept.append(e)
        universe = kept

    for e in universe:
        e.pop("priority", None)

    by_tag: dict[str, int] = {}
    for e in universe:
        by_tag[e["tag"]] = by_tag.get(e["tag"], 0) + 1

    return {
        "ontology": "known_solutions_id_universe_not_lambda_eq_gamma",
        "n_total": len(universe),
        "by_tag": by_tag,
        "universe": universe,
        "sources": {
            "rcsb_list_path": str(rcsb_path),
            "rcsb_list_status": rcsb_status,
            "rcsb_n_listed": len(rcsb_ids),
            "cpsea2": {
                "status": cpsea_meta.get("status"),
                "ok": cpsea_meta.get("ok"),
                "n_ids": len(cpsea_meta.get("ids") or []),
                "error": cpsea_meta.get("error"),
                "demo_path": cpsea_meta.get("demo_path"),
            },
            "skip_expand": bool(skip_expand),
            "allow_hf": bool(allow_hf),
            "only_ids": bool(only_ids),
            "max_expand": max_expand,
            "expand_dropped_by_cap": int(expand_capped),
        },
        "note": "Tagged public PDB ids for dual-gate known-solution ranking; not ship accept.",
    }
