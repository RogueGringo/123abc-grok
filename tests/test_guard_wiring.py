"""The guard and the component vector must be ENFORCED, not merely available.

Axiom 6.2 permits reject | flag | rollback, and the published ladder demonstrated
that a flag nobody reads is indistinguishable from no guard at all. So the
degeneracy signature has to reach the path where fitness is actually computed
(`realm.validate.refit.score_gammas`), which every tournament and refit calls.

Three policies, because reproducing history and making new claims need different
strictness:

* ``guard="stamp"`` (default) — measure and record. Published configurations still
  score, but every artifact carries the signature, so a degenerate result can never
  again look clean.
* ``guard="reject"`` — raise. Required for anything used to select or to claim.
* ``guard="off"`` — explicit opt-out; must be asked for by name.

Axiom 9.3 is enforced in the same place: the scalar `F` is still emitted for
continuity, but it must arrive labelled with the reduction that produced it, so no
number is anonymous.
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pytest

from realm.validate.guard import GuardRejection
from realm.validate.refit import score_gammas
from realm.validate.zeros import real_zeros
from realm.zeta_field import ZETA_ZEROS_IMAG

CHAMPION_VEC = None  # filled by fixture


@pytest.fixture(autouse=True)
def _quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture(scope="module")
def champion_vec():
    import json as _json
    from pathlib import Path

    from realm.validate.refit import knobs_to_vec

    kn = _json.loads(Path("evolve_result.json").read_text(encoding="utf-8"))["best_knobs"]
    return knobs_to_vec(kn, float(ZETA_ZEROS_IMAG[13]))


# --- the guard reaches the fitness path -------------------------------------


def test_default_policy_stamps_the_signature(champion_vec):
    out = score_gammas(champion_vec, gammas=ZETA_ZEROS_IMAG[:14])
    assert "degeneracy" in out, "guard is not wired into score_gammas"
    assert out["degeneracy"]["is_degenerate"] is True
    assert out["degeneracy"]["stamp"] == "DEGENERATE_OBJECTIVE"


def test_reject_policy_refuses_the_published_champion(champion_vec):
    """The configuration that motivated the guard must not be selectable."""
    with pytest.raises(GuardRejection):
        score_gammas(champion_vec, gammas=ZETA_ZEROS_IMAG[:14], guard="reject")


def test_off_policy_must_be_named(champion_vec):
    out = score_gammas(champion_vec, gammas=ZETA_ZEROS_IMAG[:14], guard="off")
    assert out.get("degeneracy") is None


def test_unknown_policy_is_rejected(champion_vec):
    with pytest.raises(ValueError):
        score_gammas(champion_vec, gammas=ZETA_ZEROS_IMAG[:14], guard="maybe")


# --- stamping must not change the numbers -----------------------------------


def test_stamping_does_not_perturb_the_published_value(champion_vec):
    """Non-destructive: F must be bit-identical with the guard stamping."""
    PUB = 0.004532164789813
    out = score_gammas(champion_vec, gammas=ZETA_ZEROS_IMAG[:14], guard="stamp")
    assert out["F"] == pytest.approx(PUB, abs=1e-14)
    off = score_gammas(champion_vec, gammas=ZETA_ZEROS_IMAG[:14], guard="off")
    assert out["F"] == off["F"]
    assert out["R"] == off["R"]


# --- Axiom 9.3: no anonymous scalar -----------------------------------------


def test_scalar_arrives_labelled_with_its_reduction(champion_vec):
    out = score_gammas(champion_vec, gammas=ZETA_ZEROS_IMAG[:14])
    assert "components" in out, "component vector is not reported"
    assert "reduction" in out, "F is anonymous - which weighting produced it?"
    red = out["reduction"]
    assert red["name"]
    assert red["weights"]
    assert red["rationale"]
    assert red["deprecated_for_selection"] is True


def test_components_cover_all_previously_dead_terms(champion_vec):
    from realm.validate.baseline import DEAD_TERMS

    out = score_gammas(champion_vec, gammas=ZETA_ZEROS_IMAG[:14])
    assert set(DEAD_TERMS) <= set(out["components"])


def test_output_is_artifact_safe(champion_vec):
    out = score_gammas(champion_vec, gammas=ZETA_ZEROS_IMAG[:14])
    json.dumps(out)


# --- a healthy configuration is not blocked ---------------------------------


def test_same_block_path_can_never_pass_the_guard(champion_vec):
    """Measured: 0 of 9 (sectors x k) combinations pass. This is structural.

    On the same-block path `key.thetas` is always drawn from the critical minima
    that `build_lock` also reads, so the coincidence and vacuous-stationarity
    conditions fire for every sector count and every ordinate count. Raising
    n_sectors does NOT repair it — the constraint-count argument alone is not a
    remedy. Only an independent baseline (Axiom 6.1) can clear this guard.
    """
    for n_sectors in (6, 8, 12):
        for k in (14, 20, 28):
            with pytest.raises(GuardRejection):
                score_gammas(
                    champion_vec,
                    gammas=real_zeros(k),
                    n_sectors=n_sectors,
                    guard="reject",
                )


def test_independent_baseline_path_can_pass_the_guard():
    """Guard must be selective, not a blanket refusal.

    The counterpart to the test above: with a disjoint lock block the coincidence
    breaks (measured 0 for every arm) and configurations can pass. If nothing could
    ever pass, the guard would be useless rather than strict.
    """
    import json as _json
    from pathlib import Path

    from realm.validate.adversarial import make_adversarial_seed
    from realm.validate.baseline import score_with_independent_baseline
    from realm.validate.zeros import window

    kn = _json.loads(Path("evolve_result.json").read_text(encoding="utf-8"))["best_knobs"]
    kb, lb = window(1, 14), window(15, 14)
    passed = 0
    for kind in ("zeta", "poisson", "scramble", "geometric"):
        out = score_with_independent_baseline(
            knobs=kn,
            key_gammas=make_adversarial_seed(
                kind, 14, np.random.default_rng([11, 0]), base=kb
            ),
            lock_gammas=make_adversarial_seed(
                kind, 14, np.random.default_rng([11, 0]), base=lb
            ),
        )
        assert out["degeneracy"]["n_exact_coincident"] == 0
        passed += not out["degeneracy"]["is_degenerate"]
    assert passed > 0, "independent baseline still cannot clear the guard"
