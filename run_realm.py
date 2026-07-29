#!/usr/bin/env python3
"""Entry point: change the realm — full cohesive → zeta → prime-wave pipeline."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure repo root on path when run as script
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

from realm.pipeline import RealmPipeline  # noqa: E402


def main() -> int:
    pipe = RealmPipeline(N=11, d=2, twist_mode="pi_scale", out_dir=ROOT)
    manifest = pipe.run()
    print()
    print(manifest["honest_summary"])
    print(f"\nPlot: {manifest['plot']}")
    print(f"Manifest: {ROOT / 'realm_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
