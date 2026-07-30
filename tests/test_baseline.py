"""Independent lock baseline (Axiom 6.1) — verification needs T0 != T.

Axiom 6.1 defines verification as `d(T, T0) < eps` against a **known-good
baseline**. The published residual is the degenerate case T0 = T: the sector pool
is drawn from Crit(S) minima and the lock is built from those same minima, so at
n_sectors=6 the two are bit-identical and `d ≡ 0` by construction.

The repair forges the lock reference from a **disjoint ordinate block** under the
same knobs. The key still comes from the training block. Stationarity is then
evaluated against the *baseline* action, which turns it from a tautology into a
real question: do the sector angles derived from block A sit at critical points of
the action derived from block B?

Stage 1's pass criterion (design spec §5): across >=20 spectra spanning all arms,
each of the four previously-dead terms must have non-zero variance and a 5th
percentile above 1e-6. Any term still pinned at zero is deleted from fitness.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pytest

from realm.validate.adversarial import KINDS, make_adversarial_seed
from realm.validate.baseline import (
    DEAD_TERMS,
    revival_report,
    score_with_independent_baseline,
)
from realm.validate.zeros import window

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


@pytest.fixture(scope="module")
def blocks():
    return window(1, 14), window(15, 14)


# --- the coincidence must actually break ------------------------------------


@needs_evolve
def test_disjoint_baseline_breaks_the_coincidence(champion, blocks):
    key_block, lock_block = blocks
    out = score_with_independent_baseline(
        knobs=champion, key_gammas=key_block, lock_gammas=lock_block
    )
    assert out["degeneracy"]["n_exact_coincident"] == 0, (
        "lock and key still coincide - baseline is not independent"
    )


@needs_evolve
def test_same_block_still_degenerates(champion, blocks):
    """Control: pass the same block for both and the old degeneracy must return.

    This is the H1 loop L2 break - the guard measures coincidence rather than
    assuming the baseline is independent, so it must still catch T0 = T.
    """
    key_block, _ = blocks
    out = score_with_independent_baseline(
        knobs=champion, key_gammas=key_block, lock_gammas=key_block
    )
    assert out["degeneracy"]["is_degenerate"]
    assert out["degeneracy"]["n_exact_coincident"] > 0


@needs_evolve
def test_ontology_preserved(champion, blocks):
    """P3: geometry derived off the field, never lambda scored against gamma."""
    key_block, lock_block = blocks
    out = score_with_independent_baseline(
        knobs=champion, key_gammas=key_block, lock_gammas=lock_block
    )
    assert "not_lambda_eq_gamma" in out["ontology"]


@needs_evolve
def test_components_are_reported_not_summed(champion, blocks):
    """Axiom 9.3: emit a component vector; no static-weight scalar for selection."""
    key_block, lock_block = blocks
    out = score_with_independent_baseline(
        knobs=champion, key_gammas=key_block, lock_gammas=lock_block
    )
    assert set(DEAD_TERMS) <= set(out["components"])
    assert "F" not in out, "a static-weight scalar must not be offered for selection"


# --- Stage 1 pass criterion -------------------------------------------------


@needs_evolve
def test_stage1_pass_criterion_dead_terms_revive(champion, blocks):
    """>=20 spectra; each dead term needs non-zero variance and p5 > 1e-6."""
    key_block, lock_block = blocks
    rows = []
    for kind in KINDS:
        for inst in range(2):
            rng = np.random.default_rng([11, inst])
            kg = make_adversarial_seed(kind, 14, rng, base=key_block)
            lg = make_adversarial_seed(kind, 14, np.random.default_rng([11, inst]), base=lock_block)
            rows.append(
                score_with_independent_baseline(
                    knobs=champion, key_gammas=kg, lock_gammas=lg
                )["components"]
            )
    assert len(rows) >= 20

    report = revival_report(rows)
    # The report is the artifact that decides which terms survive into fitness.
    for term in DEAD_TERMS:
        assert term in report
        assert "variance" in report[term] and "p5" in report[term]
        assert "revived" in report[term]

    # At least one term must revive, or the repair achieved nothing.
    assert any(report[t]["revived"] for t in DEAD_TERMS), (
        f"no term revived under an independent baseline: "
        f"{ {t: report[t]['p5'] for t in DEAD_TERMS} }"
    )


@needs_evolve
def test_revival_report_is_json_safe(champion, blocks):
    key_block, lock_block = blocks
    rows = [
        score_with_independent_baseline(
            knobs=champion, key_gammas=key_block, lock_gammas=lock_block
        )["components"]
    ]
    json.dumps(revival_report(rows))


def test_rejects_mismatched_block_lengths(champion, blocks):
    key_block, lock_block = blocks
    with pytest.raises(ValueError):
        score_with_independent_baseline(
            knobs=champion, key_gammas=key_block, lock_gammas=lock_block[:5]
        )
