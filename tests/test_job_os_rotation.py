"""Multi-well rotation (Mode C): same pin, firewall_certified branch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from realm.job_os.rotation import (
    classify_rotation,
    load_rotation_manifest,
    run_job_rotation,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_edr.las"


def test_classify_rotation_branches():
    assert classify_rotation(
        [{"firewall_certified": True}, {"firewall_certified": True}]
    )["branch"] == "ROTATION_PASS"
    assert classify_rotation(
        [{"firewall_certified": True}, {"firewall_certified": False}]
    )["branch"] == "ROTATION_PARTIAL"
    assert classify_rotation(
        [{"firewall_certified": False}, {"firewall_certified": False}]
    )["branch"] == "ROTATION_FAIL"
    partial = classify_rotation(
        [
            {"firewall_certified": True, "firewall_near_miss": False},
            {"firewall_certified": False, "firewall_near_miss": True},
        ]
    )
    assert partial["near_miss_flag"] is True
    assert partial["certify_fraction"] == pytest.approx(0.5)


def test_load_manifest_requires_las(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"wells": [{"well_id": "x"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="las"):
        load_rotation_manifest(bad)


def test_rotation_dry_run(tmp_path: Path):
    man = {
        "kind": "job_rotation_manifest",
        "prereg_id": "test_dry",
        "free_params": {"channel_pack": "surface_min"},
        "wells": [
            {"well_id": "A", "las": str(FIXTURE)},
            {"well_id": "B", "las": str(FIXTURE)},
        ],
    }
    man_path = tmp_path / "man.json"
    man_path.write_text(json.dumps(man), encoding="utf-8")
    report = run_job_rotation(
        man_path, out_root=tmp_path / "rot", dry_run=True
    )
    assert report["branch"] == "DRY_RUN"
    assert report["pin_writable"] is False
    assert (Path(report["batch_dir"]) / "MANIFEST.json").is_file()
    assert (Path(report["batch_dir"]) / "ROTATION_REPORT.json").is_file()


def test_rotation_two_fixture_aliases_pass(tmp_path: Path):
    """Same LAS as two well_ids = affordable rotation smoke under identical pin."""
    man = {
        "kind": "job_rotation_manifest",
        "prereg_id": "fixture_dual_alias",
        "stability_k": 1,
        "max_rounds": 4,
        "free_params": {
            "channel_pack": "surface_min",
            "align_mode": "depth_primary",
            "null_policy": "mark_only",
        },
        "thresholds": {},
        "wells": [
            {"well_id": "fixture_w1", "las": str(FIXTURE)},
            {"well_id": "fixture_w2", "las": str(FIXTURE)},
        ],
    }
    man_path = tmp_path / "man_live.json"
    man_path.write_text(json.dumps(man), encoding="utf-8")
    report = run_job_rotation(man_path, out_root=tmp_path / "rot_live")
    assert report["pin_identical_across_wells"] is True
    assert report["pin_writable"] is False
    assert len(report["wells"]) == 2
    # Fixture surface_min is designed to SOLVE → both should certify
    for w in report["wells"]:
        assert w.get("status") == "ok"
        assert w.get("pin_config_depth_mono_eps") is not None
    assert report["branch"] == "ROTATION_PASS"
    assert report["classification"]["n_firewall_certified"] == 2
    assert (Path(report["batch_dir"]) / "ROTATION_REPORT.md").is_file()
    # Nested Job OS trees + FIREWALL
    for w in report["wells"]:
        out = Path(w["out_root"])
        assert (out / "FIREWALL.json").is_file()
        assert (out / "COHERENCE.json").is_file()


def test_cli_rotation_dry(tmp_path: Path):
    import subprocess
    import sys

    man = {
        "wells": [
            {"well_id": "cli_a", "las": str(FIXTURE)},
            {"well_id": "cli_b", "las": str(FIXTURE)},
        ],
        "free_params": {"channel_pack": "surface_min"},
    }
    man_path = tmp_path / "cli_man.json"
    man_path.write_text(json.dumps(man), encoding="utf-8")
    out = tmp_path / "cli_rot"
    proc = subprocess.run(
        [
            sys.executable,
            "job_coherence.py",
            "--rotation",
            str(man_path),
            "--rotation-dry-run",
            "--out-dir",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    assert body.get("rotation") is True
    assert body.get("branch") == "DRY_RUN"
