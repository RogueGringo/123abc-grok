"""Job Coherence OS P5 EOW package ship gate + inventory tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from realm.job_os.eow_ship import (
    UNSOLVED_SHIP_BANNER,
    classify_eow_file,
    inventory_eow_package,
    ship_eow_package,
    sha256_file,
)
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.types import FreeParams, JobThresholds

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LAS = FIXTURES / "mini_edr.las"
SURVEY = FIXTURES / "mini_survey.csv"


def _make_eow_dir(tmp_path: Path) -> Path:
    """Build a mini EOW-like directory: survey, LAS, pdf, xlsx checklist."""
    eow = tmp_path / "MWD_EOW_EXAMPLE"
    eow.mkdir(parents=True, exist_ok=True)
    shutil.copy(SURVEY, eow / "survey_stations.csv")
    shutil.copy(LAS, eow / "surface.las")
    (eow / "report.pdf").write_bytes(b"%PDF-1.4 mini eow report\n")
    (eow / "eow_checklist.xlsx").write_bytes(
        b"PK\x03\x04mini-xlsx-checklist-placeholder"
    )
    (eow / "notes.txt").write_text("client drop note\n", encoding="utf-8")
    return eow


def test_classify_eow_kinds(tmp_path: Path):
    assert classify_eow_file(tmp_path / "foo.las") == "las"
    assert classify_eow_file(tmp_path / "survey_table.csv") == "survey"
    assert classify_eow_file(tmp_path / "report.pdf") == "pdf"
    assert classify_eow_file(tmp_path / "eow_checklist.xlsx") == "checklist"
    assert classify_eow_file(tmp_path / "data.xlsx") == "xlsx"
    assert classify_eow_file(tmp_path / "readme.txt") == "other"


def test_inventory_eow_package_hashes(tmp_path: Path):
    eow = _make_eow_dir(tmp_path)
    inv = inventory_eow_package(eow)
    assert inv["n_files"] >= 4
    assert inv["counts"]["survey"] >= 1
    assert inv["counts"]["las"] >= 1
    assert inv["counts"]["pdf"] >= 1
    assert inv["counts"]["checklist"] >= 1
    for f in inv["files"]:
        assert len(f["sha256"]) == 64
        assert f["size_bytes"] >= 0
        assert Path(f["abs_path"]).is_file()
        # Integrity: re-hash matches
        assert f["sha256"] == sha256_file(f["abs_path"])


def test_ship_refused_when_not_solved(tmp_path: Path):
    eow = _make_eow_dir(tmp_path)
    run_dir = tmp_path / "run_unsolved"
    run_dir.mkdir()
    result = ship_eow_package(
        run_dir=run_dir,
        eow_package=eow,
        solved=False,
        force_ship=False,
        run_id="unsolved_test",
    )
    assert result["refused"] is True
    assert result["shipped"] is False
    assert result["ok"] is False
    assert result["status"] == "REFUSED_NOT_SOLVED"
    assert not (run_dir / "eow" / "PACKAGE_INDEX.json").is_file()
    assert not (run_dir / "eow" / "SHIP.md").is_file()


def test_force_ship_unsolved_banner(tmp_path: Path):
    eow = _make_eow_dir(tmp_path)
    run_dir = tmp_path / "run_force"
    run_dir.mkdir()
    result = ship_eow_package(
        run_dir=run_dir,
        eow_package=eow,
        solved=False,
        force_ship=True,
        run_id="force_test",
        free_params={"align_mode": "depth_primary"},
    )
    assert result["shipped"] is True
    assert result["ok"] is True
    assert result["refused"] is False
    assert result["status"] == UNSOLVED_SHIP_BANNER
    assert result["banner"] == UNSOLVED_SHIP_BANNER
    ship_md = Path(result["ship_md"]).read_text(encoding="utf-8")
    assert UNSOLVED_SHIP_BANNER in ship_md
    assert "not** SOLVED" in ship_md or "not SOLVED" in ship_md.lower()
    idx_path = run_dir / "eow" / "PACKAGE_INDEX.json"
    assert idx_path.is_file()
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    assert idx["banner"] == UNSOLVED_SHIP_BANNER
    assert idx["solved"] is False
    assert idx["force_ship"] is True


def test_ship_after_solved_writes_index_and_recipe_ref(tmp_path: Path):
    eow = _make_eow_dir(tmp_path)
    # Run job OS to SOLVED so PARTNER_RECIPE exists
    result = run_job_coherence_loop(
        las_path=LAS,
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
        run_id="eow_solved_ship",
        eow_package=eow,
        force_ship=False,
    )
    assert result["solved"] is True
    assert result["partner_recipe"] is not None
    assert result["eow_ship_status"] == "SHIPPED"
    eow_ship = result["eow_ship"]
    assert eow_ship["shipped"] is True
    assert eow_ship["banner"] is None
    assert eow_ship["solved"] is True

    run_dir = Path(result["out_root"])
    assert (run_dir / "PARTNER_RECIPE.json").is_file()
    assert (run_dir / "eow" / "PACKAGE_INDEX.json").is_file()
    assert (run_dir / "eow" / "SHIP.md").is_file()
    assert (run_dir / "eow" / "SHIP.json").is_file()

    idx = json.loads((run_dir / "eow" / "PACKAGE_INDEX.json").read_text(encoding="utf-8"))
    assert idx["status"] == "SHIPPED"
    assert idx["partner_recipe"]["present"] is True
    assert idx["partner_recipe"]["sha256"]
    assert idx["partner_recipe"]["free_params"] is not None
    assert "align_mode" in idx["partner_recipe"]["free_params"]
    inv = idx["inventory"]
    assert inv["counts"]["survey"] >= 1
    assert inv["counts"]["las"] >= 1
    assert all(len(f["sha256"]) == 64 for f in inv["files"])

    ship_md = (run_dir / "eow" / "SHIP.md").read_text(encoding="utf-8")
    assert "PARTNER_RECIPE" in ship_md
    assert "PACKAGE_INDEX" in ship_md
    assert UNSOLVED_SHIP_BANNER not in ship_md

    # RUN.json records ship
    run_doc = json.loads((run_dir / "RUN.json").read_text(encoding="utf-8"))
    assert run_doc["eow_ship_status"] == "SHIPPED"
    assert run_doc["partner_recipe"]


def test_resume_solved_then_eow_package(tmp_path: Path):
    """CLI path: full run to SOLVED, then --resume + --eow-package attach."""
    first = run_job_coherence_loop(
        las_path=LAS,
        out_root=tmp_path / "job_os",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_min",
            null_policy="mark_only",
        ),
        thresholds=JobThresholds(),
        max_rounds=3,
        stability_k=1,
        os_mode=True,
        run_id="eow_resume_attach",
    )
    assert first["solved"] is True
    run_dir = Path(first["out_root"])
    assert not (run_dir / "eow" / "PACKAGE_INDEX.json").is_file()

    eow = _make_eow_dir(tmp_path)
    second = run_job_coherence_loop(
        resume_dir=run_dir,
        eow_package=eow,
        force_ship=False,
    )
    assert second["solved"] is True
    assert second["eow_ship_status"] == "SHIPPED"
    assert (run_dir / "eow" / "PACKAGE_INDEX.json").is_file()
    assert (run_dir / "eow" / "SHIP.md").is_file()
    # Recipe still present and referenced
    idx = json.loads((run_dir / "eow" / "PACKAGE_INDEX.json").read_text(encoding="utf-8"))
    assert idx["partner_recipe"]["present"] is True
    recipe = json.loads((run_dir / "PARTNER_RECIPE.json").read_text(encoding="utf-8"))
    assert recipe["solved"] is True
    assert recipe["free_params"] == idx["partner_recipe"]["free_params"]


def test_loop_refuses_eow_when_stuck_no_force(tmp_path: Path):
    """Unsolved job with eow_package and no force → refuse, no eow artifacts."""
    # Force stuck: impossible pack without micropulse + max_rounds tiny won't recover
    # if we start at surface_min we solve — use require_survey without survey
    eow = _make_eow_dir(tmp_path)
    result = run_job_coherence_loop(
        las_path=LAS,
        out_root=tmp_path / "job_os",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_min",
            null_policy="mark_only",
            survey_gate="qc_only",
        ),
        thresholds=JobThresholds(require_survey=True),
        max_rounds=2,
        stability_k=1,
        os_mode=True,
        run_id="eow_stuck_refuse",
        eow_package=eow,
        force_ship=False,
    )
    assert result["solved"] is False
    assert result["eow_ship_status"] == "REFUSED_NOT_SOLVED"
    assert result["eow_ship"]["refused"] is True
    run_dir = Path(result["out_root"])
    assert not (run_dir / "eow" / "PACKAGE_INDEX.json").is_file()
    assert result["partner_recipe"] is None  # recipe only on SOLVED


def test_loop_force_ship_when_stuck(tmp_path: Path):
    eow = _make_eow_dir(tmp_path)
    result = run_job_coherence_loop(
        las_path=LAS,
        out_root=tmp_path / "job_os",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_min",
            survey_gate="qc_only",
        ),
        thresholds=JobThresholds(require_survey=True),
        max_rounds=2,
        stability_k=1,
        os_mode=True,
        run_id="eow_stuck_force",
        eow_package=eow,
        force_ship=True,
    )
    assert result["solved"] is False
    assert result["eow_ship_status"] == UNSOLVED_SHIP_BANNER
    run_dir = Path(result["out_root"])
    ship_md = (run_dir / "eow" / "SHIP.md").read_text(encoding="utf-8")
    assert UNSOLVED_SHIP_BANNER in ship_md
    # No PARTNER_RECIPE on unsolved — ship notes recipe absent
    idx = json.loads((run_dir / "eow" / "PACKAGE_INDEX.json").read_text(encoding="utf-8"))
    assert idx["partner_recipe"]["present"] is False


def test_cli_eow_package_after_solved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import job_coherence as jc

    eow = _make_eow_dir(tmp_path)
    out = tmp_path / "cli_job_os"
    # Full run + ship in one invocation
    code = jc.main(
        [
            "--os",
            "--las",
            str(LAS),
            "--out-dir",
            str(out),
            "--run-id",
            "cli_eow",
            "--eow-package",
            str(eow),
            "--max-rounds",
            "3",
        ]
    )
    assert code == 0
    run_dir = out / "cli_eow"
    assert (run_dir / "eow" / "PACKAGE_INDEX.json").is_file()
    assert (run_dir / "PARTNER_RECIPE.json").is_file()
