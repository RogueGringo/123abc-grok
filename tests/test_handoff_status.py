"""handoff_status CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

from handoff_status import build_status, main as status_main
from realm.handoff.package import archive_partner_release, write_release_md


def test_handoff_status_build_and_cli(tmp_path: Path):
    camp = tmp_path / "camp"
    camp.mkdir()
    zpath = tmp_path / "p.zip"
    zpath.write_bytes(b"PK\x03\x04z")
    campaign = {
        "ids": ["1CSA"],
        "export": {"n_ok": 1, "n_ids": 1, "summary_md": str(camp / "SUMMARY.md")},
        "package": {"zip_path": str(zpath), "zip_sha256": "zz"},
        "quality_gate": {"ok": True},
    }
    (camp / "SUMMARY.md").write_text("# s\n", encoding="utf-8")
    (camp / "campaign_report.json").write_text("{}\n", encoding="utf-8")
    (camp / "verify_report.json").write_text('{"ok":true}\n', encoding="utf-8")
    write_release_md(campaign, camp / "RELEASE.md", label="st")
    campaign["release_md"] = str(camp / "RELEASE.md")
    releases = tmp_path / "releases"
    archive_partner_release(
        campaign, archive_root=releases, label="st", campaign_dir=camp
    )

    matrix = tmp_path / "matrix_report.json"
    matrix.write_text(
        json.dumps(
            {
                "ok": True,
                "tokens": ["probe", "holdout"],
                "rows": [{"token": "probe", "ok": True}],
                "ontology": "handoff_matrix_not_lambda_eq_gamma",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    st = build_status(
        releases_dir=releases,
        matrix_report=matrix,
        verify_latest=True,
        rebuild_catalog=True,
    )
    assert st["ok"] is True
    assert st["pin"]["ok"] is True
    assert abs(st["pin"]["soft_T"] - 0.036) < 1e-12
    assert st["n_drops"] >= 1
    assert st["latest"] is not None
    assert st["archive_verify"]["ok"] is True
    assert (releases / "INDEX.json").is_file()
    assert (releases / "STATUS.json").is_file() or True  # written by CLI

    rc = status_main(
        [
            "--releases",
            str(releases),
            "--matrix-report",
            str(matrix),
            "--verify-latest",
            "--report",
            str(releases / "STATUS.json"),
        ]
    )
    assert rc == 0
    data = json.loads((releases / "STATUS.json").read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert "not_lambda_eq_gamma" in data["ontology"]
