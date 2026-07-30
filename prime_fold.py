#!/usr/bin/env python3
"""CLI: Coutsias → MaxOp sheaf L spectral action → 3D embed (PrimeFold).

Ontology: scores geometry's connection Laplacian spectrum S_L(s)=Σ λ^{-s}.
Never λ=γ. ζ is substrate seed only in Crit path (not required here).
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

from realm.ontology import ontology_note
from realm.prime_fold import PrimeFoldingEngine
from realm.validate.report import write_json


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Prime fold: Coutsias + MaxOp spectral action")
    p.add_argument("-N", type=int, default=11, help="cycle length (CA atoms)")
    p.add_argument("-s", type=float, default=2.0, help="spectral zeta order")
    p.add_argument("--starts", type=int, default=24, help="Coutsias multi-starts")
    p.add_argument("--max-roots", type=int, default=6)
    p.add_argument("--no-de", action="store_true", help="skip DE global seed")
    p.add_argument("--no-maxop", action="store_true", help="force numpy Laplacian")
    p.add_argument("--json", type=Path, default=Path("prime_fold_result.json"))
    p.add_argument("--xyz", type=Path, default=None, help="optional write N×3 coords npy")
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("\n=== PRIME FOLD (Coutsias → MaxOp L → spectral action) ===")
    print(f"  {ontology_note()}")
    print(f"  N={args.N}  s={args.s}  starts={args.starts}  maxop={not args.no_maxop}")

    eng = PrimeFoldingEngine(
        N=args.N,
        s=args.s,
        prefer_maxop=not args.no_maxop,
        n_starts=args.starts,
        use_de=not args.no_de,
    )
    result = eng.execute_folding(max_roots=args.max_roots)
    sc = result.score
    print(
        f"\n  GROUND STATE  total={sc['total']:.4f}  S_L={sc['spectral_action']:.4f}  "
        f"res={sc['residual']:.4f}  gap={sc['spectral_gap']:.4f}  "
        f"twist={sc['twist_so2']:+.3f}  backend={sc.get('backend')}"
    )
    print(f"  candidates={len(result.candidates)}  coords={None if result.coordinates is None else result.coordinates.shape}")

    payload = result.to_dict()
    write_json(args.json, payload)
    print(f"  wrote {args.json}")

    if args.xyz is not None and result.coordinates is not None:
        np.save(args.xyz, np.asarray(result.coordinates, float))
        print(f"  wrote {args.xyz}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
