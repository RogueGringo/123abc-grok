"""Job OS run catalog INDEX."""

from __future__ import annotations

import json
from pathlib import Path

from realm.job_os.catalog import scan_job_os_runs, write_job_os_catalog
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.types import FreeParams, JobThresholds


def test_catalog_after_runs(tmp_path: Path):
    parent = tmp_path / "job_os"
    for rid in ("a", "b"):
        run_job_coherence_loop(
            las_path=Path("tests/fixtures/mini_edr.las"),
            out_root=parent,
            initial=FreeParams(channel_pack="surface_min", regime_mode="persist_h0"),
            thresholds=JobThresholds(),
            max_rounds=2,
            os_mode=True,
            run_id=rid,
            with_regime=True,
            stability_k=1,
        )
    cat = write_job_os_catalog(parent)
    assert cat["n_runs"] >= 2
    assert cat["n_solved"] >= 1
    assert cat["not_acceptance"] is True
    assert (parent / "INDEX.json").is_file()
    assert (parent / "INDEX.md").is_file()
    body = json.loads((parent / "INDEX.json").read_text(encoding="utf-8"))
    assert any(r.get("partner_recipe") for r in body["runs"])


def test_scan_empty(tmp_path: Path):
    assert scan_job_os_runs(tmp_path) == []
