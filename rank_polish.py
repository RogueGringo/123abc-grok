#!/usr/bin/env python3
"""Geodesic polish of ranking hyperparameters on probe only (AXiomZ G3 / 19.3).

Tunes soft_T and Crit aggregate on PROBE_IDS; evaluates HOLDOUT never in
objective. Does not touch residual / ζ preference claim.

Writes rank_polish_result.json + optional --write-defaults into evolve stage.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdb_batch import HOLDOUT_IDS, PROBE_IDS, rank_one
from realm.validate.report import load_knobs, write_json

logger = logging.getLogger("rank_polish")

# Compact geodesic grid on ranking geometry (G3 / 19.3)
SOFT_T_GRID = [0.04, 0.06, 0.08, 0.10, 0.14, 0.20]
AGG_GRID = ["softmin", "softmin_min", "topk"]


def _mean_enrich(
    ids: list[str],
    knobs: dict,
    *,
    n_decoys: int,
    n_seeds: int,
    k: int,
    sectors: int,
    soft_T: float,
    aggregate: str,
    rng: np.random.Generator,
) -> tuple[float, list]:
    rows = []
    for pid in ids:
        try:
            row = rank_one(
                pid,
                knobs,
                n_decoys,
                k,
                sectors,
                0.45,
                rng,
                n_seeds=n_seeds,
                alpha_proj=1.0,
                soft_T=soft_T,
                aggregate=aggregate,
            )
        except Exception as exc:  # noqa: BLE001
            row = {"pdb": pid, "status": "ERROR", "error": str(exc)}
        rows.append(row)
    ok = [r for r in rows if r.get("status") == "OK"]
    if not ok:
        return 0.0, rows
    return float(np.mean([r["enrichment"] for r in ok])), rows


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Probe-only ranking hyperparam polish")
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("--n-decoys", type=int, default=24)
    p.add_argument("--n-seeds", type=int, default=2)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--json", type=Path, default=Path("rank_polish_result.json"))
    p.add_argument(
        "--write-evolve",
        action="store_true",
        help="write ranking_hparams into evolve_result.json stage",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    knobs = load_knobs(args.knobs)
    history = []
    best = None
    eval_i = 0

    for agg in AGG_GRID:
        for T in SOFT_T_GRID:
            if agg == "topk" and abs(T - 0.08) > 1e-12:
                continue  # topk independent of T — one point
            eval_i += 1
            rng = np.random.default_rng(31 + 17 * eval_i)
            enr, rows = _mean_enrich(
                PROBE_IDS,
                knobs,
                n_decoys=args.n_decoys,
                n_seeds=args.n_seeds,
                k=args.k,
                sectors=args.sectors,
                soft_T=T,
                aggregate=agg,
                rng=rng,
            )
            entry = {
                "aggregate": agg,
                "soft_T": T,
                "probe_enrichment": enr,
                "n_ok": sum(1 for r in rows if r.get("status") == "OK"),
            }
            history.append(entry)
            logger.info("agg=%s T=%.3f probe=%.1f%%", agg, T, 100 * enr)
            if best is None or enr > best["probe_enrichment"] + 1e-12:
                best = {**entry, "probe_rows": rows}

    assert best is not None
    # Held-out (never in objective)
    hold_enr, hold_rows = _mean_enrich(
        HOLDOUT_IDS,
        knobs,
        n_decoys=args.n_decoys,
        n_seeds=max(2, args.n_seeds),
        k=args.k,
        sectors=args.sectors,
        soft_T=best["soft_T"],
        aggregate=best["aggregate"],
        rng=np.random.default_rng(901),
    )
    # Baseline reference (current defaults)
    base_enr, _ = _mean_enrich(
        PROBE_IDS,
        knobs,
        n_decoys=args.n_decoys,
        n_seeds=args.n_seeds,
        k=args.k,
        sectors=args.sectors,
        soft_T=0.08,
        aggregate="softmin",
        rng=np.random.default_rng(902),
    )
    base_hold, _ = _mean_enrich(
        HOLDOUT_IDS,
        knobs,
        n_decoys=args.n_decoys,
        n_seeds=max(2, args.n_seeds),
        k=args.k,
        sectors=args.sectors,
        soft_T=0.08,
        aggregate="softmin",
        rng=np.random.default_rng(903),
    )

    print("\n=== RANK POLISH (probe geodesic; holdout report) ===")
    print(
        f"  best: aggregate={best['aggregate']}  soft_T={best['soft_T']:.3f}  "
        f"probe={best['probe_enrichment']:.1%}  holdout={hold_enr:.1%}"
    )
    print(
        f"  baseline softmin T=0.08: probe={base_enr:.1%}  holdout={base_hold:.1%}"
    )
    print(
        f"  Δprobe={best['probe_enrichment'] - base_enr:+.1%}  "
        f"Δhold={hold_enr - base_hold:+.1%}"
    )

    # Continuity guards (6.2 / 12.3): holdout not worse; probe gain real
    accept = (hold_enr >= base_hold - 0.02) and (
        best["probe_enrichment"] >= base_enr - 0.005
    )
    # Prefer baseline unless clear holdout improvement (avoid probe lottery)
    prefer_baseline = hold_enr < base_hold + 0.01 and best["probe_enrichment"] < base_enr + 0.03
    if prefer_baseline and not (
        hold_enr > base_hold + 0.02 and best["probe_enrichment"] > base_enr + 0.01
    ):
        accept = False
    print(f"  accept_for_defaults={accept}  (holdout/probe continuity guards)")

    chosen = (
        {
            "aggregate": best["aggregate"],
            "soft_T": best["soft_T"],
            "probe_enrichment": best["probe_enrichment"],
            "holdout_enrichment": hold_enr,
        }
        if accept
        else {
            "aggregate": "softmin",
            "soft_T": 0.08,
            "probe_enrichment": base_enr,
            "holdout_enrichment": base_hold,
            "note": "baseline retained — candidate failed full continuity policy",
        }
    )

    payload = {
        "best_candidate": {
            "aggregate": best["aggregate"],
            "soft_T": best["soft_T"],
            "probe_enrichment": best["probe_enrichment"],
            "holdout_enrichment": hold_enr,
        },
        "chosen": chosen,
        "baseline": {
            "aggregate": "softmin",
            "soft_T": 0.08,
            "probe_enrichment": base_enr,
            "holdout_enrichment": base_hold,
        },
        "accept_for_defaults": accept,
        "history": history,
        "holdout_rows": hold_rows,
        "probe_ids": PROBE_IDS,
        "holdout_ids": HOLDOUT_IDS,
        "n_decoys": args.n_decoys,
        "n_seeds": args.n_seeds,
        "note": (
            "Probe-only polish can overfit vs full 40-decoy multi-seed batch. "
            "Always confirm with pdb_batch --n-decoys 40 --n-seeds 3 before commit."
        ),
        "axioms": ["G3", "5.2", "6.2", "12.3", "19.3"],
        "ontology": "rank_hyperparam_polish_not_lambda_eq_gamma",
    }
    write_json(args.json, payload)

    if args.write_evolve and args.knobs.is_file():
        import json

        data = json.loads(args.knobs.read_text(encoding="utf-8"))
        stage = data.setdefault("stage", {})
        stage["ranking_hparams"] = {
            **chosen,
            "accepted": bool(accept),
            "confirmed_full_batch": False,
        }
        data["ranking_hparams"] = stage["ranking_hparams"]
        args.knobs.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(
            f"  wrote ranking_hparams (accepted={accept}) → {args.knobs}",
            file=sys.stderr,
        )

    print(f"wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
