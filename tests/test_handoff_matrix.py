"""Handoff matrix dry-run smoke."""

from __future__ import annotations

import json
from pathlib import Path

from handoff_matrix import main as matrix_main


def test_matrix_dry_run(tmp_path: Path):
    rc = matrix_main(
        [
            "--tokens",
            "probe,holdout",
            "--out-root",
            str(tmp_path / "matrix"),
            "--dry-run",
            "--no-biopython-check",
        ]
    )
    assert rc == 0
    report = tmp_path / "matrix" / "matrix_report.json"
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "probe" in text and "holdout" in text
    assert "not_lambda_eq_gamma" in text
    acc = tmp_path / "matrix" / "matrix_acceptance.json"
    assert acc.is_file()
    data = json.loads(acc.read_text(encoding="utf-8"))
    assert data.get("ok") is True
    assert data.get("n_tokens") == 2


def test_matrix_attach_known_solutions_after_dry_does_not_run(tmp_path: Path):
    """dry-run skips attach; attach path only applied when not dry-run."""
    ks = tmp_path / "ks"
    ks.mkdir()
    (ks / "PARTNER_SCIENCE_ANNEX.json").write_text("{}", encoding="utf-8")
    (ks / "PARTNER_SCIENCE_ANNEX.md").write_text("a", encoding="utf-8")
    out = tmp_path / "matrix"
    rc = matrix_main(
        [
            "--tokens",
            "probe",
            "--out-root",
            str(out),
            "--dry-run",
            "--attach-known-solutions",
            str(ks),
            "--no-biopython-check",
        ]
    )
    assert rc == 0
    # dry-run: no attach files
    assert not (out / "KNOWN_SOLUTIONS_ATTACH.json").is_file()
