from __future__ import annotations

import json
from pathlib import Path

from realm.validate.harness import score_configuration


def test_zeta_harness_published_seal_residual():
    """Main residual is the seating/legacy score (published F_zeta ~ 0.00453)."""
    kn_path = Path("evolve_result.json")
    assert kn_path.is_file(), "need champion evolve_result.json"
    kn = json.loads(kn_path.read_text(encoding="utf-8"))["best_knobs"]
    out = score_configuration(
        kind="zeta", knobs=kn, N=13, n_zeros=14, n_sectors=6, rng_seed=0
    )
    R = float(out.get("R", out.get("F", 1e9)))
    assert R < 0.05, f"expected low published residual, got {R}"
    # Occupancy / diagnostics present
    assert "occupancy" in out or "key_occupancy" in out or any("occup" in k for k in out)
