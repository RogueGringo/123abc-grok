#!/usr/bin/env python3
"""Phase 3: single cyclic PDB native vs decoy mold ranking."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.lock_key import Keymaker
from realm.projection import build_moduli_landscape
from realm.validate.decoys import (
    make_ca_decoys,
    score_geometry_on_mold,
    score_geometry_vs_crit,
)
from realm.validate.pdb_io import PdbIOError, fetch_pdb, load_ca
from realm.validate.report import load_knobs, write_json

logger = logging.getLogger("pdb_decoy")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Native vs decoy mold ranking")
    p.add_argument("--pdb", type=str, default="1CSA", help="PDB id")
    p.add_argument("--pdb-file", type=Path, default=None, help="Local PDB path (offline)")
    p.add_argument("--chain", type=str, default=None)
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("--n-decoys", type=int, default=32)
    p.add_argument("-N", type=int, default=13)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--force", action="store_true", help="Skip null gate check")
    p.add_argument("--null-json", type=Path, default=Path("null_battery_result.json"))
    p.add_argument("--json", type=Path, default=Path("pdb_decoy_result.json"))
    p.add_argument("--plot", type=Path, default=Path("pdb_decoy.png"))
    p.add_argument("--allow-hf-fallback", action="store_true")
    p.add_argument(
        "--method",
        choices=("crit_kabsch", "theta_proxy", "both"),
        default="crit_kabsch",
        help="Ranking score: Crit geometry RMSD (default) or theta proxy",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if not args.force and args.null_json.is_file():
        null = json.loads(args.null_json.read_text(encoding="utf-8"))
        if not null.get("passed", False):
            print("null battery gate FAIL — pass --force to run anyway", file=sys.stderr)
            return 2

    knobs = load_knobs(args.knobs)

    try:
        if args.pdb_file is not None:
            path = args.pdb_file
        else:
            try:
                path = fetch_pdb(args.pdb)
            except PdbIOError as exc:
                if args.allow_hf_fallback:
                    from realm.validate import hf_io

                    logger.warning("RCSB failed (%s); trying HF demo ids only", exc)
                    demo = hf_io.download_cpsea_demo()
                    ids = hf_io.list_cpsea_demo_pdb_ids(demo)
                    logger.info("HF demo ids: %s", ids[:10])
                    raise PdbIOError(
                        f"RCSB failed; HF listed ids {ids[:5]} — re-run with --pdb <id>"
                    ) from exc
                raise
        xyz = load_ca(path, chain=args.chain)
    except PdbIOError as exc:
        print(f"I/O fail: {exc}", file=sys.stderr)
        return 3

    # ζ landscape + Crit sector templates from champion knobs
    der = Keymaker(N=args.N, n_zeros=args.k, n_sectors=args.sectors).forge(**knobs)
    land = build_moduli_landscape(
        field=der.field, action=der.action, critical=der.critical
    )
    basin = float(np.pi / max(len(land.valleys), 1))
    templates = []
    for s in der.sectors:
        pts = getattr(s, "positions", None)
        if pts is not None:
            arr = np.asarray(pts, dtype=float)
            if arr.ndim == 2 and arr.shape[1] >= 3:
                templates.append(arr[:, :3])

    def _score(cloud: np.ndarray) -> dict:
        if args.method == "theta_proxy":
            return score_geometry_on_mold(cloud, land, basin=basin)
        if args.method == "both":
            a = score_geometry_vs_crit(cloud, templates)
            b = score_geometry_on_mold(cloud, land, basin=basin)
            # lower is better: blend normalized ranks later — use kabsch primary
            a["theta_proxy_dist"] = b["mean_dist"]
            return a
        return score_geometry_vs_crit(cloud, templates)

    native = _score(xyz)
    native["label"] = "native"
    native["closure"] = float(np.linalg.norm(xyz[0] - xyz[-1]))

    rng = np.random.default_rng(7)
    decoy_xyz = make_ca_decoys(xyz, args.n_decoys, rng, noise=0.45)
    decoy_scores = []
    for i, d in enumerate(decoy_xyz):
        sc = _score(d)
        sc["label"] = f"decoy_{i}"
        decoy_scores.append(sc)

    all_rows = [native] + decoy_scores
    ranked = sorted(all_rows, key=lambda r: r["mean_dist"])
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i

    native_rank = next(r["rank"] for r in ranked if r["label"] == "native")
    n_tot = len(ranked)
    worse = sum(1 for r in decoy_scores if r["mean_dist"] > native["mean_dist"])
    enrichment = worse / max(len(decoy_scores), 1)
    top20 = native_rank <= max(1, int(0.2 * n_tot))

    print("\n=== PDB DECOY RANK ===")
    print(f"  structure: {path}")
    print(f"  CA atoms: {xyz.shape[0]}")
    print(f"  native dist={native['mean_dist']:.4f}  rank={native_rank}/{n_tot}")
    print(f"  enrichment (frac decoys worse)={enrichment:.2%}")
    print(f"  top-20%? {top20}  method={native['method']}")

    payload = {
        "pdb": args.pdb if args.pdb_file is None else str(args.pdb_file),
        "path": str(path),
        "n_ca": int(xyz.shape[0]),
        "native": native,
        "native_rank": native_rank,
        "n_total": n_tot,
        "enrichment": enrichment,
        "top20": top20,
        "ranked": ranked,
        "knobs": knobs,
        "method": args.method,
        "ontology": "mold_ranking_not_lambda_eq_gamma",
        "note": "crit_kabsch = min shape-RMSD to Crit sector embeddings; theta_proxy = FALLBACK",
    }
    write_json(args.json, payload)

    # plot
    fig, ax = plt.subplots(figsize=(8, 4))
    dists = [r["mean_dist"] for r in ranked]
    colors = ["#00ff88" if r["label"] == "native" else "#4488ff" for r in ranked]
    ax.bar(range(1, n_tot + 1), dists, color=colors)
    ax.set_xlabel("rank")
    ax.set_ylabel("mold distance")
    ax.set_title(f"native rank {native_rank}/{n_tot}  enrich={enrichment:.0%}")
    fig.tight_layout()
    fig.savefig(args.plot, dpi=200, facecolor="#0a0a12")
    plt.close(fig)

    print(f"wrote {args.json}", file=sys.stderr)
    print(f"wrote {args.plot}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
