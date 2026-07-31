"""handoff_science golden-path dry-run / pin tests."""

from __future__ import annotations

import json
from pathlib import Path

from handoff_science import main as science_main


def test_handoff_science_dry_run(tmp_path: Path):
    out = tmp_path / "ks"
    rc = science_main(
        [
            "--dry-run",
            "--skip-expand",
            "--out-dir",
            str(out),
            "--compare-modes",
            "",
        ]
    )
    assert rc == 0
    assert (out / "LATEST").is_file() or any(out.iterdir())
    # pin stamped under stamp dir
    latest = (out / "LATEST").read_text(encoding="utf-8").strip()
    pin = json.loads(Path(latest, "pin.json").read_text(encoding="utf-8"))
    assert pin.get("ok") is True
    assert abs(float(pin["soft_T"]) - 0.036) < 1e-12


def test_handoff_science_attach_existing_stamp(tmp_path: Path):
    """Attach path exercised via known_solutions attach after dry-run stamp."""
    from realm.validate.known_solutions import attach_report_to_dir

    out = tmp_path / "ks"
    rc = science_main(["--dry-run", "--skip-expand", "--out-dir", str(out)])
    assert rc == 0
    stamp = Path((out / "LATEST").read_text(encoding="utf-8").strip())
    # dry-run writes annex; ensure partner disclaimer present
    annex_md = stamp / "PARTNER_SCIENCE_ANNEX.md"
    assert annex_md.is_file()
    text = annex_md.read_text(encoding="utf-8")
    assert "ACCEPTANCE" in text or "acceptance" in text.lower()

    releases = tmp_path / "releases"
    releases.mkdir()
    meta = attach_report_to_dir(stamp, releases)
    assert meta["ok"] is True
    assert (releases / "PARTNER_SCIENCE_ANNEX.json").is_file()
