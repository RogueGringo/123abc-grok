from __future__ import annotations

import json
from pathlib import Path

import pytest

from realm.handoff.generate import generate_structure_ensemble


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_fixture(*parts: str) -> Path | None:
    """Prefer repo-root relative to this test file; fall back to CWD."""
    for base in (_repo_root(), Path.cwd()):
        p = base.joinpath(*parts)
        if p.is_file():
            return p
    return None


def test_structure_ensemble_from_local_pdb():
    kn_path = _resolve_fixture("evolve_result.json")
    pdb_path = _resolve_fixture("data", "pdb", "1CSA.pdb")
    if kn_path is None or pdb_path is None:
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
    assert len(molds) <= 4
    scores = [m.rank_score for m in molds]
    assert scores == sorted(scores)
    assert all(m.source == "crit" for m in molds)
    assert all(m.method == "structure_self_fit_dense" for m in molds)
    # 1CSA cyclic band is N=11; templates are (N, 3)
    assert all(m.xyz.ndim == 2 and m.xyz.shape == (m.N, 3) for m in molds)
    assert all(m.N == 11 for m in molds)
    assert all(m.xyz.shape[1] == 3 for m in molds)
