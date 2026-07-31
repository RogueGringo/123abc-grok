"""Job Coherence OS P2: MicroPulse fiber join, channel pack, structural glue."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from realm.job_os.glue import compute_glue
from realm.job_os.ingest_las import parse_las, select_channel_pack
from realm.job_os.ingest_micropulse import (
    join_surface_micropulse,
    load_micropulse_bundle,
    parse_micropulse_csv,
)
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.observe import is_solved, observe_job
from realm.job_os.pin import verify_job_pin
from realm.job_os.propose import collect_section_proposals, merge_proposals, negotiate
from realm.job_os.types import FreeParams, JobThresholds, Observations, PACK_REQUIRED

FIX = Path(__file__).resolve().parent / "fixtures"
LAS = FIX / "mini_edr.las"
MP_GAMMA = FIX / "mini_micropulse_GAMMA.csv"
MP_SHOCK = FIX / "mini_micropulse_SHOCK.csv"
MP_VIBE = FIX / "mini_micropulse_VIBE.csv"
MP_TEMP = FIX / "mini_micropulse_TEMP.csv"


def test_fixtures_exist():
    assert LAS.is_file()
    assert MP_GAMMA.is_file()
    assert MP_SHOCK.is_file()
    assert MP_VIBE.is_file()
    assert MP_TEMP.is_file()


def test_parse_micropulse_gamma_header_skip():
    fiber = parse_micropulse_csv(MP_GAMMA)
    assert fiber["kind"] == "GAMMA"
    assert fiber["n_rows"] == 10
    assert fiber["time_key"] in ("RTC_TIME", "TIME")
    assert sum(1 for t in fiber["times"] if t is not None) == 10
    assert "GAMMA" in fiber["channels"] or "GAMMA1" in fiber["channels"]
    # fixture includes DEPT for depth-domain glue
    assert fiber.get("depth_key") == "DEPT"
    assert sum(1 for d in fiber["depths"] if d is not None) == 10


def test_parse_micropulse_shock_and_vibe():
    shock = parse_micropulse_csv(MP_SHOCK)
    assert shock["kind"] == "SHOCK"
    assert shock["n_rows"] >= 5
    assert "SHOCK" in shock["channels"]
    vibe = parse_micropulse_csv(MP_VIBE)
    assert vibe["kind"] == "VIBE"
    assert "VIBE" in vibe["channels"]


def test_parse_micropulse_temp_unit_line_skip():
    """TEMP files have a unit row after header — must not become data."""
    fiber = parse_micropulse_csv(MP_TEMP)
    assert fiber["kind"] == "TEMP"
    assert fiber["n_rows"] == 4
    assert "TEMP" in fiber["channels"]
    # first temp value should be ~33.54 not a parse of "Celcius"
    temps = [x for x in fiber["channels"]["TEMP"] if x is not None]
    assert temps[0] == pytest.approx(33.54, rel=1e-3)


def test_load_bundle_from_dir():
    bundle = load_micropulse_bundle(FIX)
    assert bundle["n_fibers"] >= 3
    kinds = set(bundle["kinds"])
    assert "GAMMA" in kinds
    assert "SHOCK" in kinds
    assert "VIBE" in kinds
    assert "GAMMA" in bundle["pack_channels"]
    assert "SHOCK" in bundle["pack_channels"]
    assert "VIBE" in bundle["pack_channels"]
    assert len(bundle["times_union"]) > 0


def test_load_bundle_single_file():
    bundle = load_micropulse_bundle(MP_GAMMA)
    assert bundle["n_fibers"] == 1
    assert "GAMMA" in bundle["kinds"]


def test_join_surface_micropulse_promotes_pack_channels():
    surface = parse_las(LAS)
    bundle = load_micropulse_bundle(FIX)
    joined = join_surface_micropulse(surface, bundle)
    assert joined["has_micropulse"] is True
    ch = joined["channels"]
    assert "GAMMA" in ch
    assert "SHOCK" in ch
    assert "VIBE" in ch
    assert "WOB" in ch  # surface preserved
    assert joined["micropulse"]["n_fibers"] >= 3


def test_pack_required_mwd_and_job_union_include_downhole():
    assert "GAMMA" in PACK_REQUIRED["mwd_full"]
    assert "GAMMA" in PACK_REQUIRED["job_union"]
    assert "SHOCK" in PACK_REQUIRED["job_union"]
    assert "VIBE" in PACK_REQUIRED["job_union"]
    # surface packs stay surface-only
    assert "GAMMA" not in PACK_REQUIRED["surface_min"]
    assert "GAMMA" not in PACK_REQUIRED["surface_full"]


def test_pin_mwd_full_needs_gamma_join():
    surface = parse_las(LAS)
    pin_no_mp = verify_job_pin(surface, pack="mwd_full")
    assert pin_no_mp["ok"] is False
    assert "GAMMA" in pin_no_mp["missing_channels"]

    bundle = load_micropulse_bundle(FIX)
    joined = join_surface_micropulse(surface, bundle)
    pin = verify_job_pin(joined, pack="mwd_full")
    assert pin["ok"] is True
    assert "GAMMA" in pin["present_channels"]


def test_pin_job_union_needs_gamma_shock_vibe():
    surface = parse_las(LAS)
    bundle = load_micropulse_bundle(FIX)
    joined = join_surface_micropulse(surface, bundle)
    pin = verify_job_pin(joined, pack="job_union")
    assert pin["ok"] is True
    for ch in ("GAMMA", "SHOCK", "VIBE", "SSSI"):
        assert ch in pin["present_channels"]


def test_glue_depth_proximity_with_fixture_depths():
    surface = parse_las(LAS)
    bundle = load_micropulse_bundle(FIX)
    glue = compute_glue(surface, bundle, align_mode="depth_primary")
    assert glue["multi_source"] is True
    assert glue["has_micropulse"] is True
    assert glue["has_depth_domain"] is True
    assert glue["score"] >= 0.5
    assert glue["method"] == "depth_proximity"
    assert "glue_incomplete" not in glue["notes"]


def test_glue_single_source_no_mp():
    surface = parse_las(LAS)
    glue = compute_glue(surface, None, align_mode="depth_primary")
    assert glue["multi_source"] is False
    assert glue["score"] == pytest.approx(1.0)


def test_glue_incomplete_proposes_align_free_params():
    """When multi-source glue is weak, align section proposes free moves (not pin)."""
    thr = JobThresholds(min_align_score=0.5)
    params = FreeParams(
        align_mode="depth_primary",
        channel_pack="mwd_full",
        null_policy="mark_only",
    )
    obs = Observations(
        pin_ok=True,
        n_rows=20,
        n_channels=8,
        n_required=6,
        n_required_present=6,
        export_ok_fraction=1.0,
        verify_ok=True,
        align_score=0.3,
        physics_n_ok=3,
        physics_n_warn=0,
        physics_n_fail=0,
        depth_mono_ok=True,
        unit_sanity_ok=True,
        out_dir="/tmp",
        notes=["align_weak", "glue_incomplete"],
        has_micropulse=True,
        glue_score=0.3,
        glue_method="structural_fiber_join",
        mp_n_fibers=1,
        glue_notes=["glue_incomplete", "no_shared_depth_or_time_axis"],
    )
    props = collect_section_proposals(obs, params, thr, tried=set())
    assert props
    sections = {p.section for p in props}
    assert "align" in sections
    nxt, reason, board = merge_proposals(props, params)
    assert nxt is not None
    # Prefer time_primary or hold_last — never pin fields
    assert nxt.align_mode in ("time_primary", "depth_primary")
    blob = json.dumps(nxt.to_dict())
    assert "depth_mono_eps" not in blob


def test_observe_joined_series_mwd_full():
    surface = parse_las(LAS)
    bundle = load_micropulse_bundle(FIX)
    joined = join_surface_micropulse(surface, bundle)
    joined = select_channel_pack(joined, "mwd_full")
    params = FreeParams(channel_pack="mwd_full", align_mode="depth_primary")
    thr = JobThresholds()
    pin = verify_job_pin(joined, pack="mwd_full")
    glue = compute_glue(joined, bundle, align_mode="depth_primary")
    obs = observe_job(
        series=joined, params=params, thr=thr, out_dir="/x", pin=pin, glue=glue
    )
    assert obs.pin_ok
    assert obs.has_micropulse
    assert obs.glue_score >= 0.5
    assert obs.export_ok_fraction == pytest.approx(1.0)
    assert is_solved(obs, thr, params)


def test_os_loop_mwd_full_with_micropulse_solves(tmp_path: Path):
    result = run_job_coherence_loop(
        las_path=LAS,
        micropulse_path=FIX,
        out_root=tmp_path / "job_os_mp",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="mwd_full",
            null_policy="mark_only",
        ),
        thresholds=JobThresholds(),
        max_rounds=4,
        stability_k=1,
        os_mode=True,
        run_id="test_mp_mwd",
    )
    assert result["solved"] is True
    assert result["micropulse_n_fibers"] >= 3
    assert "GAMMA" in (result.get("micropulse_kinds") or [])
    run_dir = Path(result["out_root"])
    assert (run_dir / "PARTNER_RECIPE.json").is_file()
    recipe = json.loads((run_dir / "PARTNER_RECIPE.json").read_text(encoding="utf-8"))
    assert recipe.get("micropulse_path")
    # cycle wrote glue.json
    glue_path = run_dir / "cycle_01" / "glue.json"
    assert glue_path.is_file()
    glue = json.loads(glue_path.read_text(encoding="utf-8"))
    assert glue["multi_source"] is True


def test_os_loop_job_union_with_micropulse_solves(tmp_path: Path):
    result = run_job_coherence_loop(
        las_path=LAS,
        micropulse_path=FIX,
        out_root=tmp_path / "job_os_union",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="job_union",
            null_policy="mark_only",
        ),
        thresholds=JobThresholds(),
        max_rounds=4,
        stability_k=1,
        os_mode=True,
        run_id="test_mp_union",
    )
    assert result["solved"] is True


def test_mwd_full_without_mp_narrows_to_surface(tmp_path: Path):
    """mwd_full missing GAMMA is soft pack fail → negotiate narrow (not pin abort)."""
    result = run_job_coherence_loop(
        las_path=LAS,
        micropulse_path=None,
        out_root=tmp_path / "job_os_no_mp",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="mwd_full",
            null_policy="mark_only",
        ),
        thresholds=JobThresholds(),
        max_rounds=6,
        stability_k=1,
        os_mode=True,
        run_id="test_narrow_mwd",
    )
    # Should recover via surface_min narrow
    assert result["solved"] is True
    assert result["final_params"]["channel_pack"] == "surface_min"


def test_pin_never_retuned_with_micropulse():
    thr = JobThresholds()
    params = FreeParams(channel_pack="mwd_full", align_mode="depth_primary")
    obs = Observations(
        pin_ok=False,
        n_rows=20,
        n_channels=5,
        n_required=6,
        n_required_present=5,
        export_ok_fraction=0.8,
        verify_ok=False,
        align_score=0.2,
        physics_n_ok=1,
        physics_n_warn=0,
        physics_n_fail=1,
        depth_mono_ok=False,
        unit_sanity_ok=True,
        out_dir="/tmp",
        notes=["pin_fail"],
        has_micropulse=True,
        glue_score=0.2,
    )
    nxt, reason, board = negotiate(obs, params, thr, tried=set())
    assert nxt is None
    assert "pin" in reason


def test_cli_micropulse_flag(tmp_path: Path):
    import subprocess
    import sys

    out = tmp_path / "cli_mp"
    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "job_coherence.py"),
            "--os",
            "--las",
            str(LAS),
            "--micropulse",
            str(FIX),
            "--channel-pack",
            "mwd_full",
            "--out-dir",
            str(out),
            "--stability-k",
            "1",
            "--run-id",
            "cli_mp_test",
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    body = json.loads(proc.stdout)
    assert body["solved"] is True
    assert body.get("micropulse_kinds")
