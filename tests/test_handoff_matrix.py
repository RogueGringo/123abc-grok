"""Handoff matrix dry-run smoke."""

from __future__ import annotations

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
