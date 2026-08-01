"""Job QC Firewall — explore vs certify split (PRIMON PCF restricted to oilfield).

Doctrine (shared Gate Kernel law; dual-stalk with ig-primon Tier-E / Tier-C):

  * EXPLORE (Tier-E analog): science annex, dynamical topology *measure*, regime
    structure scores, multi-scale / graph λ1 trends, chunk inspect residue.
    These may look good; they never seal a job alone.

  * CERTIFY (Tier-C analog): QC pin hard invariants, is_solved ∧ empty free-param
    board × K (optional topology_stable control only when it joins that fixed-point
    with pin). Only CERTIFY licenses SOLVED / PARTNER_RECIPE / EOW ship.

Thesis (from Precision–Certification Firewall, restricted):
  **Agreement is not verification.** A near-miss is when EXPLORE metrics pass
  (e.g. science native beats decoy, high structure score, long topo bars) while
  CERTIFY fails (pin hard fail or unsolved fixed-point). Explore-agreement would
  ship the near-miss; the firewall **rejects** it.

Never:
  - retune pin / mono ε / pack required set from explore metrics
  - treat not_acceptance fields as SOLVED / ACCEPTANCE
  - λ=γ (graph λ1 is algebraic connectivity only)
  - invent surveys or reorder depth
"""

from __future__ import annotations

from typing import Any

FIREWALL_ONTOLOGY = "job_qc_firewall_explore_vs_certify_v1"
FIREWALL_VERSION = "1.0"

# Explore-only keys that must never flip SOLVED alone (defense in depth).
EXPLORE_ONLY_KEYS: frozenset[str] = frozenset(
    {
        "science_native_score",
        "science_decoy_score",
        "science_native_beats_decoy",
        "regime_structure_score",
        "regime_barcode_n_bars",
        "regime_shock_exceedance",
        "graph_lambda_1",
        "multi_scale_n_long",
        "multi_scale_n_short",
        "rips_h0_n_long",
        "dynamical_topology",
        "trend_rollup",
        "chunk_inspect",
        "not_acceptance",
    }
)

# Certify keys that can participate in SOLVED / partner seal.
CERTIFY_KEYS: frozenset[str] = frozenset(
    {
        "pin_ok",
        "pin_hard_ok",
        "depth_mono_ok",
        "unit_sanity_ok",
        "is_solved_slice",
        "solved",
        "empty_free_param_board",
        "stability_streak",
        "stability_k",
        "topology_stable_control",  # only when topo_stability gate is on
        "export_ok_fraction",
        "verify_ok",
        "physics_n_fail",
        "survey_stalk_ok",  # when survey gate engaged / required
        "regime_stalk_ok",  # only when --require-regime
    }
)


def _truthy(v: Any) -> bool:
    return bool(v) is True


