"""Job Coherence OS P1 unit tests (pin, free params, fixed-point, fixture)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from realm.job_os.ingest_las import apply_null_policy, parse_las, select_channel_pack
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.observe import coherence_score, is_solved, observe_job
from realm.job_os.pin import verify_job_pin
from realm.job_os.propose import collect_section_proposals, merge_proposals, negotiate
from realm.job_os.types import (
    PIN_FORBIDDEN_KEYS,
    FreeParams,
    JobThresholds,
    Observations,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_edr.las"


def test_fixture_exists():
    assert FIXTURE.is_file()


def test_parse_las_mini():
    series = parse_las(FIXTURE)
    assert series["n_rows"] == 20
    assert "DEPT" in series["channels"] or series["depth_key"]
    assert len(series["depths"]) == 20
    assert series["depths"][0] == pytest.approx(1000.0)
    assert series["depths"][-1] == pytest.approx(1019.0)
    for ch in ("WOB", "RPM", "TOR", "SPP", "SSSI"):
        assert ch in series["channels"]
        assert len(series["channels"][ch]) == 20


def test_free_params_clamp():
    p = FreeParams(
        align_mode="weird",
        window_scale=99,
        channel_pack="nope",
        null_policy="zzz",
        survey_gate="bad",
        regime_mode="bad",
    ).clamp()
    assert p.align_mode == "depth_primary"
    assert p.window_scale == 8
    assert p.channel_pack == "surface_min"
    assert p.null_policy == "mark_only"
    assert p.survey_gate == "off"
    assert p.regime_mode == "off"
    # bounds low
    p2 = FreeParams(window_scale=0).clamp()
    assert p2.window_scale == 1


def test_pin_ok_on_fixture():
    series = parse_las(FIXTURE)
    pin = verify_job_pin(series, pack="surface_min")
    assert pin["ok"] is True
    assert pin["depth_mono_ok"] is True
    assert pin["unit_sanity_ok"] is True
    assert not pin["missing_channels"]


def test_pin_surface_full_on_fixture():
    series = parse_las(FIXTURE)
    pin = verify_job_pin(series, pack="surface_full")
    assert pin["ok"] is True
    assert "SSSI" in pin["present_channels"] or "SSSI" not in pin["missing_channels"]


def test_pin_depth_not_monotonic():
    series = parse_las(FIXTURE)
    # Break monotonicity
    depths = list(series["depths"])
    depths[5] = depths[4] - 10.0
    series = dict(series)
    series["depths"] = depths
    series["channels"] = dict(series["channels"])
    series["channels"]["DEPT"] = depths
    pin = verify_job_pin(series, pack="surface_min")
    assert pin["ok"] is False
    assert pin["depth_mono_ok"] is False
    assert any("monotonic" in r for r in pin["reasons"])


def test_pin_missing_channel():
    series = parse_las(FIXTURE)
    series = dict(series)
    ch = dict(series["channels"])
    del ch["WOB"]
    series["channels"] = ch
    pin = verify_job_pin(series, pack="surface_min")
    assert pin["ok"] is False
    assert "WOB" in pin["missing_channels"]


def test_pin_unit_inversion():
    series = parse_las(FIXTURE)
    series = dict(series)
    series["units"] = dict(series.get("units") or {})
    series["units"]["DEPT"] = "psi"
    pin = verify_job_pin(series, pack="surface_min")
    assert pin["ok"] is False
    assert pin["unit_sanity_ok"] is False


def test_is_solved_and_score():
    thr = JobThresholds()
    params = FreeParams(align_mode="depth_primary", channel_pack="surface_min")
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
    )
    assert is_solved(good, thr, params) is True
    assert coherence_score(good, thr, params) > 0.9

    bad = Observations(
        pin_ok=False,
        n_rows=20,
        n_channels=2,
        n_required=3,
        n_required_present=1,
        export_ok_fraction=0.3,
        verify_ok=False,
        align_score=0.1,
        physics_n_ok=0,
        physics_n_warn=0,
        physics_n_fail=2,
        depth_mono_ok=False,
        unit_sanity_ok=True,
        out_dir="/tmp",
        notes=["pin_fail", "export_incomplete"],
    )
    assert is_solved(bad, thr, params) is False


def test_negotiate_never_suggests_pin_change_on_pin_fail():
    thr = JobThresholds()
    params = FreeParams()
    obs = Observations(
        pin_ok=False,
        n_rows=0,
        n_channels=0,
        n_required=3,
        n_required_present=0,
        export_ok_fraction=0.0,
        verify_ok=False,
        align_score=0.0,
        physics_n_ok=0,
        physics_n_warn=0,
        physics_n_fail=2,
        depth_mono_ok=False,
        unit_sanity_ok=False,
        out_dir="/tmp",
        notes=["pin_fail"],
    )
    nxt, reason, board = negotiate(obs, params, thr, tried=set())
    assert nxt is None
    assert "pin" in reason
    assert board == []


def test_pin_veto_proposals_never_include_pin_fields():
    thr = JobThresholds()
    params = FreeParams(align_mode="none", channel_pack="surface_min")
    obs = Observations(
        pin_ok=True,
        n_rows=20,
        n_channels=6,
        n_required=3,
        n_required_present=3,
        export_ok_fraction=1.0,
        verify_ok=True,
        align_score=0.0,  # weak align → proposals
        physics_n_ok=2,
        physics_n_warn=0,
        physics_n_fail=0,
        depth_mono_ok=True,
        unit_sanity_ok=True,
        out_dir="/tmp",
        notes=["align_weak"],
    )
    props = collect_section_proposals(obs, params, thr, tried=set())
    assert props, "expected align proposals"
    for pr in props:
        keys = set(pr.params.to_dict().keys())
        assert not (keys & PIN_FORBIDDEN_KEYS)
        # No pin threshold fields in dict values either
        blob = json.dumps(pr.to_dict())
        assert "depth_mono_eps" not in blob
        assert "soft_T" not in blob
        assert "face_weight" not in blob


def test_align_propose_from_none():
    thr = JobThresholds(min_align_score=0.5)
    params = FreeParams(align_mode="none")
    obs = Observations(
        pin_ok=True,
        n_rows=10,
        n_channels=3,
        n_required=3,
        n_required_present=3,
        export_ok_fraction=1.0,
        verify_ok=True,
        align_score=0.5,
        physics_n_ok=3,
        physics_n_warn=0,
        physics_n_fail=0,
        depth_mono_ok=True,
        unit_sanity_ok=True,
        out_dir="/tmp",
        notes=["align_weak"],
    )
    # force weak: align_score below thr
    obs.align_score = 0.2
    tried: set[str] = set()
    props = collect_section_proposals(obs, params, thr, tried=tried)
    sections = {p.section for p in props}
    assert "align" in sections
    nxt, reason, board = merge_proposals(props, params)
    assert nxt is not None
    assert nxt.align_mode == "depth_primary"


def test_multi_section_merge_priority():
    thr = JobThresholds(max_physics_fail=0)
    params = FreeParams(
        align_mode="none",
        channel_pack="job_union",
        null_policy="mark_only",
        window_scale=1,
    )
    obs = Observations(
        pin_ok=True,
        n_rows=5,
        n_channels=2,
        n_required=6,
        n_required_present=2,
        export_ok_fraction=0.3,
        verify_ok=False,
        align_score=0.2,
        physics_n_ok=0,
        physics_n_warn=0,
        physics_n_fail=1,
        depth_mono_ok=True,
        unit_sanity_ok=True,
        out_dir="/tmp",
        notes=["export_incomplete", "physics_fail", "align_weak"],
    )
    tried: set[str] = set()
    props = collect_section_proposals(obs, params, thr, tried=tried)
    sections = {p.section for p in props}
    assert sections & {"export", "align", "physics", "verify"}
    nxt, reason, board = merge_proposals(props, params)
    assert nxt is not None
    assert reason.startswith("merge[")
    # export priority beats align/physics when present
    if any(p.section == "export" for p in props):
        assert "export" in reason


def test_observe_from_fixture():
    series = parse_las(FIXTURE)
    params = FreeParams(channel_pack="surface_min", align_mode="depth_primary")
    thr = JobThresholds()
    pin = verify_job_pin(series, pack="surface_min")
    obs = observe_job(series=series, params=params, thr=thr, out_dir="/x", pin=pin)
    assert obs.pin_ok
    assert obs.n_rows == 20
    assert obs.export_ok_fraction == pytest.approx(1.0)
    assert is_solved(obs, thr, params)


def test_null_policy_hold_last():
    series = parse_las(FIXTURE)
    series = dict(series)
    ch = {k: list(v) for k, v in series["channels"].items()}
    ch["WOB"][3] = None
    series["channels"] = ch
    out = apply_null_policy(series, "hold_last")
    assert out["channels"]["WOB"][3] is not None
    assert out["channels"]["WOB"][3] == out["channels"]["WOB"][2]


def test_select_channel_pack():
    series = parse_las(FIXTURE)
    packed = select_channel_pack(series, "surface_min")
    keys = set(packed["channels"].keys())
    assert "WOB" in keys
    assert "RPM" in keys
    # TOR not required for surface_min filter
    assert "TOR" not in keys or "TOR" in keys  # filter may drop TOR
    assert "TOR" not in keys


def test_fixed_point_k1_with_fixture(tmp_path: Path):
    result = run_job_coherence_loop(
        las_path=FIXTURE,
        out_root=tmp_path / "job_os",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_min",
            null_policy="mark_only",
            window_scale=1,
        ),
        thresholds=JobThresholds(),
        max_rounds=4,
        stability_k=1,
        os_mode=True,
        run_id="test_fixed_k1",
    )
    assert result["solved"] is True
    assert result["stop_reason"] == "coherent"
    assert result["os_mode"] is True
    run_dir = Path(result["out_root"])
    assert (run_dir / "RUN.json").is_file()
    assert (run_dir / "ledger.jsonl").is_file()
    assert (run_dir / "PARTNER_RECIPE.json").is_file()
    assert (run_dir / "COHERENCE.json").is_file()
    recipe = json.loads((run_dir / "PARTNER_RECIPE.json").read_text(encoding="utf-8"))
    assert recipe["solved"] is True
    assert "align_mode" in recipe["free_params"]
    assert "depth_mono_eps" not in recipe["free_params"]
    run_doc = json.loads((run_dir / "RUN.json").read_text(encoding="utf-8"))
    assert run_doc["status"] == "solved"
    # LATEST pointer
    assert (tmp_path / "job_os" / "LATEST").is_file()


def test_negotiate_toward_solved_from_align_none(tmp_path: Path):
    """Start with align_mode=none may still solve (score 0.5 == thr) or negotiate."""
    result = run_job_coherence_loop(
        las_path=FIXTURE,
        out_root=tmp_path / "job_os2",
        initial=FreeParams(
            align_mode="none",
            channel_pack="surface_min",
            null_policy="mark_only",
        ),
        thresholds=JobThresholds(min_align_score=0.5),
        max_rounds=5,
        stability_k=1,
        os_mode=True,
        run_id="test_align_none",
    )
    # align none gives 0.5 which equals min_align_score → solved
    assert result["solved"] is True


def test_resume_already_solved(tmp_path: Path):
    out = tmp_path / "job_os_r"
    r1 = run_job_coherence_loop(
        las_path=FIXTURE,
        out_root=out,
        initial=FreeParams(channel_pack="surface_min", align_mode="depth_primary"),
        max_rounds=3,
        stability_k=1,
        os_mode=True,
        run_id="resume_me",
    )
    assert r1["solved"]
    run_dir = Path(r1["out_root"])
    r2 = run_job_coherence_loop(
        out_root=out,
        resume_dir=run_dir,
        max_rounds=3,
        stability_k=1,
        os_mode=True,
    )
    assert r2["solved"] is True


def test_export_prefers_narrow_not_broaden_when_channels_missing():
    """Missing required pack channels → first merge is surface_min, not richer pack."""
    thr = JobThresholds()
    params = FreeParams(
        align_mode="depth_primary",
        channel_pack="surface_full",
        null_policy="mark_only",
    )
    # surface_full requires DEPT,WOB,RPM,TOR,SPP,SSSI — only 2 present
    obs = Observations(
        pin_ok=False,  # soft pack fail
        n_rows=20,
        n_channels=2,
        n_required=6,
        n_required_present=2,
        export_ok_fraction=2.0 / 6.0,
        verify_ok=False,
        align_score=1.0,
        physics_n_ok=1,
        physics_n_warn=0,
        physics_n_fail=1,
        depth_mono_ok=True,
        unit_sanity_ok=True,
        out_dir="/tmp",
        notes=["export_incomplete", "pin_fail"],
    )
    tried: set[str] = set()
    props = collect_section_proposals(obs, params, thr, tried=tried)
    assert props
    nxt, reason, board = merge_proposals(props, params)
    assert nxt is not None
    assert nxt.channel_pack == "surface_min", (
        f"expected narrow to surface_min first, got {nxt.channel_pack} reason={reason}"
    )
    assert "narrow" in reason or "surface_min" in reason
    # No broaden winner at equal/higher precedence
    richer = {"mwd_full", "job_union", "surface_full"}
    assert nxt.channel_pack not in richer


def test_negotiate_soft_pack_fail_allows_pack_move():
    """Missing channels only (hard pin ok) may negotiate channel_pack."""
    thr = JobThresholds()
    params = FreeParams(channel_pack="surface_full")
    obs = Observations(
        pin_ok=False,
        n_rows=20,
        n_channels=3,
        n_required=6,
        n_required_present=3,
        export_ok_fraction=0.5,
        verify_ok=False,
        align_score=1.0,
        physics_n_ok=2,
        physics_n_warn=0,
        physics_n_fail=1,
        depth_mono_ok=True,
        unit_sanity_ok=True,
        out_dir="/tmp",
        notes=["export_incomplete"],
    )
    nxt, reason, board = negotiate(obs, params, thr, tried=set())
    assert nxt is not None
    assert nxt.channel_pack == "surface_min"
    assert reason != "pin_locked_fail_cannot_negotiate"


def test_no_window_scale_proposals_in_p1():
    thr = JobThresholds(max_physics_fail=0)
    params = FreeParams(window_scale=1, null_policy="mark_only")
    obs = Observations(
        pin_ok=True,
        n_rows=10,
        n_channels=3,
        n_required=3,
        n_required_present=3,
        export_ok_fraction=1.0,
        verify_ok=True,
        align_score=1.0,
        physics_n_ok=0,
        physics_n_warn=0,
        physics_n_fail=2,
        depth_mono_ok=True,
        unit_sanity_ok=True,
        out_dir="/tmp",
        notes=["physics_fail"],
    )
    props = collect_section_proposals(obs, params, thr, tried=set())
    for pr in props:
        assert "window_scale" not in pr.reason
        # may keep window_scale field equal to current; must not bump it as the move
        if pr.params.window_scale != params.window_scale:
            raise AssertionError("P1 must not propose window_scale changes")


def test_solved_implies_empty_proposal_board_without_force_clear():
    """Invariant: is_solved thresholds align with proposal triggers."""
    thr = JobThresholds()
    params = FreeParams(
        align_mode="depth_primary",
        channel_pack="surface_min",
        null_policy="mark_only",
        window_scale=1,
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
    )
    assert is_solved(obs, thr, params) is True
    props = collect_section_proposals(obs, params, thr, tried=set())
    assert props == []


def test_fixed_point_k2_requires_two_consecutive_solved_cycles(tmp_path: Path):
    result = run_job_coherence_loop(
        las_path=FIXTURE,
        out_root=tmp_path / "job_os_k2",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_min",
            null_policy="mark_only",
        ),
        thresholds=JobThresholds(),
        max_rounds=6,
        stability_k=2,
        os_mode=True,
        run_id="test_fixed_k2",
    )
    assert result["solved"] is True
    assert result["stability_k"] == 2
    assert result["stability_streak"] >= 2
    ledger = result["ledger"]
    actions = [e.get("action") for e in ledger if isinstance(e.get("round"), int)]
    assert "stability_hold" in actions
    assert "halt" in actions
    # hold before halt
    hold_i = actions.index("stability_hold")
    halt_i = actions.index("halt")
    assert hold_i < halt_i
    halt_entry = next(e for e in ledger if e.get("action") == "halt")
    assert int(halt_entry.get("stability_streak") or 0) >= 2


def test_cli_exit_codes(tmp_path: Path):
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    cli = str(root / "job_coherence.py")

    # --- exit 0: solved ---
    out = tmp_path / "cli_out"
    proc = subprocess.run(
        [
            sys.executable,
            cli,
            "--os",
            "--las",
            str(FIXTURE),
            "--out-dir",
            str(out),
            "--stability-k",
            "1",
            "--channel-pack",
            "surface_min",
            "--run-id",
            "cli_smoke",
        ],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(proc.stdout)
    assert data["solved"] is True

    # --- exit 2: missing --las ---
    proc2 = subprocess.run(
        [sys.executable, cli, "--os", "--out-dir", str(tmp_path / "cli_missing")],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    assert proc2.returncode == 2, proc2.stdout + proc2.stderr

    # --- exit 2: bad resume path ---
    proc2b = subprocess.run(
        [
            sys.executable,
            cli,
            "--resume",
            str(tmp_path / "no_such_run"),
            "--out-dir",
            str(tmp_path / "cli_bad_resume"),
        ],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    assert proc2b.returncode == 2, proc2b.stdout + proc2b.stderr

    # --- exit 4: hard pin fail (non-monotonic depth) ---
    bad_las = tmp_path / "non_mono.las"
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    # Swap two depth values in ~A section to break mono
    out_lines = []
    in_a = False
    rows: list[str] = []
    for line in lines:
        if line.strip().upper().startswith("~A"):
            in_a = True
            out_lines.append(line)
            continue
        if in_a and line.strip() and not line.strip().startswith("~"):
            rows.append(line)
        else:
            if in_a and rows:
                # break mono: put a high depth early
                parts = rows[0].split()
                parts[0] = "9999.00"
                rows[0] = " ".join(parts)
                out_lines.extend(rows)
                rows = []
                in_a = False
            out_lines.append(line)
    if rows:
        parts = rows[0].split()
        parts[0] = "9999.00"
        rows[0] = " ".join(parts)
        # also make a later row lower to ensure violation after first
        if len(rows) > 1:
            p2 = rows[1].split()
            p2[0] = "1000.00"
            rows[1] = " ".join(p2)
        out_lines.extend(rows)
    bad_las.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    proc4 = subprocess.run(
        [
            sys.executable,
            cli,
            "--os",
            "--las",
            str(bad_las),
            "--out-dir",
            str(tmp_path / "cli_pin"),
            "--run-id",
            "cli_pin_fail",
        ],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    assert proc4.returncode == 4, proc4.stdout + proc4.stderr
    data4 = json.loads(proc4.stdout)
    assert data4.get("stop_reason") == "pin_fail"


def test_wrap_yes_best_effort_parse(tmp_path: Path):
    """WRAP=YES token-stream chunking (best-effort; P1 fixture is WRAP=NO)."""
    las = tmp_path / "wrap.las"
    las.write_text(
        "\n".join(
            [
                "~VERSION INFORMATION",
                "VERS.                           2.0 : CWLS",
                "WRAP.                          YES : Multiple lines per depth",
                "~WELL INFORMATION",
                "NULL.                        -999.25 : NULL",
                "~CURVE INFORMATION",
                "DEPT.FT                              : Depth",
                "WOB.klbf                             : WOB",
                "RPM.rpm                              : RPM",
                "~A",
                "1000.0 20.0",
                "50.0",
                "1001.0 21.0 52.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    series = parse_las(las)
    assert series["wrap"] is True
    assert series["n_rows"] >= 2
    assert series["depths"][0] == pytest.approx(1000.0)
