"""Partner audit: FIREWALL / pin seal without re-ingest."""

from __future__ import annotations

import json
from pathlib import Path

from realm.job_os.audit import audit_job_run, audit_rotation_batch
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.rotation import run_job_rotation
from realm.job_os.types import FreeParams, JobThresholds

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_edr.las"


def test_audit_solved_run(tmp_path: Path):
    result = run_job_coherence_loop(
        las_path=FIXTURE,
        out_root=tmp_path / "aud",
        initial=FreeParams(channel_pack="surface_min"),
        thresholds=JobThresholds(),
        max_rounds=4,
        os_mode=True,
        stability_k=1,
    )
    assert result["solved"] is True
    report = audit_job_run(result["out_root"])
    assert report["ok"] is True
    assert report["firewall_certified"] is True
    assert report["solved"] is True
    assert report["partner_recipe"] is True
    assert report["pin_writable"] is False
    assert report["n_fail"] == 0


def test_audit_missing_dir(tmp_path: Path):
    r = audit_job_run(tmp_path / "nope")
    assert r["ok"] is False


def test_audit_near_miss_invariant_fail(tmp_path: Path):
    # Craft a broken FIREWALL on disk
    run = tmp_path / "bad"
    run.mkdir()
    (run / "COHERENCE.json").write_text(
        json.dumps({"solved": False, "run_id": "bad", "ledger": []}),
        encoding="utf-8",
    )
    (run / "FIREWALL.json").write_text(
        json.dumps(
            {
                "kind": "job_qc_firewall",
                "pin_writable": False,
                "acceptance_writable": False,
                "certified": True,  # inconsistent with near_miss
                "explore": {
                    "not_acceptance": True,
                    "pin_writable": False,
                    "acceptance_writable": False,
                    "looks_promising": True,
                },
                "certify": {"certified": True, "pin_writable": False},
                "near_miss": {"near_miss": True, "certified": True, "verdict": "bad"},
            }
        ),
        encoding="utf-8",
    )
    r = audit_job_run(run)
    assert r["ok"] is False
    codes = {f["code"] for f in r["findings"]}
    assert "near_miss_certified" in codes or "certify_without_solved" in codes


def test_audit_rotation_batch(tmp_path: Path):
    man = {
        "prereg_id": "audit_rot",
        "stability_k": 1,
        "max_rounds": 4,
        "free_params": {"channel_pack": "surface_min"},
        "wells": [
            {"well_id": "a", "las": str(FIXTURE)},
            {"well_id": "b", "las": str(FIXTURE)},
        ],
    }
    man_path = tmp_path / "man.json"
    man_path.write_text(json.dumps(man), encoding="utf-8")
    report = run_job_rotation(man_path, out_root=tmp_path / "rot")
    assert report["branch"] == "ROTATION_PASS"
    aud = audit_rotation_batch(report["batch_dir"])
    assert aud["ok"] is True
    assert aud["branch"] == "ROTATION_PASS"
    assert aud["n_firewall_certified"] == 2
    assert all(w.get("ok") for w in aud["wells"])
