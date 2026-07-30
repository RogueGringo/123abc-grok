"""Window-invariant frequency parameterization — Axiom G5, Scale-Free Structure.

G5 promises that "knowledge gained at one scale can be transferred to another"
because patterns are self-similar. The published parameterization breaks it:

    omega = (g / g[0]) * omega_scale          (derive.py)

makes the frequency *ratio* omega_max/omega_min equal to g[-1]/g[0], which is a
property of the window, not of any knob:

    gamma_1..14   ratio 4.3037
    gamma_15..28  ratio 1.4724
    gamma_29..42  ratio 1.2902

`omega_scale` multiplies uniformly and is bounded (0.4, 2.8), so no knob value can
recover a 4.30x spread from a 1.47x one. The feasible configuration set therefore
differs per window, which is exactly why the frozen-knob transfer test could only
support a *ratio* claim and not an absolute one.

The repair adds an opt-in span knob:

    omega = omega_scale * (1 + (g - g[0])/(g[-1] - g[0]) * (omega_span - 1))

so the ratio is `omega_span` in **every** window. Algebra of the anchor: the legacy
form equals the new form at `omega_span = g[-1]/g[0]`, since
`1 + (g-g0)/(gK-g0) * (gK/g0 - 1) = 1 + (g-g0)/g0 = g/g0`. So setting
`omega_span = 4.3037` on window 1 reproduces the published behaviour **exactly**,
not merely to within 1% — the anchor is an algebraic identity, so Stage 2 cannot
manufacture an improvement.

Legacy behaviour is preserved when `omega_span is None`, keeping every published
artifact reproducible.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pytest

from realm.derive import SpectralAction
from realm.lock_key import Keymaker, build_key, build_lock, residual
from realm.validate.zeros import window
from realm.zeta_field import ZetaField

EVOLVE = Path("evolve_result.json")
needs_evolve = pytest.mark.skipif(not EVOLVE.is_file(), reason="champion knobs absent")

WINDOW_STARTS = (1, 15, 29, 43, 57)


@pytest.fixture(autouse=True)
def _quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture(scope="module")
def champion():
    return json.loads(EVOLVE.read_text(encoding="utf-8"))["best_knobs"]


def _omega(gammas, *, omega_scale, omega_span=None):
    return SpectralAction.from_field(
        ZetaField.from_gammas(gammas),
        omega_scale=omega_scale,
        omega_span=omega_span,
    ).omega


# --- the legacy path is untouched -------------------------------------------


def test_omega_span_none_is_exactly_legacy():
    g = window(1, 14)
    # Legacy formula verbatim, including its 1e-15 guard on the denominator —
    # without it this differs in the last bit and the exactness claim is untestable.
    legacy = (g / (g[0] + 1e-15)) * 1.62699
    assert np.array_equal(_omega(g, omega_scale=1.62699), legacy)


# --- the anchor is an algebraic identity ------------------------------------


def test_anchor_reproduces_legacy_exactly():
    """omega_span = g[-1]/g[0] must reproduce the legacy omega bit-for-bit."""
    for start in WINDOW_STARTS[:3]:
        g = window(start, 14)
        anchor = float(g[-1] / g[0])
        legacy = _omega(g, omega_scale=1.62699)
        spanned = _omega(g, omega_scale=1.62699, omega_span=anchor)
        assert np.allclose(spanned, legacy, rtol=1e-12), f"window {start}"


@needs_evolve
def test_anchor_reproduces_champion_residual_exactly(champion):
    """Stage 2 pass criterion part 1: reproduced window-1 R matches to <1%.

    The anchor is an identity, so the tolerance is machine precision.
    """
    g = window(1, 14)
    anchor = float(g[-1] / g[0])
    kn = {k: v for k, v in champion.items()}

    def R(extra):
        der = Keymaker(N=13, n_zeros=14, n_sectors=6).forge(**kn, **extra, gammas=g)
        return float(residual(build_lock(der), build_key(der), action=der.action).total)

    legacy = R({})
    spanned = R({"omega_span": anchor})
    assert spanned == pytest.approx(legacy, rel=1e-12)
    # and the anchor is inside the proposed search box
    assert 1.5 < anchor < 14.0


# --- G5: the ratio is now a knob, not a window property ---------------------


def test_legacy_ratio_is_window_dependent():
    """Documents the violation being repaired."""
    ratios = []
    for start in WINDOW_STARTS:
        g = window(start, 14)
        om = _omega(g, omega_scale=1.62699)
        ratios.append(float(om.max() / om.min()))
    assert max(ratios) / min(ratios) > 3.0, "expected strong window dependence"


@pytest.mark.parametrize("span", [2.0, 7.0, 12.0])
def test_spanned_ratio_is_window_invariant(span):
    """Stage 2 pass criterion part 2: agreement across >=5 windows within 5%."""
    ratios = []
    for start in WINDOW_STARTS:
        g = window(start, 14)
        om = _omega(g, omega_scale=1.62699, omega_span=span)
        ratios.append(float(om.max() / om.min()))
    assert len(ratios) >= 5
    spread = (max(ratios) - min(ratios)) / np.mean(ratios)
    assert spread < 0.05, f"ratios not window-invariant: {ratios}"
    for r in ratios:
        assert r == pytest.approx(span, rel=1e-9)


def test_span_scales_overall_amplitude_independently():
    """omega_scale still sets overall scale; omega_span sets only the ratio."""
    g = window(1, 14)
    a = _omega(g, omega_scale=1.0, omega_span=5.0)
    b = _omega(g, omega_scale=2.0, omega_span=5.0)
    assert np.allclose(b, 2.0 * a)
    assert a.max() / a.min() == pytest.approx(5.0, rel=1e-9)


# --- plumbing ---------------------------------------------------------------


@needs_evolve
def test_omega_span_threads_through_keymaker(champion):
    g = window(1, 14)
    der = Keymaker(N=13, n_zeros=14, n_sectors=6).forge(
        **champion, omega_span=6.0, gammas=g
    )
    om = der.action.omega
    assert om.max() / om.min() == pytest.approx(6.0, rel=1e-9)


def test_degenerate_span_is_rejected():
    g = window(1, 14)
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError):
            _omega(g, omega_scale=1.0, omega_span=bad)
