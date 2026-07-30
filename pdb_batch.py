#!/usr/bin/env python3
"""Batch cyclic PDB native-vs-decoy ranking on the sealed geometric path.

Stays structure-only. Does not ingest HF language benchmarks (~400 protein
repos). Curated cyclic IDs + RCSB; N matched to CA count.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.lock_key import Keymaker
from realm.validate.decoys import make_ca_decoys, score_geometry_vs_crit
from realm.validate.pdb_io import PdbIOError, fetch_pdb, load_ca_cyclic_band
from realm.validate.report import load_knobs, write_json

logger = logging.getLogger("pdb_batch")

# Curated cyclic / short-peptide public structures (RCSB geometry only).
# Not scraped from ~400 HF protein-language repos.
# Curated IDs known to expose a CA chain in the cyclic band (RCSB).
DEFAULT_CYCLIC_IDS = [
    "1CSA",
    "1IKF",
    "2X2C",
    "4M6E",
    "3WNE",
    "4K8Y",
    "1JBL",
    "5EOC",
    "3AVB",
    "5LSO",
    "1TET",
]

# Default joint-polish train probe (never sole success metric)
PROBE_IDS = ["1CSA", "2X2C", "4M6E", "3WNE"]
HOLDOUT_IDS = ["1IKF", "1JBL", "4K8Y", "5EOC", "3AVB", "5LSO"]


def rank_one(
    pdb_id: str,
    knobs: dict,
    n_decoys: int,
    n_zeros: int,
    n_sectors: int,
    noise: float,
    rng: np.random.Generator,
) -> dict:
    path = fetch_pdb(pdb_id)
    xyz, chain_used = load_ca_cyclic_band(path, lo=6, hi=40)
    n_ca = int(xyz.shape[0])
    if n_ca < 6 or n_ca > 40:
        return {
            "pdb": pdb_id,
            "status": "SKIP_LENGTH",
            "n_ca": n_ca,
            "chain": chain_used,
            "note": "no chain in cyclic peptide length band [6,40]",
        }

    # Match Keymaker N to backbone length (geometry scaffold size)
    N = max(n_ca, 7)
    der = Keymaker(N=N, n_zeros=n_zeros, n_sectors=n_sectors).forge(**knobs)
    templates = []
    for s in der.sectors:
        pts = getattr(s, "positions", None)
        if pts is not None:
            arr = np.asarray(pts, dtype=float)
            if arr.ndim == 2 and arr.shape[1] >= 3:
                templates.append(arr[:, :3])

    # Pure Crit-Kabsch (dual mold blend regressed full-batch enrichment)
    native = score_geometry_vs_crit(xyz, templates)
    native["label"] = "native"
    n_soft = max(n_decoys // 2, 1)
    n_hard = n_decoys - n_soft
    decoys = make_ca_decoys(xyz, n_soft, rng, noise=noise)
    decoys += make_ca_decoys(xyz, n_hard, rng, noise=noise * 1.8)
    rows = [native]
    for i, d in enumerate(decoys):
        sc = score_geometry_vs_crit(d, templates)
        sc["label"] = f"decoy_{i}"
        rows.append(sc)

    ranked = sorted(rows, key=lambda r: r["mean_dist"])
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    native_rank = next(r["rank"] for r in ranked if r["label"] == "native")
    worse = sum(1 for r in ranked if r["label"] != "native" and r["mean_dist"] > native["mean_dist"])
    enrichment = worse / max(n_decoys, 1)
    top20 = native_rank <= max(1, int(0.2 * len(ranked)))

    return {
        "pdb": pdb_id,
        "status": "OK",
        "n_ca": n_ca,
        "chain": chain_used,
        "N_scaffold": N,
        "native_dist": native["mean_dist"],
        "native_rank": native_rank,
        "n_total": len(ranked),
        "enrichment": enrichment,
        "top20": top20,
        "method": native.get("method"),
        "n_templates": len(templates),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Batch cyclic PDB mold ranking")
    p.add_argument("--ids", type=str, default=",".join(DEFAULT_CYCLIC_IDS))
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("--n-decoys", type=int, default=32)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--noise", type=float, default=0.45)
    p.add_argument("--null-json", type=Path, default=Path("null_battery_result.json"))
    p.add_argument("--force", action="store_true")
    p.add_argument("--json", type=Path, default=Path("pdb_batch_result.json"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if not args.force and args.null_json.is_file():
        null = json.loads(args.null_json.read_text(encoding="utf-8"))
        if not null.get("passed", False):
            print("null battery gate FAIL — pass --force to run", file=sys.stderr)
            return 2

    knobs = load_knobs(args.knobs)
    ids = [x.strip().upper() for x in args.ids.split(",") if x.strip()]
    rng = np.random.default_rng(11)
    rows = []
    for pid in ids:
        try:
            row = rank_one(
                pid, knobs, args.n_decoys, args.k, args.sectors, args.noise, rng
            )
        except PdbIOError as exc:
            row = {"pdb": pid, "status": "IO_FAIL", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            row = {"pdb": pid, "status": "ERROR", "error": str(exc)}
        rows.append(row)
        logger.info("%s", row)

    ok = [r for r in rows if r.get("status") == "OK"]
    mean_enr = float(np.mean([r["enrichment"] for r in ok])) if ok else 0.0
    n_top20 = sum(1 for r in ok if r.get("top20"))
    print("\n=== PDB BATCH (structure path) ===")
    for r in rows:
        if r.get("status") == "OK":
            print(
                f"  {r['pdb']:5s}  CA={r['n_ca']:2d}  rank={r['native_rank']:2d}/{r['n_total']}  "
                f"enrich={r['enrichment']:.0%}  top20={r['top20']}"
            )
        else:
            print(f"  {r['pdb']:5s}  {r['status']}  {r.get('error') or r.get('note', '')}")
    print(f"\nOK={len(ok)}/{len(rows)}  mean_enrichment={mean_enr:.1%}  top20_count={n_top20}")

    payload = {
        "rows": rows,
        "summary": {
            "n_ok": len(ok),
            "n_total_ids": len(rows),
            "mean_enrichment": mean_enr,
            "top20_count": n_top20,
        },
        "knobs": knobs,
        "ontology": "structure_path_not_protein_lm_bench",
        "note": (
            "Curated cyclic PDB IDs only. HF language datasets (~400 repos) "
            "are out of band; use CPSea/RCSB for coords."
        ),
    }
    write_json(args.json, payload)
    print(f"wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
