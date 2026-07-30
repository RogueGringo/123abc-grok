"""Exact rank-sum test must handle ties (PR #2 review, comment 3680365770).

The original implementation built a first-occurrence rank map:

    for i, x in enumerate(pooled): rank.setdefault(x, i + 1)

so every duplicate of a tied value received the rank of its *first* occurrence,
while the enumeration summed distinct positional ranks `i + 1`. The observed
statistic and the reference distribution were therefore computed on different
scales whenever ties were present.

Measured on a constructed tie case: obs = 5 where the correct midrank obs = 7.0.

The reported results are unaffected — all 15 held-out density values were distinct
— so this was latent rather than active. Fixed with midranks (scipy.rankdata),
which is the standard treatment and reduces to the old behaviour when untied.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

sys.argv = ["pytest"]
from fair_transfer import _exact_rank_p  # noqa: E402


def test_untied_case_unchanged():
    """The published numbers must still come out as reported."""
    z = [0.11768, 0.146792, 0.147111]
    for other, expected in (
        ([0.3742, 0.3742001, 0.3743], 0.050),  # arith, disjoint
        ([0.171, 0.2113, 0.2188], 0.050),  # scramble, disjoint
        ([0.1263, 0.127, 0.2044], 0.500),  # goe, overlapping
        ([0.1275, 0.1305, 0.159], 0.500),  # poisson, overlapping
    ):
        _, p = _exact_rank_p(z, other)
        assert p == pytest.approx(expected, abs=1e-9)


def test_ties_use_midranks():
    """Tied values must share the average of their positions."""
    a = [1.0, 2.0, 2.0]
    b = [2.0, 3.0, 4.0]
    obs, p = _exact_rank_p(a, b)
    # pooled ranks with midranks: 1.0->1, three 2.0s -> (2+3+4)/3 = 3, 3.0->5, 4.0->6
    assert obs == pytest.approx(1.0 + 3.0 + 3.0)
    assert 0.0 < p <= 1.0


def test_all_tied_gives_p_one():
    """No separation possible: every arrangement is as extreme as observed."""
    obs, p = _exact_rank_p([1.0, 1.0, 1.0], [1.0, 1.0, 1.0])
    assert p == pytest.approx(1.0)


def test_p_is_a_valid_probability():
    rng = np.random.default_rng(0)
    for _ in range(30):
        a = list(np.round(rng.normal(size=4), 2))  # rounding forces ties
        b = list(np.round(rng.normal(size=4), 2))
        _, p = _exact_rank_p(a, b)
        assert 0.0 < p <= 1.0


def test_perfect_separation_hits_the_floor():
    from math import comb

    a = [1.0, 2.0, 3.0]
    b = [4.0, 5.0, 6.0]
    _, p = _exact_rank_p(a, b)
    assert p == pytest.approx(1.0 / comb(6, 3))


def test_symmetry_of_complementary_call():
    """Swapping the groups must give the complementary tail, not the same value."""
    a = [1.0, 2.0, 3.0]
    b = [4.0, 5.0, 6.0]
    _, p_ab = _exact_rank_p(a, b)
    _, p_ba = _exact_rank_p(b, a)
    assert p_ab < 0.5 < p_ba
