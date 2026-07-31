#!/usr/bin/env python3
"""Known-solutions report: public natives → science ledger + partner annex.

Dual-gate rank_one on curated ∪ RCSB expand ∪ optional CPSea2 demo;
Kabsch structure subset (capped). Report-only: enrichment never gates ship.
Pin soft_T(n=12)=0.036 locked. Never λ=γ.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.validate.known_solutions import run_known_solutions

logger = logging.getLogger("known_solutions")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Known-solutions dual-gate report (internal ledger + partner annex). "
            "Report-only; not ACCEPTANCE/SHIP."
        )
    )
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("--out-dir", type=Path, default=Path("out/known_solutions"))
    p.add_argument("--n-decoys", type=int, default=24)
    p.add_argument("--n-seeds", type=int, default=3)
    p.add_argument("-k", "--n-zeros", type=int, default=14)
    p.add_argument("--noise", type=float, default=0.45)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument(
        "--skip-expand",
        action="store_true",
        help="curated probe/holdout only",
    )
    p.add_argument(
        "--allow-hf",
        action="store_true",
        help="include CPSea2 demo IDs when huggingface_hub available",
    )
    p.add_argument(
        "--rcsb-list",
        type=Path,
        default=None,
        help="override RCSB expand list path",
    )
    p.add_argument(
        "--ids",
        type=str,
        default="",
        help="comma-separated extra PDB ids (cli_override tag)",
    )
    p.add_argument(
        "--only-ids",
        action="store_true",
        help="rank only --ids (omit curated + expand); requires --ids",
    )
    p.add_argument(
        "--max-expand",
        type=int,
        default=None,
        help="cap rcsb_expand+cpsea2 entries after curated (None = no cap)",
    )
    p.add_argument(
        "--full-seeds",
        action="store_true",
        help="apply --n-seeds to expand IDs too (default: expand uses 1 seed)",
    )
    p.add_argument(
        "--kabsch-set",
        type=str,
        default="curated",
        choices=("curated", "probe", "holdout", "all", "none"),
        help="which IDs get structure Kabsch (capped)",
    )
    p.add_argument("--kabsch-max", type=int, default=12)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve universe + pin only; no ranking",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if not args.knobs.is_file() and not args.dry_run:
        logger.error("knobs not found: %s", args.knobs)
        return 2

    extra = [x.strip() for x in args.ids.split(",") if x.strip()] if args.ids else []
    if args.only_ids and not extra:
        logger.error("--only-ids requires --ids")
        return 2

    report = run_known_solutions(
        knobs_path=args.knobs,
        out_dir=args.out_dir,
        n_decoys=args.n_decoys,
        n_seeds=args.n_seeds,
        n_zeros=args.n_zeros,
        noise=args.noise,
        skip_expand=args.skip_expand,
        allow_hf=args.allow_hf,
        rcsb_list=args.rcsb_list,
        extra_ids=extra or None,
        only_ids=args.only_ids,
        max_expand=args.max_expand,
        full_seeds=args.full_seeds,
        kabsch_set=args.kabsch_set,
        kabsch_max=args.kabsch_max,
        dry_run=args.dry_run,
        seed=args.seed,
    )

    pin = report.get("pin") or {}
    status = report.get("status")
    out = report.get("out_dir") or args.out_dir

    if not pin.get("ok"):
        logger.error("dual-gate pin FAIL: %s", pin)
        print(f"PIN_FAIL soft_T={pin.get('soft_T')} expected=0.036", file=sys.stderr)
        return 2

    if status == "EMPTY_UNIVERSE":
        logger.error("empty ID universe")
        return 3

    agg = report.get("aggregates") or {}
    print(
        f"status={status} pin_ok={pin.get('ok')} "
        f"soft_T={pin.get('soft_T')} "
        f"n_ok={agg.get('n_ok', 0)} n_attempted={agg.get('n_attempted', 0)} "
        f"out={out}"
    )
    if status == "DRY_RUN":
        u = report.get("id_universe") or {}
        print(f"universe n={u.get('n_total')} by_tag={u.get('by_tag')}")
        return 0

    if int(agg.get("n_ok") or 0) < 1 and not args.dry_run:
        # total ranking collapse (all SKIP/ERROR) — I/O style fail
        if int(agg.get("n_attempted") or 0) > 0:
            logger.error("zero successful rank rows")
            return 3
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