def _last_cycle(ledger: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not ledger:
        return {}
    for e in reversed(ledger):
        if isinstance(e.get("round"), int):
            return e
    return {}


def extract_explore_tier(
    *,
    result: dict[str, Any] | None = None,
    ledger: list[dict[str, Any]] | None = None,
    observations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the EXPLORE (Tier-E) bundle — measure only, never acceptance."""
    r = result or {}
    last = _last_cycle(ledger)
    obs = observations or last.get("observations") or {}
    trend = last.get("trend") or {}
    sci_beats = obs.get("science_native_beats_decoy")
    if sci_beats is None:
        sci_beats = last.get("science_native_beats_decoy")
    structure = obs.get("regime_structure_score")
    if structure is None:
        structure = trend.get("regime_structure_score")
    dt = r.get("dynamical_topology") or {}
    tr = r.get("trend_rollup") or {}

    explore_pass_signals: list[str] = []
    if sci_beats is True:
        explore_pass_signals.append("science_native_beats_decoy")
    try:
        if structure is not None and float(structure) > 0.5:
            explore_pass_signals.append("regime_structure_score_gt_0_5")
    except (TypeError, ValueError):
        pass
    try:
        n_long = dt.get("n_long")
        if n_long is not None and int(n_long) > 0:
            explore_pass_signals.append("dynamical_topology_n_long_gt_0")
    except (TypeError, ValueError):
        pass
    if tr.get("lambda_1_trend") in ("non_decreasing", "flat") and tr.get(
        "lambda_1_series"
    ):
        explore_pass_signals.append("lambda_1_trend_present")

    return {
        "tier": "explore",
        "analog": "Tier-E",
        "not_acceptance": True,
        "pin_writable": False,
        "acceptance_writable": False,
        "ontology": "job_explore_measure_only",
        "fields": {
            "science_enabled": bool(
                obs.get("science_enabled") or last.get("science_enabled") or r.get("with_science")
            ),
            "science_native_score": obs.get("science_native_score")
            if obs.get("science_native_score") is not None
            else last.get("science_native_score"),
            "science_decoy_score": obs.get("science_decoy_score")
            if obs.get("science_decoy_score") is not None
            else last.get("science_decoy_score"),
            "science_native_beats_decoy": sci_beats,
            "regime_enabled": bool(
                obs.get("regime_enabled") or last.get("regime_enabled") or r.get("with_regime")
            ),
            "regime_structure_score": structure,
            "regime_barcode_n_bars": obs.get("regime_barcode_n_bars")
            if obs.get("regime_barcode_n_bars") is not None
            else last.get("regime_barcode_n_bars"),
            "graph_lambda_1": trend.get("graph_lambda_1"),
            "multi_scale_n_long": trend.get("multi_scale_n_long"),
            "dynamical_topology_n_stages": dt.get("n_stages"),
            "dynamical_topology_n_long": dt.get("n_long"),
            "dynamical_topology_n_short": dt.get("n_short"),
            "lambda_1_trend": tr.get("lambda_1_trend"),
            "chunk_inspect_present": r.get("chunk_inspect") is not None,
            # C6: vendor→canonical maps this run (measure/transparency only)
            "alias_applied": (
                (last.get("sources") or {}).get("alias_applied")
                if isinstance(last.get("sources"), dict)
                else None
            )
            or r.get("alias_applied"),
            "n_aliases_applied": len(
                (last.get("sources") or {}).get("alias_applied")
                if isinstance(last.get("sources"), dict)
                and (last.get("sources") or {}).get("alias_applied") is not None
                else (r.get("alias_applied") or [])
            ),
        },
        "looks_promising": len(explore_pass_signals) > 0,
        "pass_signals": explore_pass_signals,
        "doctrine": (
            "Explore metrics may agree with a good job story; they do not certify. "
            "Partner must not ship on explore alone."
        ),
    }


def extract_certify_tier(
    *,
    result: dict[str, Any] | None = None,
    ledger: list[dict[str, Any]] | None = None,
    pin: dict[str, Any] | None = None,
    solved: bool | None = None,
) -> dict[str, Any]:
    """Build the CERTIFY (Tier-C) bundle — pin + fixed-point authority."""
    r = result or {}
    last = _last_cycle(ledger)
    pin_d = pin or last.get("pin") or (r.get("pin_locked") or {})
    # hard_ok preferred; fall back to depth_mono ∧ unit_sanity or overall ok
    hard_ok = pin_d.get("hard_ok")
    if hard_ok is None:
        dm = pin_d.get("depth_mono_ok")
        us = pin_d.get("unit_sanity_ok")
        if dm is not None and us is not None:
            hard_ok = bool(dm) and bool(us)
        else:
            hard_ok = pin_d.get("ok")
    pin_ok = pin_d.get("ok")
    if pin_ok is None and r.get("pin_locked"):
        pin_ok = (r.get("pin_locked") or {}).get("last_ok")

    solved_b = bool(solved) if solved is not None else bool(r.get("solved"))
    is_slice = last.get("is_solved_slice")
    streak = last.get("stability_streak")
    if streak is None:
        streak = r.get("stability_streak")
    k = last.get("stability_k")
    if k is None:
        k = r.get("stability_k", 1)
    topo_ctrl = last.get("topology_stable")
    topo_gate_on = bool(
        last.get("topo_stability")
        if last.get("topo_stability") is not None
        else r.get("topo_stability")
    )

    board = last.get("proposals")
    empty_board = True if solved_b else (board is not None and len(board) == 0)
    if last.get("action") == "halt" and last.get("solved"):
        empty_board = True

    certify_ok = bool(solved_b) and bool(hard_ok is not False)

    reasons: list[str] = []
    if not solved_b:
        reasons.append("not_solved_fixed_point")
    if hard_ok is False:
        reasons.append("pin_hard_fail")
    if pin_ok is False and hard_ok is not True:
        reasons.append("pin_ok_false")
    if certify_ok:
        reasons.append("certified_solved_with_pin")

    return {
        "tier": "certify",
        "analog": "Tier-C",
        "not_acceptance": False,  # this tier *is* the commercial seal language
        "pin_writable": False,
        "ontology": "job_certify_pin_and_fixed_point",
        "fields": {
            "pin_ok": pin_ok,
            "pin_hard_ok": hard_ok,
            "depth_mono_ok": pin_d.get("depth_mono_ok"),
            "unit_sanity_ok": pin_d.get("unit_sanity_ok"),
            "pack_ok": pin_d.get("pack_ok"),
            "solved": solved_b,
            "is_solved_slice": is_slice,
            "empty_free_param_board": empty_board,
            "stability_streak": streak,
            "stability_k": k,
            "topo_stability_gate": topo_gate_on,
            "topology_stable_control": topo_ctrl if topo_gate_on else None,
            "stop_reason": r.get("stop_reason"),
            "partner_recipe": bool(r.get("partner_recipe")),
        },
        "certified": certify_ok,
        "reasons": reasons,
        "doctrine": (
            "Only pin seal + is_solved ∧ empty free-param board × K "
            "(+ optional topology_stable control) certifies commercial SOLVED."
        ),
    }


def evaluate_near_miss(
    explore: dict[str, Any],
    certify: dict[str, Any],
) -> dict[str, Any]:
    """Load-bearing firewall tooth: explore looks good, certify rejects.

    Mirrors PRIMON near-miss: passes FP32-grade agreement, fails Tier-C.
    Here: explore pass_signals non-empty (or looks_promising) while not certified.
    """
    looks = bool(explore.get("looks_promising"))
    signals = list(explore.get("pass_signals") or [])
    certified = bool(certify.get("certified"))
    is_near_miss = looks and not certified
    is_honest = certified and (
        bool(certify.get("fields", {}).get("pin_hard_ok") is not False)
    )
    is_gross = (
        not certified
        and certify.get("fields", {}).get("pin_hard_ok") is False
        and not looks
    )

    verdict = "certified" if certified else (
        "near_miss_rejected" if is_near_miss else (
            "gross_reject" if is_gross else "unsolved_no_explore_claim"
        )
    )

    return {
        "near_miss": is_near_miss,
        "honest_certified": is_honest,
        "gross_reject": is_gross,
        "verdict": verdict,
        "explore_looks_promising": looks,
        "explore_pass_signals": signals,
        "certified": certified,
        "thesis": (
            "Agreement is not verification: explore metrics that look good "
            "while pin/fixed-point fails are rejected (near-miss)."
        ),
        "partner_rule": (
            "Do not ship or claim SOLVED on science/topo/λ1 agreement alone."
        ),
    }


def build_job_firewall(
    *,
    result: dict[str, Any] | None = None,
    ledger: list[dict[str, Any]] | None = None,
    pin: dict[str, Any] | None = None,
    observations: dict[str, Any] | None = None,
    solved: bool | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Assemble full firewall document for RUN.json / COHERENCE.json / FIREWALL.json."""
    r = result or {}
    led = ledger if ledger is not None else list(r.get("ledger") or [])
    explore = extract_explore_tier(
        result=r, ledger=led, observations=observations
    )
    certify = extract_certify_tier(
        result=r, ledger=led, pin=pin, solved=solved if solved is not None else r.get("solved")
    )
    near = evaluate_near_miss(explore, certify)

    return {
        "kind": "job_qc_firewall",
        "ontology": FIREWALL_ONTOLOGY,
        "version": FIREWALL_VERSION,
        "run_id": run_id or r.get("run_id"),
        "not_acceptance": True,  # the *document* is meta; certify.certified is the seal
        "pin_writable": False,
        "acceptance_writable": False,
        "explore": explore,
        "certify": certify,
        "near_miss": near,
        "certified": bool(certify.get("certified")),
        "explore_only_keys": sorted(EXPLORE_ONLY_KEYS),
        "certify_keys": sorted(CERTIFY_KEYS),
        "laws": [
            "Agreement is not verification.",
            "Explore (science/topo/λ1/structure) never retunes pin.",
            "Certify = pin hard seal + is_solved ∧ empty free-param board × K.",
            "Near-miss: explore promising + certify fail → REJECT for ship.",
            "Never λ=γ; graph λ1 is algebraic connectivity only.",
            "Never invent Inc/Azi; never reorder depth for score.",
        ],
        "bridge": {
            "sister": "ig-primon-t1 Precision-Certification Firewall (Tier-E/Tier-C)",
            "restriction": "oilfield Job OS substrate (LAS/MicroPulse/survey)",
            "shared_kernel": "GATE_KERNEL: CLAIM/ANCHOR/LEDGER/RESIDUE; measure≠accept",
        },
        "note": (
            "Job QC Firewall v1 — dual-stalk with PRIMON PCF. "
            "Does not import mpmath anchors; does not move QC pin."
        ),
    }


def assert_firewall_invariants(fw: dict[str, Any]) -> list[str]:
    """Return list of invariant violations (empty = on-shell)."""
    violations: list[str] = []
    if fw.get("pin_writable") is True:
        violations.append("firewall.pin_writable must be False")
    if fw.get("acceptance_writable") is True:
        violations.append("firewall.acceptance_writable must be False")
    exp = fw.get("explore") or {}
    if exp.get("pin_writable") is True:
        violations.append("explore.pin_writable must be False")
    if exp.get("not_acceptance") is not True:
        violations.append("explore.not_acceptance must be True")
    if exp.get("acceptance_writable") is True:
        violations.append("explore.acceptance_writable must be False")
    cert = fw.get("certify") or {}
    if cert.get("pin_writable") is True:
        violations.append("certify.pin_writable must be False")
    # Near-miss must not be certified
    near = fw.get("near_miss") or {}
    if near.get("near_miss") and fw.get("certified"):
        violations.append("near_miss cannot be certified")
    if near.get("near_miss") and cert.get("certified"):
        violations.append("near_miss with certify.certified")
    return violations
