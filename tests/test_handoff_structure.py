from __future__ import annotations

import json
from pathlib import Path

import pytest

from realm.handoff.generate import generate_structure_ensemble


def test_structure_ensemble_from_local_pdb():
    kn_path = Path("evolve_result.json")
    pdb_path = Path("data/pdb/1CSA.pdb")
    if not kn_path.is_file() or not pdb_path.is_file():
        pytest.skip("need evolve_result.json and data/pdb/1CSA.pdb")
    kn = json.loads(kn_path.read_text(encoding="utf-8"))["best_knobs"]
    molds = generate_structure_ensemble(
        "1CSA",
        kn,
        n_zeros=14,
        top_k=4,
        include_coutsias=False,
    )
    assert len(molds) >= 1
    assert all(m.xyz.ndim == 2 and m.xyz.shape[1] >= 3 for m in molds)
    assert all(m.source in ("crit", "coutsias") for m in molds)
