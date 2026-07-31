"""Commercial DELIVERY receipt tests."""

from __future__ import annotations

import json
from pathlib import Path

from handoff_deliver import main as deliver_main
from realm.handoff.package import write_delivery_receipt
from realm.handoff.verify import verify_delivery_receipt, verify_dual_gate_pin


def test_write_delivery_receipt(tmp_path: Path):
    pin = verify_dual_gate_pin()
    ma = {
        "ok": True,
        "n_tokens": 2,
        "n_accepted": 2,
        "n_pdb_total": 24,
        "tokens": {
            "probe": {
                "accepted": True,
                "n_pdb": 8,
                "archive_dir": str(tmp_path / "missing"),
                "reasons": [],
            },
            "holdout": {
                "accepted": True,
                "n_pdb": 16,
                "archive_dir": None,
                "reasons": [],
            },
        },
    }
    latest = {
        "archive_dir": str(tmp_path),
        "label": "matrix-holdout",
        "accepted": True,
        "n_pdb": 16,
        "zip_sha256": "abc",
        "payload_sha256": "def",
    }
    path = write_delivery_receipt(
        path=tmp_path / "DELIVERY.json",
        pin=pin,
        matrix_acceptance=ma,
        latest=latest,
        matrix_report={"tokens": ["probe", "holdout"]},
        label="test-ship",
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["shippable"] is True
    assert data["pin"]["ok"] is True
    assert abs(data["pin"]["soft_T"] - 0.036) < 1e-12
    assert data["matrix_acceptance"]["n_pdb_total"] == 24
    assert len(data["drops"]) == 2
    assert "mean_enrichment" in data["not_acceptance_criteria"]
    assert data.get("payload_sha256")
    assert "not_lambda_eq_gamma" in data["ontology"]
    v = verify_delivery_receipt(path, require_shippable=True)
    assert v["ok"] is True
    assert v["payload_sha256_ok"] is True

    # tamper
    data["shippable"] = False
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    bad = verify_delivery_receipt(path, require_shippable=True)
    assert bad["ok"] is False


def test_handoff_deliver_cli(tmp_path: Path):
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
            "probe": {"accepted": True, "n_pdb": 4, "archive_dir": None, "reasons": []}
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
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (releases / "LATEST.json").write_text(
        json.dumps(
            {
                "archive_dir": str(releases / "drop"),
                "label": "probe",
                "accepted": True,
                "n_pdb": 4,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rc = deliver_main(
        [
            "--matrix-report",
            str(matrix_dir / "matrix_report.json"),
            "--releases",
            str(releases),
            "--require-shippable",
            "--label",
            "cli-test",
        ]
    )
    assert rc == 0
    assert (matrix_dir / "DELIVERY.json").is_file()
    assert (releases / "DELIVERY.json").is_file()
    ship = json.loads((matrix_dir / "DELIVERY.json").read_text(encoding="utf-8"))
    assert ship["shippable"] is True
