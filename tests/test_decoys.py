import numpy as np

from realm.validate.decoys import closure_residual, make_ca_decoys, theta_proxy_from_ca


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
