"""Seed factories + ZetaField.from_gammas."""
from __future__ import annotations

import numpy as np

from realm.validate.seeds import make_seed
from realm.zeta_field import ZETA_ZEROS_IMAG, ZetaField


def test_from_gammas_gaps():
    g = np.array([10.0, 12.0, 15.0, 20.0])
    f = ZetaField.from_gammas(g)
    assert np.allclose(f.gammas, g)
    assert np.allclose(f.gaps, np.diff(g))


def test_zeta_matches_table():
    g = make_seed("zeta", 6, np.random.default_rng(0))
    assert np.allclose(g, ZETA_ZEROS_IMAG[:6])


def test_scramble_preserves_gap_multiset():
    z = make_seed("zeta", 10, np.random.default_rng(0))
    s = make_seed("scramble", 10, np.random.default_rng(1))
    assert np.allclose(sorted(np.diff(z)), sorted(np.diff(s)))


def test_gue_poisson_arith_length_and_positive():
    for kind in ("gue", "goe", "poisson", "arith"):
        g = make_seed(kind, 14, np.random.default_rng(2))
        assert g.shape == (14,)
        assert np.all(np.diff(g) > 0)
        assert np.all(g > 0)


def test_forge_accepts_gammas():
    from realm.lock_key import Keymaker

    g = make_seed("poisson", 8, np.random.default_rng(3))
    der = Keymaker(N=11, n_zeros=8, n_sectors=4).forge(gammas=g)
    assert der.field.gammas.size == 8
    assert np.allclose(der.field.gammas, np.sort(g))
