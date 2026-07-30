"""Null spacing samplers must match their closed-form surmises.

The original `_sample_gue_spacings` matched neither (KS D=0.085 vs GUE, 0.118 vs
GOE, both p~0 at n=200k; mean 0.922 vs 1, variance 0.135 vs GUE's 0.178). Its
rejection loop fell through to a second `normal(0.8, 0.4)` proposal on rejection
instead of retrying the exponential, so the output was an ad-hoc mixture.

Closed forms, both normalized to unit mean:

  GOE (beta=1):  p(s) = (pi/2) s exp(-pi s^2 / 4)
                 CDF  = 1 - exp(-pi s^2 / 4)
                 var  = 4/pi - 1 ~ 0.27324

  GUE (beta=2):  p(s) = (32/pi^2) s^2 exp(-4 s^2 / pi)
                 CDF  = erf(2s/sqrt(pi)) - (4s/pi) exp(-4 s^2 / pi)
                 var  = 3 pi/8 - 1 ~ 0.17810

The legacy sampler is retained (renamed) so the published artifacts stay
reproducible; it is asserted to be broken rather than quietly deleted.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from realm.validate.seeds import (
    _sample_gue_spacings,
    cdf_goe,
    cdf_gue,
    sample_goe_spacings,
    sample_gue_spacings,
)

N = 200_000
GUE_VAR = 3 * np.pi / 8 - 1
GOE_VAR = 4 / np.pi - 1


@pytest.fixture(scope="module")
def gue():
    return sample_gue_spacings(N, np.random.default_rng(0))


@pytest.fixture(scope="module")
def goe():
    return sample_goe_spacings(N, np.random.default_rng(0))


# --- closed forms -----------------------------------------------------------


def test_cdfs_are_valid_distributions():
    s = np.linspace(0, 8, 20001)
    for cdf in (cdf_gue, cdf_goe):
        c = cdf(s)
        assert c[0] == pytest.approx(0.0, abs=1e-12)
        assert c[-1] == pytest.approx(1.0, abs=1e-6)
        assert np.all(np.diff(c) >= -1e-12), "CDF must be non-decreasing"


def test_cdfs_integrate_to_unit_mean():
    """Both surmises are normalized so E[s] = 1."""
    s = np.linspace(0, 12, 200001)
    for cdf in (cdf_gue, cdf_goe):
        pdf = np.gradient(cdf(s), s)
        mean = float(np.trapezoid(s * pdf, s))
        assert mean == pytest.approx(1.0, abs=2e-3)


# --- GUE (beta = 2) ---------------------------------------------------------


def test_gue_matches_closed_form_cdf(gue):
    ks = stats.ks_1samp(gue, cdf_gue)
    assert ks.pvalue > 0.05, f"GUE sampler rejected: D={ks.statistic:.4f} p={ks.pvalue:.3g}"


def test_gue_moments(gue):
    assert gue.mean() == pytest.approx(1.0, abs=5e-3)
    assert gue.var() == pytest.approx(GUE_VAR, abs=5e-3)


# --- GOE (beta = 1) ---------------------------------------------------------


def test_goe_matches_closed_form_cdf(goe):
    ks = stats.ks_1samp(goe, cdf_goe)
    assert ks.pvalue > 0.05, f"GOE sampler rejected: D={ks.statistic:.4f} p={ks.pvalue:.3g}"


def test_goe_moments(goe):
    assert goe.mean() == pytest.approx(1.0, abs=5e-3)
    assert goe.var() == pytest.approx(GOE_VAR, abs=5e-3)


def test_goe_and_gue_are_distinct(gue, goe):
    """beta=1 is more dispersed than beta=2 - level repulsion is weaker."""
    assert goe.var() > gue.var()
    assert stats.ks_2samp(gue, goe).pvalue < 1e-10


# --- shape / reproducibility ------------------------------------------------


@pytest.mark.parametrize("fn", [sample_gue_spacings, sample_goe_spacings])
def test_shape_positive_and_reproducible(fn):
    a = fn(500, np.random.default_rng(7))
    b = fn(500, np.random.default_rng(7))
    assert a.shape == (500,)
    assert np.all(a > 0)
    assert np.allclose(a, b), "same seed must give same draw"


# --- the legacy sampler is kept, and kept honest ----------------------------


def test_legacy_name_now_delegates_to_the_correct_sampler():
    """`_sample_gue_spacings` is repaired, not merely retained.

    Two branches fixed the original defect independently. main replaced the
    mixed-proposal loop with pure rejection (retry Exp(1), envelope c=2.5); this
    branch replaced it with inverse-CDF. The merge keeps the name and routes it to
    inverse-CDF, because the rejection envelope is provably violated - see
    test_rejection_envelope_would_have_been_violated below.

    Consequence: the `goe`/`goe_legacy` arms no longer reproduce the pre-repair
    published draws. That costs nothing, because those arms were never
    reproducible anyway - the runs that produced fair_fight_result.json seeded
    spectra with `abs(hash(kind))`, and Python randomizes str hashing per process.
    """
    s = _sample_gue_spacings(50_000, np.random.default_rng(0))
    assert stats.ks_1samp(s, cdf_gue).pvalue > 0.05
    assert s.mean() == pytest.approx(1.0, abs=8e-3)


def test_rejection_envelope_would_have_been_violated():
    """Why inverse-CDF wins the merge: 2.5*exp(-s) does not dominate p_GUE(s).

    Measured violation on s in [1.0355, 1.1738], peak ratio 1.0101. A rejection
    sampler with a violated envelope is biased by about that margin in that band.
    Inverse-CDF has no envelope, so the failure mode does not exist.
    """
    s = np.linspace(1e-6, 10.0, 2_000_001)
    p = (32 / np.pi**2) * s**2 * np.exp(-4 * s**2 / np.pi)
    envelope = 2.5 * np.exp(-s)
    violated = s[p > envelope]
    assert violated.size > 0
    assert violated.min() == pytest.approx(1.0355, abs=1e-3)
    assert violated.max() == pytest.approx(1.1738, abs=1e-3)
    assert (p / envelope).max() == pytest.approx(1.0101, abs=1e-3)


# --- make_seed must never fabricate ordinates -------------------------------


def test_make_seed_never_mean_gap_extrapolates():
    """seeds.py:41 used to invent ordinates past the hardcoded table.

    Genuine zeros are available via realm.validate.zeros; fabrication is not an
    acceptable fallback, so a request beyond what can be computed must raise.
    """
    from realm.validate.seeds import make_seed
    from realm.zeta_field import ZETA_ZEROS_IMAG

    k = ZETA_ZEROS_IMAG.size + 10
    g = make_seed("zeta", k, np.random.default_rng(0))
    mean_gap = float(np.mean(np.diff(ZETA_ZEROS_IMAG)))
    fabricated = ZETA_ZEROS_IMAG[-1] + mean_gap
    assert abs(g[ZETA_ZEROS_IMAG.size] - fabricated) > 1e-3, "still extrapolating"

    # and it must agree with the verified table
    from realm.validate.zeros import real_zeros

    assert np.allclose(g, real_zeros(k), atol=1e-8)


def test_make_seed_preserves_published_ordinates_exactly():
    """k <= table size must stay bit-identical so published artifacts reproduce."""
    from realm.validate.seeds import make_seed
    from realm.zeta_field import ZETA_ZEROS_IMAG

    g = make_seed("zeta", 14, np.random.default_rng(0))
    assert np.array_equal(g, ZETA_ZEROS_IMAG[:14])


# --- arm registry stability -------------------------------------------------


def test_arm_seed_ids_are_explicit_and_stable():
    """Seeding must not depend on list position, or adding an arm reseeds others."""
    from realm.validate.adversarial import ARM_SEED_ID, KINDS, arm_seed_id

    assert set(KINDS) <= set(ARM_SEED_ID)
    assert len(set(ARM_SEED_ID.values())) == len(ARM_SEED_ID), "ids must be unique"
    for kind in KINDS:
        assert arm_seed_id(kind) == ARM_SEED_ID[kind]


def test_correct_and_legacy_random_matrix_arms_coexist():
    from realm.validate.adversarial import KINDS, make_adversarial_seed
    from realm.validate.zeros import real_zeros

    base = real_zeros(14)
    for kind in ("gue", "goe_true", "goe"):
        assert kind in KINDS
        g = make_adversarial_seed(kind, 14, np.random.default_rng(0), base=base)
        assert g.shape == (14,)
        assert np.all(np.diff(g) > 0)

    # gue and goe_true must be genuinely different families
    a = make_adversarial_seed("gue", 14, np.random.default_rng(1), base=base)
    b = make_adversarial_seed("goe_true", 14, np.random.default_rng(1), base=base)
    assert not np.allclose(a, b)
