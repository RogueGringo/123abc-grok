"""Standalone handoff_release CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

from handoff_release import main as release_main


def test_handoff_release_restamp_and_archive(tmp_path: Path):
    camp = tmp_path / "camp"
    camp.mkdir()
    zpath = tmp_path / "handoff.zip"
    zpath.write_bytes(b"PK\x03\x04fakezip")
    campaign = {
        "ids": ["1IKF"],
        "export": {
            "n_ok": 1,
            "n_ids": 1,
            "summary_md": str(camp / "SUMMARY.md"),
            "enrichment_aggregate": {
                "n_with_enrichment": 0,
                "mean_enrichment": None,
                "top20_count": 0,
            },
        },
        "package": {
            "package_dir": str(tmp_path / "pkg"),
            "zip_path": str(zpath),
            "zip_sha256": "aa",
            "has_summary_md": True,
        },
        "verify": {
            "ok": True,
            "pin": {"ok": True, "soft_T": 0.036, "seq_mix": 0.0, "face_weight": 0.08},
            "ontology_remarks": {"ok": True, "n_pdb": 2},
            "sha256": {"ok": True},
        },
        "quality_gate": {"ok": True, "reasons": [], "n_pdb": 2},
        "ontology": "handoff_campaign_not_lambda_eq_gamma",
    }
    (camp / "campaign_report.json").write_text(
        json.dumps(campaign, indent=2) + "\n", encoding="utf-8"
    )
    (camp / "SUMMARY.md").write_text("# sum\n", encoding="utf-8")
    (camp / "verify_report.json").write_text(
        json.dumps(campaign["verify"], indent=2) + "\n", encoding="utf-8"
    )

    rc = release_main(
        [
            str(camp),
            "--release-label",
            "holdout-restamp",
            "--archive",
            "--archive-dir",
            str(tmp_path / "releases"),
            "--skip-preflight",
        ]
    )
    assert rc == 0
    assert (camp / "RELEASE.md").is_file()
    text = (camp / "RELEASE.md").read_text(encoding="utf-8")
    assert "0.036" in text or "soft_T" in text
    data = json.loads((camp / "campaign_report.json").read_text(encoding="utf-8"))
    assert data.get("archive")
    assert Path(data["archive"]["archive_dir"]).is_dir()
    assert (Path(data["archive"]["archive_dir"]) / "ARCHIVE.json").is_file()
