"""Job QC Firewall: explore vs certify; near-miss rejected; pin never writable."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from realm.job_os.firewall import (
    CERTIFY_KEYS,
    EXPLORE_ONLY_KEYS,
    assert_firewall_invariants,
    build_job_firewall,
    evaluate_near_miss,
    extract_certify_tier,
    extract_explore_tier,
)
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.types import FreeParams, JobThresholds

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_edr.las"


def test_explore_tier_not_acceptance_and_not_pin_writable():
    exp = extract_explore_tier(
        result={
            "with_science": True,
            "dynamical_topology": {"n_stages": 3, "n_long": 1, "n_short": 2},
            "trend_rollup": {"lambda_1_trend": "flat", "lambda_1_series": [0.1, 0.1]},
        },
        observations={
            "science_enabled": True,
            "science_native_beats_decoy": True,
            "science_native_score": 0.9,
            "science_decoy_score": 0.2,
            "regime_structure_score": 0.8,
        },
    )
    assert exp["not_acceptance"] is True
    assert exp["pin_writable"] is False
    assert exp["acceptance_writable"] is False
    assert exp["looks_promising"] is True
    assert "science_native_beats_decoy" in exp["pass_signals"]


def test_certify_tier_requires_solved_and_pin():
    cert_ok = extract_certify_tier(
        result={"solved": True, "stability_k": 1, "stability_streak": 1},
        pin={"ok": True, "hard_ok": True, "depth_mono_ok": True, "unit_sanity_ok": True},
        solved=True,
    )
    assert cert_ok["certified"] is True
    assert cert_ok["pin_writable"] is False

    cert_fail = extract_certify_tier(
        result={"solved": False, "stop_reason": "pin_fail"},
        pin={"ok": False, "hard_ok": False, "depth_mono_ok": False},
        solved=False,
    )
    assert cert_fail["certified"] is False
    assert "pin_hard_fail" in cert_fail["reasons"] or "not_solved_fixed_point" in cert_fail["reasons"]


def test_near_miss_explore_good_certify_fail():
    explore = {
        "looks_promising": True,
        "pass_signals": ["science_native_beats_decoy", "regime_structure_score_gt_0_5"],
    }
    certify = {"certified": False, "fields": {"pin_hard_ok": False}}
    near = evaluate_near_miss(explore, certify)
    assert near["near_miss"] is True
    assert near["certified"] is False
    assert near["verdict"] == "near_miss_rejected"
    assert "Agreement is not verification" in near["thesis"]


def test_near_miss_not_when_certified():
    explore = {"looks_promising": True, "pass_signals": ["science_native_beats_decoy"]}
    certify = {
        "certified": True,
        "fields": {"pin_hard_ok": True},
    }
    near = evaluate_near_miss(explore, certify)
    assert near["near_miss"] is False
    assert near["honest_certified"] is True
    assert near["verdict"] == "certified"


def test_build_firewall_near_miss_invariants():
    fw = build_job_firewall(
        result={
            "run_id": "test_nm",
            "solved": False,
            "stop_reason": "pin_fail",
            "with_science": True,
            "dynamical_topology": {"n_long": 2, "n_stages": 4},
            "ledger": [
                {
                    "round": 1,
                    "is_solved_slice": False,
                    "proposals": [{"section": "export"}],
                    "pin": {"ok": False, "hard_ok": False, "depth_mono_ok": False},
                    "observations": {
                        "science_enabled": True,
                        "science_native_beats_decoy": True,
                        "regime_structure_score": 0.9,
                    },
                    "science_native_beats_decoy": True,
                }
            ],
        },
        solved=False,
        run_id="test_nm",
    )
    assert fw["kind"] == "job_qc_firewall"
    assert fw["pin_writable"] is False
    assert fw["acceptance_writable"] is False
    assert fw["explore"]["looks_promising"] is True
    assert fw["certify"]["certified"] is False
    assert fw["near_miss"]["near_miss"] is True
    assert fw["certified"] is False
    assert assert_firewall_invariants(fw) == []


def test_build_firewall_honest_solved():
    fw = build_job_firewall(
        result={
            "run_id": "test_ok",
            "solved": True,
            "stability_k": 1,
            "stability_streak": 1,
            "partner_recipe": "/tmp/PARTNER_RECIPE.json",
            "ledger": [
                {
                    "round": 1,
                    "action": "halt",
                    "solved": True,
                    "is_solved_slice": True,
                    "proposals": [],
                    "stability_streak": 1,
                    "stability_k": 1,
                    "pin": {
                        "ok": True,
                        "hard_ok": True,
                        "depth_mono_ok": True,
                        "unit_sanity_ok": True,
                    },
                    "observations": {"science_native_beats_decoy": None},
                }
            ],
        },
        solved=True,
    )
    assert fw["certified"] is True
    assert fw["near_miss"]["near_miss"] is False
    assert assert_firewall_invariants(fw) == []


def test_explore_keys_disjoint_from_certify_core():
    # Science / structure / topo must not sit in certify key set as sole seal
    assert "science_native_beats_decoy" in EXPLORE_ONLY_KEYS
    assert "dynamical_topology" in EXPLORE_ONLY_KEYS
    assert "graph_lambda_1" in EXPLORE_ONLY_KEYS
    assert "pin_ok" in CERTIFY_KEYS
    assert "solved" in CERTIFY_KEYS
    assert "science_native_beats_decoy" not in CERTIFY_KEYS


def test_os_loop_writes_firewall_json(tmp_path: Path):
    out = tmp_path / "job_fw"
    result = run_job_coherence_loop(
        las_path=FIXTURE,
        out_root=out,
        initial=FreeParams(channel_pack="surface_min", align_mode="depth_primary"),
        thresholds=JobThresholds(),
        max_rounds=4,
        os_mode=True,
        stability_k=1,
    )
    assert result.get("firewall") is not None
    fw = result["firewall"]
    assert fw["pin_writable"] is False
    assert fw["explore"]["not_acceptance"] is True
    assert "certified" in fw
    assert assert_firewall_invariants(fw) == []

    # Artifact on disk under run dir
    run_dir = Path(result["out_root"])
    assert (run_dir / "FIREWALL.json").is_file()
    assert (run_dir / "COHERENCE.json").is_file()
    disk_fw = json.loads((run_dir / "FIREWALL.json").read_text(encoding="utf-8"))
    assert disk_fw["kind"] == "job_qc_firewall"
    assert disk_fw["pin_writable"] is False

    coh = json.loads((run_dir / "COHERENCE.json").read_text(encoding="utf-8"))
    assert "firewall" in coh
    assert coh["firewall"]["ontology"].startswith("job_qc_firewall")

    if result.get("os_mode"):
        run_doc = json.loads((run_dir / "RUN.json").read_text(encoding="utf-8"))
        assert "firewall" in run_doc
        assert run_doc["firewall"]["pin_writable"] is False
        assert "firewall_certified" in run_doc

    md = (run_dir / "COHERENCE.md").read_text(encoding="utf-8")
    assert "Job QC Firewall" in md
    assert "Agreement is not verification" in md or "near-miss" in md.lower()


def test_firewall_certified_matches_solved_on_fixture(tmp_path: Path):
    result = run_job_coherence_loop(
        las_path=FIXTURE,
        out_root=tmp_path / "job_fw2",
        initial=FreeParams(channel_pack="surface_min"),
        thresholds=JobThresholds(),
        max_rounds=6,
        os_mode=True,
        stability_k=1,
    )
    # Fixture surface_min is designed to SOLVE; firewall must agree when solved
    if result["solved"]:
        assert result["firewall_certified"] is True
        assert result["firewall_near_miss"] is False
    else:
        # If unsolved, must not claim certified
        assert result["firewall_certified"] is False


def test_invariant_flags_bad_pin_writable():
    bad = build_job_firewall(result={"solved": False}, solved=False)
    bad["pin_writable"] = True
    v = assert_firewall_invariants(bad)
    assert any("pin_writable" in x for x in v)
