#!/usr/bin/env python3
"""Phase 2: strategy B — vary n_sectors for dens_return under seal constraints."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.validate.harness import score_configuration
from realm.validate.report import load_knobs, write_json

logger = logging.getLogger("sec_scale")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Sector scale dens_return table")
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("--sectors", type=str, default="6,8,10,12")
    p.add_argument("-N", type=int, default=13)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--json", type=Path, default=Path("sec_scale_result.json"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    knobs = load_knobs(args.knobs)
    secs = [int(x.strip()) for x in args.sectors.split(",") if x.strip()]

    rows = []
    for sec in secs:
        out = score_configuration(
            kind="zeta",
            knobs=knobs,
            N=args.N,
            n_zeros=args.k,
            n_sectors=sec,
            rng_seed=0,
        )
        need = max(3, sec // 2)
        capacity_ok = out["n_valleys"] >= need and out["n_keys"] >= need
        sealed = (
            capacity_ok
            and out["occupancy"] >= 0.80
            and float(out.get("diagnostics", {}).get("pin_align", 1.0) or 0.0) < 0.05
        )
        status = "OK" if sealed else ("FAIL_CAPACITY" if not capacity_ok else "UNSEALED")
        dens = float((out.get("diagnostics") or {}).get("density_return_l1", 1.0))
        row = {
            "n_sectors": sec,
            "status": status,
            "R": out["R"],
            "F": out["F"],
            "occupancy": out["occupancy"],
            "n_keys": out["n_keys"],
            "n_valleys": out["n_valleys"],
            "dens_return": dens,
            "diagnostics": out.get("diagnostics"),
        }
        rows.append(row)
        logger.info(
            "sec=%d %s R=%.4f dens=%.4f occ=%.0f%% keys=%d val=%d",
            sec,
            status,
            out["R"],
            dens,
            100 * out["occupancy"],
            out["n_keys"],
            out["n_valleys"],
        )

    sealed_rows = [r for r in rows if r["status"] == "OK"]
    best = None
    if sealed_rows:
        best = min(sealed_rows, key=lambda r: r["dens_return"])

    print("\n=== SEC SCALE ===")
    for r in rows:
        print(
            f"  sec={r['n_sectors']:2d}  {r['status']:14s}  R={r['R']:.4f}  "
            f"dens={r['dens_return']:.4f}  occ={r['occupancy']:.0%}"
        )
    if best:
        print(f"\nBest sealed dens_return: sec={best['n_sectors']} dens={best['dens_return']:.4f}")

    payload = {
        "rows": rows,
        "best_sealed": best,
        "knobs": knobs,
        "config": {"N": args.N, "n_zeros": args.k},
        "ontology": "strategy_B_sec_approx_k",
    }
    write_json(args.json, payload)
    print(f"wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
