"""Component-vector reporting — Axiom 9.3, Parameter Importance Inversion.

Axiom 9.3 states that a parameter critical in one regime may be irrelevant in
another, so static importance weights fail at regime transitions. This project
measured exactly that inversion:

* under **frozen ζ-fitted knobs**, `corr_penalty` carried 87–96% of every null's
  gap from ζ, while `density_return` was a minor contributor;
* under **equal-budget cold refit**, `corr_penalty` collapsed to ~1e-6 for both ζ
  and `arith`, leaving `density_return` at 99.7–99.99% of R.

`w_A₁(θⱼ) >> w_A₂(θⱼ)`. Any single fixed blend — including the published
`{shape 0.30, corr 0.25, coverage 0.25, return 0.20}` — is therefore mis-weighted
in one regime or the other, and a scalar built from it cannot support a selection
claim.

The rule this module enforces: **components are reported; scalars must be
declared.** A `ComponentVector` refuses implicit scalarization, and every reduction
carries a name, its weights, and a rationale into the artifact, so a reader can
always see which weighting produced a number. There is no anonymous default.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeclaredReduction:
    """A named, recorded way of collapsing components to one number.

    Anonymous reductions are the failure mode being prevented: the published
    ladder summed six components with fixed weights, four of which were
    structurally zero, and reported the result as a single fitness.
    """

    name: str
    weights: dict[str, float]
    rationale: str
    deprecated_for_selection: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a reduction must be named")
        if not self.weights:
            raise ValueError(f"reduction {self.name!r} has no weights")
        if not self.rationale:
            raise ValueError(f"reduction {self.name!r} needs a rationale")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "weights": dict(self.weights),
            "rationale": self.rationale,
            "deprecated_for_selection": bool(self.deprecated_for_selection),
            "axiom": "9.3 parameter_importance_inversion_principle",
        }


# The published blend. Retained so historical numbers can be reproduced, and
# explicitly refused for selection.
LEGACY_WEIGHTS = DeclaredReduction(
    name="legacy_published_blend",
    weights={
        "stationarity": 0.30,
        "corr_penalty": 0.25,
        "crit_coverage": 0.25,
        "pin_align": 0.20 * 0.40,
        "theta_ladder_l1": 0.20 * 0.35,
        "density_return_l1": 0.20 * 0.25,
    },
    rationale=(
        "Reproduces pre-rectification artifacts only. Refused for selection under "
        "Axiom 9.3: corr_penalty carried 87-96% of the null gap under frozen knobs "
        "and ~1e-6 after refit, so these fixed weights are mis-weighted in one "
        "regime or the other. Four of its six terms were also identically zero."
    ),
    deprecated_for_selection=True,
)

# Candidate carriers for Sub-spec II. Named so an experiment must pick one on the
# record rather than inheriting a default.
DENSITY_ONLY = DeclaredReduction(
    name="density_only",
    weights={"density_return_l1": 1.0},
    rationale=(
        "Formulation A from the rectification spec. Measured to FAIL property 5: "
        "arith reaches 0.0407 against zeta's 0.0884 in-sample, so it prefers a "
        "zero-information spectrum. Kept for comparison, not as a gate."
    ),
)

REVIVED_ONLY = DeclaredReduction(
    name="revived_terms_equal",
    weights={
        "stationarity": 0.25,
        "crit_coverage": 0.25,
        "pin_align": 0.25,
        "theta_ladder_l1": 0.25,
    },
    rationale=(
        "Equal weight over the four terms that revived under an independent "
        "baseline (Axiom 6.1). Diagnostic: shows what the previously-dead terms say "
        "on their own, with no tuning-era weighting carried over."
    ),
)


def reduction_registry() -> dict[str, DeclaredReduction]:
    """All reductions known by name. Extend deliberately, never implicitly."""
    return {
        r.name: r for r in (LEGACY_WEIGHTS, DENSITY_ONLY, REVIVED_ONLY)
    }


class ComponentVector:
    """Residual components, reported. Refuses to become a number by accident."""

    def __init__(self, components: dict[str, float]) -> None:
        clean: dict[str, float] = {}
        for k, v in components.items():
            f = float(v)
            if not math.isfinite(f):
                raise ValueError(f"component {k!r} is not finite: {v!r}")
            clean[str(k)] = f
        self._c = clean

    @property
    def components(self) -> dict[str, float]:
        return dict(self._c)

    def __float__(self) -> float:  # pragma: no cover - the point is that it raises
        raise TypeError(
            "ComponentVector has no implicit scalar value. Pass a DeclaredReduction "
            "to .reduce() so the weighting is recorded in the artifact (Axiom 9.3)."
        )

    def reduce(self, reduction: DeclaredReduction | None) -> dict[str, Any]:
        """Collapse to a scalar under an explicitly named weighting."""
        if reduction is None:
            raise ValueError(
                "a reduction must be named; see reduction_registry() for options"
            )
        missing = [k for k in reduction.weights if k not in self._c]
        if missing:
            raise KeyError(
                f"reduction {reduction.name!r} references unknown components: {missing}"
            )
        scalar = sum(w * self._c[k] for k, w in reduction.weights.items())
        return {
            "scalar": float(scalar),
            "reduction": reduction.to_dict(),
            "components": self.components,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "components": self.components,
            "note": (
                "No scalar is provided. Reductions must be declared by name; see "
                "realm.validate.components.reduction_registry (Axiom 9.3)."
            ),
        }
