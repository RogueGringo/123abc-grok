"""handoff_status CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

from handoff_status import build_status, main as status_main
from realm.handoff.package import (
    archive_partner_release,
    write_acceptance_json,
    write_release_md,
)
from realm.handoff.verify import verify_attestation


def test_handoff_status_build_and_cli(tmp_path: Path):
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
    write_release_md(campaign, camp / "RELEASE.md", label="st")
    campaign["release_md"] = str(camp / "RELEASE.md")
    acc = write_acceptance_json(campaign, camp / "ACCEPTANCE.json", label="st")
    campaign["acceptance_json"] = str(acc)
    releases = tmp_path / "releases"
    meta = archive_partner_release(
        campaign, archive_root=releases, label="st", campaign_dir=camp
    )
    arch = Path(meta["archive_dir"])
    assert (arch / "ATTESTATION.json").is_file()
    assert (arch / "ACCEPTANCE.json").is_file()
    av = verify_attestation(arch)
    assert av["ok"] is True

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

    # optional science stamp (must not flip commercial ok)
    ks = tmp_path / "ks"
    stamp = ks / "S1"
    stamp.mkdir(parents=True)
    (stamp / "pin.json").write_text(
        json.dumps({"ok": True, "soft_T": 0.036}), encoding="utf-8"
    )
    (stamp / "PARTNER_SCIENCE_ANNEX.json").write_text(
        json.dumps(
            {
                "kind": "partner_science_annex",
                "pin": {"ok": True, "soft_T": 0.036},
                "mean_enrichment_by_tag": {
                    "all_ok": {"n": 2, "mean_enrichment": 0.8}
                },
            }
        ),
        encoding="utf-8",
    )
    (stamp / "DECOY_MODE_COMPARE.json").write_text(
        json.dumps(
            {
                "by_mode": {
                    "soft": {"all_ok": {"mean_enrichment": 0.9}},
                    "hard": {"all_ok": {"mean_enrichment": 0.6}},
                },
                "deltas_vs_soft": {"hard": {"delta_all_vs_soft": -0.3}},
            }
        ),
        encoding="utf-8",
    )
    (ks / "LATEST").write_text(str(stamp.resolve()), encoding="utf-8")

    st = build_status(
        releases_dir=releases,
        matrix_report=matrix,
        verify_latest=True,
        rebuild_catalog=True,
        known_solutions_dir=ks,
    )
    assert st["ok"] is True
    assert st["pin"]["ok"] is True
    assert abs(st["pin"]["soft_T"] - 0.036) < 1e-12
    assert st["n_drops"] >= 1
    assert st["latest"] is not None
    assert st["archive_verify"]["ok"] is True
    assert st.get("acceptance", {}).get("accepted") is True
    ks_st = st.get("known_solutions") or {}
    assert ks_st.get("has_compare") is True
    assert ks_st.get("compare_all_enr", {}).get("soft") == 0.9
    assert "not" in (ks_st.get("note") or "").lower() or "Science" in (
        ks_st.get("note") or ""
    )
    assert st.get("attestation", {}).get("n_digests", 0) >= 1
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
    assert data.get("acceptance", {}).get("accepted") is True
