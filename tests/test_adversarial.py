"""Adversarial spectra: span-matched so scale can never be the discriminator."""

from __future__ import annotations

import numpy as np
import pytest

from realm.validate.adversarial import (
    DETERMINISTIC,
    KINDS,
    make_adversarial_seed,
)
from realm.validate.zeros import real_zeros

K = 14
BASE = real_zeros(K)


@pytest.mark.parametrize("kind", KINDS)
def test_shape_increasing_and_positive(kind):
    g = make_adversarial_seed(kind, K, np.random.default_rng(0), base=BASE)
    assert g.shape == (K,)
    assert np.all(g > 0)
    assert np.all(np.diff(g) > 0)


@pytest.mark.parametrize("kind", KINDS)
def test_span_matched_to_base(kind):
    """Every arm shares γ_0 and total span with the ζ window."""
    g = make_adversarial_seed(kind, K, np.random.default_rng(1), base=BASE)
    assert g[0] == pytest.approx(BASE[0])
    assert (g[-1] - g[0]) == pytest.approx(BASE[-1] - BASE[0], rel=1e-9)


@pytest.mark.parametrize("kind", sorted(DETERMINISTIC))
def test_deterministic_kinds_ignore_rng(kind):
    a = make_adversarial_seed(kind, K, np.random.default_rng(0), base=BASE)
    b = make_adversarial_seed(kind, K, np.random.default_rng(999), base=BASE)
    assert np.allclose(a, b), f"{kind} should not depend on the RNG stream"


def test_stochastic_kinds_do_vary():
    for kind in ("goe", "poisson", "sorted_uniform", "scramble"):
        a = make_adversarial_seed(kind, K, np.random.default_rng(0), base=BASE)
        b = make_adversarial_seed(kind, K, np.random.default_rng(1), base=BASE)
        assert not np.allclose(a, b), f"{kind} should vary across draws"


def test_arith_is_constant_gap():
    """The key falsifiability probe: zero information content."""
    g = make_adversarial_seed("arith", K, np.random.default_rng(0), base=BASE)
    d = np.diff(g)
    assert np.allclose(d, d[0])


def test_zeta_arm_is_the_real_window():
    g = make_adversarial_seed("zeta", K, np.random.default_rng(0), base=BASE)
    assert np.allclose(g, BASE)


def test_scramble_preserves_gap_multiset():
    g = make_adversarial_seed("scramble", K, np.random.default_rng(3), base=BASE)
    assert np.allclose(np.sort(np.diff(g)), np.sort(np.diff(BASE)))


def test_reversed_is_gap_reversal():
    g = make_adversarial_seed("reversed", K, np.random.default_rng(0), base=BASE)
    assert np.allclose(np.diff(g), np.diff(BASE)[::-1])


def test_rejects_short_base():
    with pytest.raises(ValueError):
        make_adversarial_seed("goe", 20, np.random.default_rng(0), base=BASE[:5])


def test_rejects_unknown_kind():
    with pytest.raises(ValueError):
        make_adversarial_seed("nope", K, np.random.default_rng(0), base=BASE)
