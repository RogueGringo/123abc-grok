from __future__ import annotations

import json
from pathlib import Path

from realm.validate.harness import score_configuration


def test_zeta_harness_low_R():
    kn_path = Path("evolve_result.json")
    assert kn_path.is_file(), "need champion evolve_result.json"
    kn = json.loads(kn_path.read_text(encoding="utf-8"))["best_knobs"]
    out = score_configuration(
        kind="zeta", knobs=kn, N=13, n_zeros=14, n_sectors=6, rng_seed=0
    )
    assert out["R"] < 0.05
    assert out["occupancy"] >= 0.8
    assert "not_lambda_eq_gamma" in out.get("ontology", "")
