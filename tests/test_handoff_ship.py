"""handoff_ship golden-path tests (no full matrix)."""

from __future__ import annotations

import json
from pathlib import Path

from handoff_ship import main as ship_main
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
    ship = json.loads((releases / "SHIP.json").read_text(encoding="utf-8"))
    assert ship["ok"] is True
    assert ship["shippable"] is True
    assert abs(ship["soft_T"] - 0.036) < 1e-12
    assert (releases / "LATEST_DELIVERY.json").is_file() or (
        matrix_dir / "DELIVERY.json"
    ).is_file()
