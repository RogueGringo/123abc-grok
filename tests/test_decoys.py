import numpy as np

from realm.validate.decoys import (
    closure_residual,
    make_ca_decoys,
    score_geometry_vs_crit,
    theta_proxy_from_ca,
)


def test_decoys_shape():
    xyz = np.array(
        [[1.0, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0]],
        dtype=float,
    )
    decoys = make_ca_decoys(xyz, n=5, rng=np.random.default_rng(0), noise=0.1)
    assert len(decoys) == 5
    assert decoys[0].shape == xyz.shape


def test_theta_proxy_range():
    xyz = np.array(
        [[1.0, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0]],
        dtype=float,
    )
    th = theta_proxy_from_ca(xyz)
    assert 0 <= th < 2 * np.pi + 1e-9


def test_closure_closed_ring():
    xyz = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
    # open chain first-last
    assert closure_residual(xyz) > 0.5


def test_score_geometry_topk_mean():
    # native-like ring and three templates; top-3 mean uses ensemble
    ring = np.array(
        [[1.0, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0], [0.7, -0.7, 0]],
        dtype=float,
    )
    tpls = [ring + 0.01 * i for i in range(4)]
    sc = score_geometry_vs_crit(ring, tpls, top_k=3)
    assert sc["method"] == "CRIT_KABSCH_TOPK"
    assert sc["top_k"] == 3
    assert sc["mean_dist"] >= sc["min_dist"]
    assert sc["mean_dist"] < 0.2
