"""Job Coherence OS P3 survey stalk tests (QC, holonomy, require-survey)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.observe import is_solved, observe_job
from realm.job_os.pin import verify_job_pin
from realm.job_os.propose import collect_section_proposals, merge_proposals
from realm.job_os.survey import (
    discrete_holonomy_defects,
    evaluate_survey,
    parse_survey_csv,
    qc_survey_stations,
)
from realm.job_os.types import FreeParams, JobThresholds, Observations
from realm.job_os.ingest_las import parse_las

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LAS = FIXTURES / "mini_edr.las"
SURVEY = FIXTURES / "mini_survey.csv"


def test_mini_survey_fixture_exists():
    assert SURVEY.is_file()
    assert LAS.is_file()


def test_parse_mini_survey_csv():
    table = parse_survey_csv(SURVEY)
    assert table["n_stations"] == 10
    assert table["stations"][0]["md"] == pytest.approx(1000.0)
    assert table["stations"][0]["inc"] == pytest.approx(1.20)
    assert table["stations"][0]["azi"] == pytest.approx(45.00)
    assert table["stations"][0]["magf"] == pytest.approx(0.48)
    assert table["stations"][0]["total_g"] == pytest.approx(0.999)
    # Never invent: last station has real values only
    last = table["stations"][-1]
    assert last["inc"] is not None
    assert last["md"] == pytest.approx(1090.0)


def test_qc_survey_passes_on_fixture():
    table = parse_survey_csv(SURVEY)
    qc = qc_survey_stations(table["stations"])
    assert qc["n_stations"] == 10
    assert qc["qc_fail_count"] == 0
    assert qc["qc_ok"] is True
    assert qc["max_abs_g_minus_1"] is not None
    assert qc["max_abs_g_minus_1"] < 0.05


def test_qc_survey_flags_bad_total_g(tmp_path: Path):
    bad = tmp_path / "bad_g.csv"
    bad.write_text(
        "MD,Inc,Azi,MagF,Total_G\n"
        "1000.0,1.0,10.0,0.48,0.999\n"
        "1010.0,2.0,12.0,0.48,1.50\n",  # |G-1|=0.5 → fail
        encoding="utf-8",
    )
    table = parse_survey_csv(bad)
    qc = qc_survey_stations(table["stations"])
    assert qc["qc_fail_count"] >= 1
    assert qc["qc_ok"] is False


def test_qc_survey_flags_bad_magf(tmp_path: Path):
    bad = tmp_path / "bad_magf.csv"
    bad.write_text(
        "MD,Inc,Azi,MagF,Total_G\n"
        "1000.0,1.0,10.0,0.48,0.999\n"
        "1010.0,2.0,12.0,5.00,1.000\n",  # MagF out of band
        encoding="utf-8",
    )
    table = parse_survey_csv(bad)
    qc = qc_survey_stations(table["stations"])
    assert qc["qc_fail_count"] >= 1
    assert any("magf" in r for r in qc["fail_reasons"])


def test_holonomy_clean_on_fixture():
    table = parse_survey_csv(SURVEY)
    hol = discrete_holonomy_defects(table["stations"])
    assert hol["defect_count"] == 0
    assert hol["holonomy_ok"] is True
    assert hol["n_pairs_checked"] >= 1
    assert hol["order"] == "md"


def test_holonomy_flags_inc_jump(tmp_path: Path):
    jagged = tmp_path / "jagged.csv"
    jagged.write_text(
        "MD,Inc,Azi,MagF,Total_G\n"
        "1000.0,1.0,10.0,0.48,0.999\n"
        "1010.0,50.0,12.0,0.48,1.000\n",  # ΔInc=49° → defect
        encoding="utf-8",
    )
    table = parse_survey_csv(jagged)
    hol = discrete_holonomy_defects(table["stations"], dinc_jump_deg=30.0)
    assert hol["defect_count"] >= 1
    assert hol["holonomy_ok"] is False


def test_never_invents_missing_inc_azi(tmp_path: Path):
    sparse = tmp_path / "sparse.csv"
    sparse.write_text(
        "MD,Inc,Azi,MagF,Total_G\n"
        "1000.0,1.0,10.0,0.48,0.999\n"
        "1010.0,,,0.48,1.000\n"  # missing Inc/Azi
        "1020.0,3.0,15.0,0.49,0.998\n",
        encoding="utf-8",
    )
    table = parse_survey_csv(sparse)
    assert table["n_stations"] == 3
    mid = table["stations"][1]
    assert mid["inc"] is None
    assert mid["azi"] is None
    # holonomy skips incomplete frames — does not invent
    hol = discrete_holonomy_defects(table["stations"])
    assert hol["n_pairs_checked"] >= 0
    for d in hol["defects"]:
        assert "invent" not in str(d).lower()


def test_evaluate_survey_gate_off_always_stalk_ok_when_missing():
    rep = evaluate_survey(None, survey_gate="off")
    assert rep["present"] is False
    assert rep["stalk_ok"] is True


def test_evaluate_survey_gate_qc_only_requires_stations():
    rep = evaluate_survey(None, survey_gate="qc_only")
    assert rep["present"] is False
    assert rep["stalk_ok"] is False


def test_evaluate_survey_holonomy_on_fixture():
    table = parse_survey_csv(SURVEY)
    rep = evaluate_survey(table, survey_gate="holonomy")
    assert rep["present"] is True
    assert rep["qc_ok"] is True
    assert rep["holonomy_ok"] is True
    assert rep["stalk_ok"] is True
    assert rep["defect_count"] == 0


def test_is_solved_require_survey_missing_stations():
    thr = JobThresholds(require_survey=True)
    params = FreeParams(survey_gate="qc_only", align_mode="depth_primary")
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
        survey_present=False,
        survey_n_stations=0,
        survey_stalk_ok=False,
    )
    assert is_solved(obs, thr, params) is False


def test_is_solved_require_survey_gate_off_not_solved():
    thr = JobThresholds(require_survey=True)
    params = FreeParams(survey_gate="off", align_mode="depth_primary")
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
        survey_present=True,
        survey_n_stations=10,
        survey_qc_ok=True,
        survey_stalk_ok=True,  # gate off → stalk_ok True but require_survey blocks gate off
    )
    assert is_solved(obs, thr, params) is False


def test_is_solved_require_survey_qc_ok():
    thr = JobThresholds(require_survey=True)
    params = FreeParams(survey_gate="qc_only", align_mode="depth_primary")
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
        survey_present=True,
        survey_n_stations=10,
        survey_qc_ok=True,
        survey_stalk_ok=True,
        survey_holonomy_ok=True,
        survey_defect_count=0,
    )
    assert is_solved(obs, thr, params) is True


def test_propose_require_survey_enables_qc_gate():
    thr = JobThresholds(require_survey=True)
    params = FreeParams(
        align_mode="depth_primary",
        channel_pack="surface_min",
        survey_gate="off",
    )
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
        survey_present=True,
        survey_n_stations=10,
        survey_stalk_ok=True,
    )
    props = collect_section_proposals(obs, params, thr, tried=set())
    sections = {p.section for p in props}
    assert "survey" in sections
    nxt, reason, board = merge_proposals(props, params)
    assert nxt is not None
    assert nxt.survey_gate == "qc_only"
    assert "survey" in reason


def test_propose_survey_anchor_when_present_glue_weak():
    thr = JobThresholds(min_align_score=0.5)
    params = FreeParams(
        align_mode="depth_primary",
        channel_pack="surface_min",
        survey_gate="off",
    )
    obs = Observations(
        pin_ok=True,
        n_rows=20,
        n_channels=6,
        n_required=3,
        n_required_present=3,
        export_ok_fraction=1.0,
        verify_ok=True,
        align_score=0.2,
        physics_n_ok=4,
        physics_n_warn=0,
        physics_n_fail=0,
        depth_mono_ok=True,
        unit_sanity_ok=True,
        out_dir="/tmp",
        notes=["align_weak"],
        survey_present=True,
        survey_n_stations=10,
        survey_stalk_ok=True,
        survey_qc_ok=True,
    )
    props = collect_section_proposals(obs, params, thr, tried=set())
    survey_props = [p for p in props if p.section == "survey"]
    assert survey_props
    assert any(p.params.align_mode == "survey_anchor" for p in survey_props)


def test_propose_mark_only_on_bad_stations():
    thr = JobThresholds()
    params = FreeParams(
        align_mode="depth_primary",
        null_policy="drop",
        survey_gate="qc_only",
    )
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
        survey_present=True,
        survey_n_stations=5,
        survey_qc_fail=2,
        survey_qc_ok=False,
        survey_stalk_ok=False,
    )
    props = collect_section_proposals(obs, params, thr, tried=set())
    assert any(
        p.section == "survey" and p.params.null_policy == "mark_only" for p in props
    )


def test_observe_with_survey_fixture():
    series = parse_las(LAS)
    table = parse_survey_csv(SURVEY)
    params = FreeParams(
        align_mode="depth_primary",
        channel_pack="surface_min",
        survey_gate="qc_only",
    )
    thr = JobThresholds(require_survey=True)
    pin = verify_job_pin(series, pack="surface_min")
    obs = observe_job(
        series=series,
        params=params,
        thr=thr,
        out_dir="/x",
        pin=pin,
        survey=table,
    )
    assert obs.survey_present is True
    assert obs.survey_n_stations == 10
    assert obs.survey_qc_fail == 0
    assert obs.survey_stalk_ok is True
    assert is_solved(obs, thr, params) is True


def test_loop_require_survey_without_survey_not_solved(tmp_path: Path):
    result = run_job_coherence_loop(
        las_path=LAS,
        out_root=tmp_path / "job_os_no_sv",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_min",
            survey_gate="off",
        ),
        thresholds=JobThresholds(require_survey=True),
        max_rounds=4,
        stability_k=1,
        os_mode=True,
        run_id="no_survey",
    )
    assert result["solved"] is False
    # should have negotiated gate to qc_only then stuck (no stations)
    final = result["final_params"]
    assert final["survey_gate"] in ("qc_only", "off", "holonomy")


def test_loop_require_survey_with_fixture_solves(tmp_path: Path):
    result = run_job_coherence_loop(
        las_path=LAS,
        survey_path=SURVEY,
        out_root=tmp_path / "job_os_sv",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_min",
            survey_gate="off",
        ),
        thresholds=JobThresholds(require_survey=True),
        max_rounds=6,
        stability_k=1,
        os_mode=True,
        run_id="with_survey",
    )
    assert result["solved"] is True
    assert result["survey_n_stations"] == 10
    assert result["final_params"]["survey_gate"] != "off"
    run_dir = Path(result["out_root"])
    assert (run_dir / "cycle_01" / "survey_report.json").is_file()
    report = json.loads(
        (run_dir / "cycle_01" / "survey_report.json").read_text(encoding="utf-8")
    )
    assert report["n_stations"] == 10
    recipe = json.loads((run_dir / "PARTNER_RECIPE.json").read_text(encoding="utf-8"))
    assert "survey_gate" in recipe["free_params"]
    assert recipe.get("require_survey") is True


def test_loop_holonomy_gate_on_fixture(tmp_path: Path):
    result = run_job_coherence_loop(
        las_path=LAS,
        survey_path=SURVEY,
        out_root=tmp_path / "job_os_hol",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_min",
            survey_gate="holonomy",
        ),
        thresholds=JobThresholds(require_survey=True),
        max_rounds=4,
        stability_k=1,
        os_mode=True,
        run_id="holonomy_ok",
    )
    assert result["solved"] is True
    assert result["final_params"]["survey_gate"] == "holonomy"


def test_loop_holonomy_fails_on_jagged(tmp_path: Path):
    jagged = tmp_path / "jagged.csv"
    jagged.write_text(
        "MD,Inc,Azi,MagF,Total_G\n"
        "1000.0,1.0,10.0,0.48,0.999\n"
        "1010.0,55.0,12.0,0.48,1.000\n"
        "1020.0,56.0,14.0,0.49,0.998\n",
        encoding="utf-8",
    )
    result = run_job_coherence_loop(
        las_path=LAS,
        survey_path=jagged,
        out_root=tmp_path / "job_os_jag",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_min",
            survey_gate="holonomy",
        ),
        thresholds=JobThresholds(require_survey=True),
        max_rounds=3,
        stability_k=1,
        os_mode=True,
        run_id="holonomy_fail",
    )
    assert result["solved"] is False


def test_loop_without_require_survey_still_solves_las_only(tmp_path: Path):
    """P1 path: no survey required → LAS-only still solves (prior tests green)."""
    result = run_job_coherence_loop(
        las_path=LAS,
        out_root=tmp_path / "job_os_p1",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_min",
            survey_gate="off",
        ),
        thresholds=JobThresholds(require_survey=False),
        max_rounds=3,
        stability_k=1,
        os_mode=True,
        run_id="las_only",
    )
    assert result["solved"] is True


def test_cli_require_survey_and_survey_gate(tmp_path: Path):
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    cli = str(root / "job_coherence.py")
    out = tmp_path / "cli_sv"
    proc = subprocess.run(
        [
            sys.executable,
            cli,
            "--os",
            "--las",
            str(LAS),
            "--survey",
            str(SURVEY),
            "--require-survey",
            "--survey-gate",
            "qc_only",
            "--out-dir",
            str(out),
            "--run-id",
            "cli_survey",
        ],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(proc.stdout)
    assert data["solved"] is True
    assert data["survey_n_stations"] == 10
    assert data["final_params"]["survey_gate"] == "qc_only"


def test_micropulse_survey_format_parse(tmp_path: Path):
    """MicroPulse-like SURVEY header with unit line."""
    mp = tmp_path / "MicroPulse_799_SURVEY_fixture.csv"
    mp.write_text(
        "\n".join(
            [
                "MicroPulse",
                "Survey Log",
                "Tool Serial Number:, 799",
                "Time, Inclination, Azimuth, MagF, Total Grav",
                "MM/dd/yyyy hh:mm:ss, Degrees, Degrees, Gauss, G",
                "07/14/2025 21:56:15,1.20,45.00,0.48,0.999",
                "07/14/2025 21:59:18,2.10,46.50,0.48,1.001",
                "07/14/2025 22:01:17,3.00,48.00,0.49,0.998",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    table = parse_survey_csv(mp)
    assert table["n_stations"] == 3
    assert table["stations"][0]["inc"] == pytest.approx(1.20)
    assert table["stations"][0]["total_g"] == pytest.approx(0.999)
    rep = evaluate_survey(table, survey_gate="qc_only")
    assert rep["qc_ok"] is True
    assert rep["stalk_ok"] is True
