from __future__ import annotations

import json
from pathlib import Path

from realm.validate.harness import score_configuration


def test_zeta_harness_informative_and_legacy():
    kn_path = Path("evolve_result.json")
    assert kn_path.is_file(), "need champion evolve_result.json"
    kn = json.loads(kn_path.read_text(encoding="utf-8"))["best_knobs"]
    out = score_configuration(
        kind="zeta", knobs=kn, N=13, n_zeros=14, n_sectors=6, rng_seed=0
    )
    # informative R = density-return (~0.09 at seal), not the old 0.0045 seating score
    assert out["fitness_mode"] == "informative"
    assert out["R_informative"] == out["R"]
    assert out["R_legacy"] < 0.05  # old seating score still low
    assert out["R"] > out["R_legacy"]  # dens_return > diluted legacy
    assert out["occupancy"] >= 0.8
    assert out["diagnostics"].get("degenerate_seating") == 1.0
    assert "not_lambda_eq_gamma" in out.get("ontology", "")
