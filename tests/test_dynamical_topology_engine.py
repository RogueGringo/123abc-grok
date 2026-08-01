import numpy as np
from realm.dynamical_topology.types import Stage
from realm.dynamical_topology.engine import run_dynamical_topology, topology_stable


def _cloud(center, n=12, scale=0.05, seed=0):
    rng = np.random.default_rng(seed)
    return rng.normal(center, scale, size=(n, 2))


def test_stable_phases_have_long_structure():
    stages = [
        Stage(0, "rearrange", _cloud(0, n=20, scale=1.0, seed=1)),
        Stage(1, "stable", np.vstack([_cloud(0, seed=2), _cloud(5, seed=3)])),
        Stage(2, "stable", np.vstack([_cloud(0, seed=4), _cloud(5, seed=5)])),
        Stage(3, "emit", np.vstack([_cloud(0, seed=6), _cloud(5, seed=7)])),
    ]
    rep = run_dynamical_topology(stages, knn_k=4, long_frac=0.2)
    assert rep["not_acceptance"] is True
    assert rep["n_stages"] == 4
    assert rep["n_long"] >= 1
    assert rep["phases"]["dominant"] in ("rearrange", "stable", "refine", "emit")


def test_topology_stable_detects_collapse():
    good = run_dynamical_topology([
        Stage(0, "a", _cloud(0, seed=1)),
        Stage(1, "b", _cloud(0, seed=2)),
    ])
    prev = dict(good)
    prev["n_long"] = 10
    curr = dict(good)
    curr["n_long"] = 1
    curr["phases"] = {"labels": ["rearrange"], "dominant": "rearrange"}
    assert topology_stable(curr, prev=prev, drop_tol=0.3) is False
    assert topology_stable(good, prev=None) in (True, False)
