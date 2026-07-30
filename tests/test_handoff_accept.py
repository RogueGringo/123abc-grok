"""Partner accept CLI / accept_partner_drop tests."""

from __future__ import annotations

import json
from pathlib import Path

from handoff_accept import main as accept_main
from realm.handoff.package import (
    archive_partner_release,
    write_acceptance_json,
    write_release_md,
)
from realm.handoff.verify import accept_partner_drop


def test_accept_partner_drop_archive(tmp_path: Path):
    camp = tmp_path / "camp"
    camp.mkdir()
    zpath = tmp_path / "p.zip"
    zpath.write_bytes(b"PK\x03\x04z")
    campaign = {
        "ids": ["1CSA"],
        "export": {"n_ok": 1, "n_ids": 1, "summary_md": str(camp / "SUMMARY.md")},
        "package": {"zip_path": str(zpath), "zip_sha256": "zz"},
        "verify": {
            "ok": True,
            "pin": {"ok": True, "soft_T": 0.036, "seq_mix": 0.0, "face_weight": 0.08},
            "ontology_remarks": {"ok": True, "n_pdb": 2},
            "sha256": {"ok": True},
            "biopython": {"ok": None, "skipped": True},
        },
        "quality_gate": {"ok": True},
    }
    (camp / "SUMMARY.md").write_text("# s\n", encoding="utf-8")
    (camp / "campaign_report.json").write_text("{}\n", encoding="utf-8")
    (camp / "verify_report.json").write_text(
        json.dumps(campaign["verify"]) + "\n", encoding="utf-8"
    )
    write_release_md(campaign, camp / "RELEASE.md", label="acc")
    campaign["release_md"] = str(camp / "RELEASE.md")
    acc = write_acceptance_json(campaign, camp / "ACCEPTANCE.json", label="acc")
    campaign["acceptance_json"] = str(acc)
    releases = tmp_path / "releases"
    meta = archive_partner_release(
        campaign, archive_root=releases, label="acc", campaign_dir=camp
    )
    arch = Path(meta["archive_dir"])

    report = accept_partner_drop(arch, require_attestation=True)
    assert report["ok"] is True
    assert report["accepted"] is True
    assert report["mode"] == "archive"
    assert report["n_pdb"] == 2
    assert abs(report["pin"]["soft_T"] - 0.036) < 1e-12

    # LATEST pointer enriched
    latest = json.loads((releases / "LATEST.json").read_text(encoding="utf-8"))
    assert latest.get("accepted") is True
    assert latest.get("n_pdb") == 2
    assert latest.get("accept_cli")

    rc = accept_main(["--latest", "--releases", str(releases)])
    assert rc == 0
    assert (arch / "ACCEPT_REPORT.json").is_file()


def test_accept_fails_without_acceptance(tmp_path: Path):
    d = tmp_path / "empty"
    d.mkdir()
    (d / "foo.txt").write_text("x", encoding="utf-8")
    r = accept_partner_drop(d, require_acceptance=True, require_attestation=False)
    assert r["ok"] is False
    assert "acceptance_json_missing" in r["reasons"]
