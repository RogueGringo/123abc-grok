"""Job Coherence OS P4: regime stalk + dual-gate science (info only)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from realm.job_os.ingest_las import parse_las
from realm.job_os.ingest_micropulse import join_surface_micropulse, load_micropulse_bundle
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.observe import is_solved, observe_job
from realm.job_os.propose import collect_section_proposals
from realm.job_os.regime import (
    channel_h0_summary,
    evaluate_regime,
    h0_runs_above,
    shock_exceedance,
    structure_score,
    window_length,
)
from realm.job_os.science import dual_gate_windows, evaluate_science
from realm.job_os.types import FreeParams, JobThresholds, Observations

FIX = Path(__file__).resolve().parent / "fixtures"
LAS = FIX / "mini_edr.las"
ROOT = Path(__file__).resolve().parents[1]


def test_fixtures_exist():
    assert LAS.is_file()


def test_window_length_scales():
    assert window_length(20, 1) == 4
    assert window_length(20, 2) == 8
    assert window_length(20, 8) == 20  # clamped to n_rows
    assert window_length(0, 1) == 0


def test_h0_runs_above():
    vals = [0.0, 1.0, 1.0, 0.0, 2.0, 0.0]
    bars = h0_runs_above(vals, 0.5)
    assert bars == [2, 1]


def test_channel_h0_summary_on_sssi():
    series = parse_las(LAS)
    sssi = [float(x) for x in series["channels"]["SSSI"]]
    summary = channel_h0_summary(sssi, window_scale=1)
    assert summary["n_samples"] == 20
    assert summary["n_windows"] >= 1
    assert summary["window_len"] == 4
    assert "barcode_n_bars" in summary
    assert summary["total_persistence"] >= 0.0


def test_evaluate_regime_off_stub():
    series = parse_las(LAS)
    rep = evaluate_regime(series, regime_mode="off", enabled=False)
    assert rep["enabled"] is False
    assert rep["stalk_ok"] is True
    assert rep["informational_only"] is True


def test_evaluate_regime_persist_h0_on_fixture():
    series = parse_las(LAS)
    rep = evaluate_regime(
        series,
        regime_mode="persist_h0",
        window_scale=1,
        enabled=True,
    )
    assert rep["enabled"] is True
    assert rep["present"] is True
    assert set(rep["channels_used"]) >= {"SSSI", "TOR", "RPM"}
    assert rep["barcode_n_bars"] >= 0
    assert rep["stalk_ok"] is True
    assert 0.0 <= rep["structure_score"] <= 1.0


def test_shock_exceedance_with_micropulse():
    surface = parse_las(LAS)
    bundle = load_micropulse_bundle(FIX)
    joined = join_surface_micropulse(surface, bundle)
    shock = shock_exceedance(joined["channels"])
    assert shock["present"] is True
    assert shock["channel"] is not None
    assert shock["n_samples"] > 0
    assert shock["n_exceed"] >= 0

    rep = evaluate_regime(
        joined,
        regime_mode="persist_h0",
        enabled=True,
    )
    assert rep["shock"]["present"] is True
    assert int(rep["shock_exceedance"]) >= 0


def test_dual_gate_science_native_vs_scramble():
    series = parse_las(LAS)
    annex = dual_gate_windows(series, window_scale=1, seed=7, pin_ok=True)
    assert annex["enabled"] is True
    assert annex["kind"] == "dual_gate_windows"
    assert annex["informational_only"] is True
    assert annex["decoy"]["kind"] == "time_scramble"
    assert "native_score" in annex
    assert "decoy_score" in annex
    assert isinstance(annex["native_beats_decoy"], bool)
    assert annex["channels_used"]


def test_evaluate_science_off_by_default():
    series = parse_las(LAS)
    rep = evaluate_science(series, with_science=False, regime_mode="off")
    assert rep["enabled"] is False


def test_evaluate_science_on_flag():
    series = parse_las(LAS)
    rep = evaluate_science(series, with_science=True, regime_mode="off", seed=1)
    assert rep["enabled"] is True
    assert rep["native_score"] is not None


def test_is_solved_independent_of_science_score():
    thr = JobThresholds(require_regime=False)
    params = FreeParams(regime_mode="off")
    good = Observations(
        pin_ok=True,
        n_rows=20,
        n_channels=6,
        n_required=3,
        n_required_present=3,
        export_ok_fraction=1.0,
        verify_ok=True,
        align_score=1.0,
        physics_n_ok=4,
        physics_n_warn=0,
        physics_n_fail=0,
        depth_mono_ok=True,
        unit_sanity_ok=True,
        out_dir="/tmp",
        science_enabled=True,
        science_native_score=0.0,
        science_decoy_score=1.0,
        science_native_beats_decoy=False,
        regime_enabled=True,
        regime_structure_score=0.0,
    )
    assert is_solved(good, thr, params) is True


def test_is_solved_require_regime_gates():
    thr = JobThresholds(require_regime=True)
    good_base = dict(
        pin_ok=True,
        n_rows=20,
        n_channels=6,
        n_required=3,
        n_required_present=3,
        export_ok_fraction=1.0,
        verify_ok=True,
        align_score=1.0,
        physics_n_ok=4,
        physics_n_warn=0,
        physics_n_fail=0,
        depth_mono_ok=True,
        unit_sanity_ok=True,
        out_dir="/tmp",
        regime_present=True,
        regime_stalk_ok=True,
    )
    # mode off → not solved under require_regime
    assert (
        is_solved(
            Observations(**good_base),
            thr,
            FreeParams(regime_mode="off"),
        )
        is False
    )
    # mode on + stalk_ok → solved
    assert (
        is_solved(
            Observations(**good_base, regime_enabled=True),
            thr,
            FreeParams(regime_mode="persist_h0"),
        )
        is True
    )
    # stalk fail → not solved
    bad = dict(good_base, regime_stalk_ok=False, regime_enabled=True)
    assert (
        is_solved(
            Observations(**bad),
            thr,
            FreeParams(regime_mode="persist_h0"),
        )
        is False
    )


def test_propose_enable_regime_on_require():
    thr = JobThresholds(require_regime=True)
    params = FreeParams(regime_mode="off")
    obs = Observations(
        pin_ok=True,
        n_rows=20,
        n_channels=6,
        n_required=3,
        n_required_present=3,
        export_ok_fraction=1.0,
        verify_ok=True,
        align_score=1.0,
        physics_n_ok=4,
        physics_n_warn=0,
        physics_n_fail=0,
        depth_mono_ok=True,
        unit_sanity_ok=True,
        out_dir="/tmp",
        regime_enabled=True,
        regime_present=True,
        regime_stalk_ok=False,
    )
    props = collect_section_proposals(obs, params, thr, tried=set())
    assert any(
        pr.section == "regime" and pr.params.regime_mode == "persist_h0" for pr in props
    )


def test_propose_window_scale_for_vacuous_barcode():
    thr = JobThresholds()
    params = FreeParams(regime_mode="persist_h0", window_scale=1)
    obs = Observations(
        pin_ok=True,
        n_rows=20,
        n_channels=6,
        n_required=3,
        n_required_present=3,
        export_ok_fraction=1.0,
        verify_ok=True,
        align_score=1.0,
        physics_n_ok=4,
        physics_n_warn=0,
        physics_n_fail=0,
        depth_mono_ok=True,
        unit_sanity_ok=True,
        out_dir="/tmp",
        regime_enabled=True,
        regime_present=True,
        regime_stalk_ok=True,
        regime_barcode_n_bars=0,
    )
    props = collect_section_proposals(obs, params, thr, tried=set())
    assert any(
        pr.section == "regime" and pr.params.window_scale > 1 for pr in props
    )


def test_loop_solved_without_require_regime_writes_reports(tmp_path):
    out = tmp_path / "job_os_regime"
    result = run_job_coherence_loop(
        las_path=LAS,
        out_root=out,
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_full",
            regime_mode="persist_h0",
            window_scale=1,
        ),
        thresholds=JobThresholds(require_regime=False),
        max_rounds=3,
        stability_k=1,
        os_mode=True,
        run_id="regime_info",
        with_regime=True,
        with_science=True,
    )
    assert result["solved"] is True
    run_dir = Path(result["out_root"])
    cycle = run_dir / "cycle_01"
    assert (cycle / "regime_report.json").is_file()
    assert (cycle / "science_annex.json").is_file()
    regime = json.loads((cycle / "regime_report.json").read_text(encoding="utf-8"))
    science = json.loads((cycle / "science_annex.json").read_text(encoding="utf-8"))
    assert regime["enabled"] is True
    assert regime["present"] is True
    assert "SSSI" in regime["channels_used"] or regime["channels_used"]
    assert science["enabled"] is True
    assert science["informational_only"] is True
    assert science["kind"] == "dual_gate_windows"
    assert "native_score" in science
    assert "decoy_score" in science
    # SOLVED independent of whether native beats decoy
    assert result["solved"] is True


def test_loop_require_regime_enables_mode(tmp_path):
    out = tmp_path / "job_os_req_regime"
    result = run_job_coherence_loop(
        las_path=LAS,
        out_root=out,
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_full",
            regime_mode="off",
        ),
        thresholds=JobThresholds(require_regime=True),
        max_rounds=4,
        stability_k=1,
        os_mode=True,
        run_id="req_regime",
        with_regime=True,
    )
    assert result["solved"] is True
    assert result["final_params"]["regime_mode"] in (
        "persist_h0",
        "dual_gate_windows",
    )


def test_loop_science_does_not_block_solved(tmp_path):
    """with-science + decoy ranking never prevents SOLVED when regime not required."""
    out = tmp_path / "job_os_sci_indep"
    result = run_job_coherence_loop(
        las_path=LAS,
        out_root=out,
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_min",
            regime_mode="off",
        ),
        thresholds=JobThresholds(require_regime=False),
        max_rounds=2,
        stability_k=1,
        os_mode=True,
        run_id="sci_indep",
        with_science=True,
    )
    assert result["solved"] is True
    run_dir = Path(result["out_root"])
    annex = run_dir / "cycle_01" / "science_annex.json"
    assert annex.is_file()
    body = json.loads(annex.read_text(encoding="utf-8"))
    assert body["informational_only"] is True


def test_observe_wires_regime_fields():
    series = parse_las(LAS)
    thr = JobThresholds()
    params = FreeParams(regime_mode="persist_h0", channel_pack="surface_full")
    obs = observe_job(
        series=series,
        params=params,
        thr=thr,
        with_regime=True,
        with_science=True,
    )
    assert obs.regime_enabled is True
    assert obs.regime_present is True
    assert obs.science_enabled is True
    assert obs.science_native_score is not None
    assert obs.science_decoy_score is not None


def test_cli_with_regime_science(tmp_path):
    out = tmp_path / "cli_regime"
    cmd = [
        sys.executable,
        str(ROOT / "job_coherence.py"),
        "--os",
        "--las",
        str(LAS),
        "--channel-pack",
        "surface_full",
        "--regime-mode",
        "persist_h0",
        "--with-regime",
        "--with-science",
        "--out-dir",
        str(out),
        "--run-id",
        "cli_reg",
        "--max-rounds",
        "2",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["solved"] is True
    run_dir = Path(payload["out"])
    assert (run_dir / "cycle_01" / "regime_report.json").is_file()
    assert (run_dir / "cycle_01" / "science_annex.json").is_file()


def test_structure_score_bounded():
    s = structure_score(
        {
            "SSSI": {
                "n_windows": 2,
                "barcode_n_bars": 4,
                "total_persistence": 8.0,
            }
        }
    )
    assert 0.0 <= s <= 1.0
