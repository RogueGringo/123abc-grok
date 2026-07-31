import numpy as np

from realm.validate.decoys import (
    closure_residual,
    make_ca_decoys,
    make_ca_decoy_reverse,
    make_ca_decoy_roll,
    make_decoy_bank,
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


def test_decoy_bank_modes():
    xyz = np.array(
        [[1.0, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0], [0.5, 0.5, 0.2], [-0.5, 0.5, -0.1]],
        dtype=float,
    )
    rng = np.random.default_rng(1)
    for mode in ("soft", "mixed", "hard"):
        bank = make_decoy_bank(xyz, 8, rng, mode=mode, noise=0.3)
        assert len(bank) == 8
        assert all(d.shape == xyz.shape for d in bank)
    rev = make_ca_decoy_reverse(xyz)
    assert rev.shape == xyz.shape
    rolled = make_ca_decoy_roll(xyz, 2)
    assert rolled.shape == xyz.shape
    # soft mode remains default production shape
    soft = make_decoy_bank(xyz, 4, np.random.default_rng(0), mode="soft")
    assert len(soft) == 4


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


def test_score_geometry_softmin_and_topk():
    ring = np.array(
        [[1.0, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0], [0.7, -0.7, 0]],
        dtype=float,
    )
    tpls = [ring + 0.01 * i for i in range(4)]
    soft = score_geometry_vs_crit(ring, tpls, aggregate="softmin")
    topk = score_geometry_vs_crit(ring, tpls, top_k=3, aggregate="topk")
    assert soft["method"] == "CRIT_KABSCH_SOFTMIN"
    assert topk["method"] == "CRIT_KABSCH_TOPK"
    assert soft["mean_dist"] + 1e-12 >= soft["min_dist"]
    assert topk["mean_dist"] + 1e-12 >= topk["min_dist"]
    assert soft["mean_dist"] < 0.2


def test_score_geometry_persist_weights():
    ring = np.array(
        [[1.0, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0], [0.7, -0.7, 0]],
        dtype=float,
    )
    tpls = [ring + 0.05 * i for i in range(4)]
    # heavy weight on nearest (i=0) vs far templates
    w = np.array([3.0, 0.2, 0.2, 0.2])
    plain = score_geometry_vs_crit(ring, tpls, aggregate="softmin")
    weighted = score_geometry_vs_crit(
        ring, tpls, aggregate="softmin_persist", sector_weights=w
    )
    assert weighted["method"] == "CRIT_KABSCH_SOFTMIN_PERSIST"
    assert weighted["weighted"] is True
    # weighting nearest lower-distance template should not increase softmin
    assert weighted["mean_dist"] <= plain["mean_dist"] + 1e-9
