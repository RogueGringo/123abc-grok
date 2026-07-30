#!/usr/bin/env python3
"""CLI: geometry off the zeta field (not matching actual zeros)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm import KinematicSpectralRealm, ZetaField


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Induce cyclic geometry from the zeta field; analyze sheaf spectra of that geometry."
    )
    p.add_argument("-N", type=int, default=11, help="cycle size")
    p.add_argument("-d", type=int, default=2, help="stalk dimension")
    p.add_argument("-k", type=int, default=6, help="number of induced sectors / field modes")
    p.add_argument(
        "--twist-source",
        choices=("gap_phases", "modes"),
        default="gap_phases",
        help="how geometry is taken off the zeta field",
    )
    p.add_argument("--no-waypoints", action="store_true")
    p.add_argument("--no-probes", action="store_true")
    p.add_argument("--json", type=Path, default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    field = ZetaField.first(args.k + 1)
    result = KinematicSpectralRealm(
        N=args.N,
        d=args.d,
        n_sectors=args.k,
        twist_source=args.twist_source,
        with_waypoints=not args.no_waypoints,
        with_probes=not args.no_probes,
    ).analyze(field=field)

    print(json.dumps(result.summary(), indent=2))
    if args.json:
        args.json.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        print(f"wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
