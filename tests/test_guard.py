"""Degeneracy guard (Axiom 6.2) — reject configurations whose residual is vacuous.

Axiom 6.2: operations that destroy topological signature are invalid and must be
rejected, flagged, or rolled back. The published ladder had exactly such a
destruction and never detected it: at n_sectors=6 the lock and key are the same
array, so 0.70 of the residual weight is identically zero.

The guard measures the signature rather than assuming independence (this is the
break for H1 loop L2 in the design spec: "degenerate" cannot be defined by
assuming the baseline is independent, because the baseline can itself collapse).

Its sharpest test is that it must fire on the *published champion* — a guard that
passes the configuration which motivated its existence is wrong.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pytest

from realm.lock_key import Keymaker, build_key, build_lock, residual

# Aliased: `test_valley_occupancy` is a production function, but pytest collects
# any test-module name starting with `test_` and would try to run it as a test.
from realm.projection import build_moduli_landscape
from realm.projection import test_valley_occupancy as valley_occupancy
from realm.validate.guard import (
    DegeneracySignature,
    GuardRejection,
    measure_degeneracy,
    require_non_degenerate,
)
from realm.validate.zeros import real_zeros

EVOLVE = Path("evolve_result.json")
needs_evolve = pytest.mark.skipif(not EVOLVE.is_file(), reason="champion knobs absent")


@pytest.fixture(autouse=True)
def _quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture(scope="module")
def champion():
    return json.loads(EVOLVE.read_text(encoding="utf-8"))["best_knobs"]


def _forge(knobs, gammas, n_sectors=6):
    der = Keymaker(N=13, n_zeros=int(gammas.size), n_sectors=n_sectors).forge(
        **knobs, gammas=gammas
    )
    lock = build_lock(der)
    key = build_key(der)
    res = residual(lock, key, action=der.action)
    land = build_moduli_landscape(
        field=der.field, action=der.action, critical=der.critical
    )
    occ = valley_occupancy(
        key.thetas,
        landscape=land,
        labels=[f"k{i + 1}" for i in range(len(key.thetas))],
        spectral_gaps=key.spectral_gaps,
    )
    return key, lock, res, occ


# --- the criterion that matters ---------------------------------------------


@needs_evolve
def test_guard_fires_on_the_published_champion(champion):
    """Spec Stage 3 pass criterion. If this fails, the guard is wrong."""
    key, lock, res, occ = _forge(champion, real_zeros(14))
    sig = measure_degeneracy(
        key_thetas=key.thetas,
        lock_minima=lock.minima_theta,
        stationarity=res.shape_l1,
        crit_coverage=res.crit_coverage,
        occupancy=occ.occupancy_fraction,
    )
    assert sig.is_degenerate
    # all four conditions are independently tripped
    assert sig.n_exact_coincident == 6
    assert sig.occupancy_saturated
    assert sig.stationarity_vacuous
    assert sig.coverage_vacuous
    assert "DEGENERATE_OBJECTIVE" in sig.stamp


@needs_evolve
def test_require_non_degenerate_rejects_champion(champion):
    key, lock, res, occ = _forge(champion, real_zeros(14))
    with pytest.raises(GuardRejection) as exc:
        require_non_degenerate(
            measure_degeneracy(
                key_thetas=key.thetas,
                lock_minima=lock.minima_theta,
                stationarity=res.shape_l1,
                crit_coverage=res.crit_coverage,
                occupancy=occ.occupancy_fraction,
            )
        )
    assert "DEGENERATE_OBJECTIVE" in str(exc.value)


# --- the guard measures, it does not assume ---------------------------------


def test_coincidence_is_measured_not_assumed():
    """Disjoint sets must report zero coincidence; identical sets must report all."""
    a = np.array([0.1, 1.0, 2.0, 3.0])
    sig_same = measure_degeneracy(
        key_thetas=a, lock_minima=a.copy(), stationarity=1.0, crit_coverage=1.0, occupancy=0.5
    )
    assert sig_same.n_exact_coincident == 4
    assert sig_same.is_degenerate

    b = a + 0.37
    sig_diff = measure_degeneracy(
        key_thetas=a, lock_minima=b, stationarity=1.0, crit_coverage=1.0, occupancy=0.5
    )
    assert sig_diff.n_exact_coincident == 0
    assert not sig_diff.is_degenerate


@pytest.mark.parametrize(
    "kwargs,expect_flag",
    [
        ({"stationarity": 1e-9}, "stationarity_vacuous"),
        ({"crit_coverage": 0.0}, "coverage_vacuous"),
        ({"occupancy": 1.0}, "occupancy_saturated"),
    ],
)
def test_each_condition_fires_independently(kwargs, expect_flag):
    """Any single condition is sufficient - they are OR'd, not AND'd."""
    base = dict(
        key_thetas=np.array([0.1, 1.0, 2.0]),
        lock_minima=np.array([0.5, 1.5, 2.5]),  # disjoint
        stationarity=1.0,
        crit_coverage=1.0,
        occupancy=0.5,
    )
    sig = measure_degeneracy(**{**base, **kwargs})
    assert getattr(sig, expect_flag) is True
    assert sig.is_degenerate


def test_healthy_configuration_passes():
    sig = measure_degeneracy(
        key_thetas=np.array([0.1, 1.0, 2.0]),
        lock_minima=np.array([0.5, 1.5, 2.5]),
        stationarity=0.2,
        crit_coverage=0.15,
        occupancy=0.67,
    )
    assert not sig.is_degenerate
    assert sig.stamp == ""
    require_non_degenerate(sig)  # must not raise


def test_signature_is_json_safe():
    sig = measure_degeneracy(
        key_thetas=np.array([0.1, 1.0]),
        lock_minima=np.array([0.1, 2.0]),
        stationarity=0.5,
        crit_coverage=0.5,
        occupancy=0.5,
    )
    blob = json.dumps(sig.to_dict())
    assert json.loads(blob)["n_exact_coincident"] == 1


def test_empty_inputs_are_degenerate_not_crashing():
    sig = measure_degeneracy(
        key_thetas=np.array([]),
        lock_minima=np.array([]),
        stationarity=0.5,
        crit_coverage=0.5,
        occupancy=0.5,
    )
    assert sig.is_degenerate  # no keys means nothing was verified


def test_signature_type():
    sig = measure_degeneracy(
        key_thetas=np.array([1.0]),
        lock_minima=np.array([2.0]),
        stationarity=0.5,
        crit_coverage=0.5,
        occupancy=0.5,
    )
    assert isinstance(sig, DegeneracySignature)
