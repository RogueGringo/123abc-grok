"""handoff_ship golden-path tests (no full matrix)."""

from __future__ import annotations

import json
from pathlib import Path

from handoff_ship import main as ship_main
from realm.handoff.package import (
    build_partner_receipt_bundle,
    verify_partner_receipt_bundle,
)
from realm.handoff.verify import verify_dual_gate_pin


def test_handoff_ship_from_existing_matrix(tmp_path: Path):
    pin = verify_dual_gate_pin()
    matrix_dir = tmp_path / "matrix"
    matrix_dir.mkdir()
    releases = tmp_path / "releases"
    releases.mkdir()
    ma = {
        "ok": True,
        "n_tokens": 2,
        "n_accepted": 2,
        "n_pdb_total": 10,
        "tokens": {
            "probe": {"accepted": True, "n_pdb": 4, "archive_dir": None, "reasons": []},
            "holdout": {
                "accepted": True,
                "n_pdb": 6,
                "archive_dir": None,
                "reasons": [],
            },
        },
    }
    (matrix_dir / "matrix_acceptance.json").write_text(
        json.dumps(ma) + "\n", encoding="utf-8"
    )
    (matrix_dir / "matrix_report.json").write_text(
        json.dumps(
            {
                "ok": True,
                "tokens": ["probe", "holdout"],
                "acceptance": ma,
                "pin": pin,
                "rows": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (releases / "LATEST.json").write_text(
        json.dumps(
            {
                "archive_dir": str(releases / "d"),
                "label": "holdout",
                "accepted": True,
                "n_pdb": 6,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    # pre-seed empty status catalog
    rc = ship_main(
        [
            "--out-root",
            str(matrix_dir),
            "--releases",
            str(releases),
            "--matrix-report",
            str(matrix_dir / "matrix_report.json"),
            "--label",
            "ship-test",
        ]
    )
    assert rc == 0
    assert (releases / "SHIP.json").is_file()
    assert (releases / "SHIP.md").is_file()
    ship = json.loads((releases / "SHIP.json").read_text(encoding="utf-8"))
    assert ship["ok"] is True
    assert ship["shippable"] is True
    assert abs(ship["soft_T"] - 0.036) < 1e-12
    assert "0.036" in (releases / "SHIP.md").read_text(encoding="utf-8")
    assert (releases / "LATEST_DELIVERY.json").is_file() or (
        matrix_dir / "DELIVERY.json"
    ).is_file()
    # DELIVERY.md companion
    for cand in (
        releases / "LATEST_DELIVERY.md",
        releases / "DELIVERY.md",
        matrix_dir / "DELIVERY.md",
    ):
        if cand.is_file():
            assert "not" in cand.read_text(encoding="utf-8").lower()
            break
    else:
        raise AssertionError("expected DELIVERY.md companion")

    assert ship.get("partner_receipt_bundle")
    assert Path(ship["partner_receipt_bundle"]).is_file()
    assert ship.get("partner_receipt_bundle_ok") is True
    assert (releases / "PARTNER_RECEIPT_BUNDLE.json").is_file()
    # rebuild bundle independently
    meta = build_partner_receipt_bundle(
        releases_dir=releases, matrix_dir=matrix_dir, label="rebuild"
    )
    assert meta["n_files"] >= 3
    assert Path(meta["zip_path"]).is_file()
    bv = verify_partner_receipt_bundle(meta["zip_path"])
    assert bv["ok"] is True
    assert abs(bv["pin"]["soft_T"] - 0.036) < 1e-12

    rc2 = ship_main(["--verify-bundle", meta["zip_path"]])
    assert rc2 == 0


def test_handoff_ship_attach_compare_annex(tmp_path: Path):
    """Attach is report-only; ship still succeeds with science compare files."""
    pin = verify_dual_gate_pin()
    matrix_dir = tmp_path / "matrix"
    matrix_dir.mkdir()
    releases = tmp_path / "releases"
    releases.mkdir()
    ma = {
        "ok": True,
        "n_tokens": 1,
        "n_accepted": 1,
        "n_pdb_total": 4,
        "tokens": {
            "probe": {"accepted": True, "n_pdb": 4, "archive_dir": None, "reasons": []},
        },
    }
    (matrix_dir / "matrix_acceptance.json").write_text(
        json.dumps(ma) + "\n", encoding="utf-8"
    )
    (matrix_dir / "matrix_report.json").write_text(
        json.dumps(
            {
                "ok": True,
                "tokens": ["probe"],
                "acceptance": ma,
                "pin": pin,
                "rows": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (releases / "LATEST.json").write_text(
        json.dumps(
            {
                "archive_dir": str(releases / "d"),
                "label": "probe",
                "accepted": True,
                "n_pdb": 4,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ks = tmp_path / "ks_stamp"
    ks.mkdir()
    (ks / "PARTNER_SCIENCE_ANNEX.json").write_text(
        json.dumps({"kind": "partner_science_annex", "pin": {"ok": True}}),
        encoding="utf-8",
    )
    (ks / "PARTNER_SCIENCE_ANNEX.md").write_text("# annex\n", encoding="utf-8")
    (ks / "pin.json").write_text(
        json.dumps({"ok": True, "soft_T": 0.036, "seq_mix": 0.0, "face_weight": 0.08}),
        encoding="utf-8",
    )
    (ks / "DECOY_MODE_COMPARE.json").write_text(
        json.dumps({"by_mode": {"soft": {}, "hard": {}}}), encoding="utf-8"
    )
    (ks / "DECOY_MODE_COMPARE.md").write_text("# compare\n", encoding="utf-8")

    rc = ship_main(
        [
            "--out-root",
            str(matrix_dir),
            "--releases",
            str(releases),
            "--matrix-report",
            str(matrix_dir / "matrix_report.json"),
            "--label",
            "ship-ks-attach",
            "--attach-known-solutions",
            str(ks),
            "--no-bundle",
        ]
    )
    assert rc == 0
    ship = json.loads((releases / "SHIP.json").read_text(encoding="utf-8"))
    assert ship.get("ok") is True
    assert ship.get("known_solutions_attach", {}).get("ok") is True
    assert ship.get("known_solutions_attach", {}).get("has_decoy_mode_compare") is True
    assert (releases / "DECOY_MODE_COMPARE.md").is_file()
    assert (releases / "PARTNER_SCIENCE_ANNEX.json").is_file()
    text = (releases / "SHIP.md").read_text(encoding="utf-8")
    assert "decoy_mode_compare" in text or "DECOY_MODE_COMPARE" in text
