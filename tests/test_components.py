"""Component-vector reporting — Axiom 9.3, Parameter Importance Inversion.

9.3: "a parameter critical in one regime may be irrelevant in another." Measured
directly in this project:

| regime | corr_penalty share of the zeta-null gap | density_return share of R |
|---|---|---|
| frozen zeta-fitted knobs | 87-96% | small |
| equal-budget cold refit | ~0 (1.9e-6 zeta, 2.7e-5 arith) | 99.7-99.99% |

That is `w_A1(theta_j) >> w_A2(theta_j)`. A single fixed weighting is therefore
mis-weighted in one regime or the other, so the published
`{shape 0.30, corr 0.25, coverage 0.25, return 0.20}` blend cannot be used for
selection.

The rule enforced here: components are reported; any scalar reduction must be
**declared by name and recorded in the artifact**. There is no anonymous default.
"""

from __future__ import annotations

import json

import pytest

from realm.validate.components import (
    LEGACY_WEIGHTS,
    ComponentVector,
    DeclaredReduction,
    reduction_registry,
)

COMPONENTS = {
    "stationarity": 0.5193,
    "crit_coverage": 0.0621,
    "pin_align": 0.1690,
    "theta_ladder_l1": 0.0971,
    "corr_penalty": 1.9e-6,
    "density_return_l1": 0.0884,
}


def test_component_vector_reports_without_scalarizing():
    cv = ComponentVector(COMPONENTS)
    assert cv.to_dict()["components"] == COMPONENTS
    assert "F" not in cv.to_dict()
    assert "total" not in cv.to_dict()


def test_scalar_requires_a_declared_reduction():
    cv = ComponentVector(COMPONENTS)
    with pytest.raises(TypeError):
        float(cv)  # no implicit scalarization
    with pytest.raises(ValueError):
        cv.reduce(None)  # must name one


def test_declared_reduction_records_itself_in_the_artifact():
    cv = ComponentVector(COMPONENTS)
    red = DeclaredReduction(
        name="density_only",
        weights={"density_return_l1": 1.0},
        rationale="Stage 7 candidate carrier",
    )
    out = cv.reduce(red)
    assert out["scalar"] == pytest.approx(0.0884)
    assert out["reduction"]["name"] == "density_only"
    assert out["reduction"]["weights"] == {"density_return_l1": 1.0}
    assert out["reduction"]["rationale"]
    json.dumps(out)  # must be artifact-safe


def test_legacy_blend_is_available_but_flagged():
    """Kept so published numbers reproduce; refused for selection."""
    assert LEGACY_WEIGHTS in reduction_registry().values()
    assert LEGACY_WEIGHTS.deprecated_for_selection is True
    cv = ComponentVector(COMPONENTS)
    out = cv.reduce(LEGACY_WEIGHTS)
    assert out["reduction"]["deprecated_for_selection"] is True
    assert "9.3" in out["reduction"]["rationale"]


def test_reduction_rejects_unknown_component():
    cv = ComponentVector(COMPONENTS)
    bad = DeclaredReduction(name="typo", weights={"densty_return": 1.0}, rationale="x")
    with pytest.raises(KeyError):
        cv.reduce(bad)


def test_reduction_requires_nonempty_weights():
    with pytest.raises(ValueError):
        DeclaredReduction(name="empty", weights={}, rationale="x")


def test_reduction_requires_rationale():
    with pytest.raises(ValueError):
        DeclaredReduction(name="x", weights={"stationarity": 1.0}, rationale="")


def test_registry_names_are_unique():
    reg = reduction_registry()
    assert len(reg) == len({r.name for r in reg.values()})


def test_component_vector_rejects_non_finite():
    with pytest.raises(ValueError):
        ComponentVector({"stationarity": float("inf")})
