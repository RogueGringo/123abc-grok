"""Trend rollup + ledger λ1 fields (info only)."""

from __future__ import annotations

import json
from pathlib import Path

from realm.job_os.loop import build_trend_rollup, run_job_coherence_loop
from realm.job_os.types import FreeParams, JobThresholds


def test_build_trend_rollup_direction():
    ledger = [
        {"round": 1, "trend": {"graph_lambda_1": 0.1}},
        {"round": 2, "trend": {"graph_lambda_1": 0.2}},
        {"round": "genotype", "trend": {}},
    ]
    r = build_trend_rollup(ledger)
    assert r["not_acceptance"] is True
    assert r["lambda_1_trend"] == "non_decreasing"
    assert r["lambda_1_delta"] is not None and r["lambda_1_delta"] > 0


def test_build_trend_rollup_decreasing():
    ledger = [
        {"round": 1, "trend": {"graph_lambda_1": 0.5}},
        {"round": 2, "trend": {"graph_lambda_1": 0.1}},
    ]
    r = build_trend_rollup(ledger)
    assert r["lambda_1_trend"] == "decreasing"


def test_job_loop_writes_trend_rollup(tmp_path):
    result = run_job_coherence_loop(
        las_path=Path("tests/fixtures/mini_edr.las"),
        out_root=tmp_path / "tr",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_min",
            regime_mode="persist_h0",
            window_scale=1,
        ),
        thresholds=JobThresholds(require_pin=True),
        max_rounds=2,
        os_mode=True,
        run_id="trend1",
        with_regime=True,
        with_science=True,
        stability_k=1,
    )
    root = Path(result["out_root"])
    assert (root / "TREND_ROLLUP.json").is_file()
    body = json.loads((root / "TREND_ROLLUP.json").read_text(encoding="utf-8"))
    assert body["not_acceptance"] is True
    assert body["n_cycles"] >= 1
    # ledger entry has trend block
    coh = json.loads((root / "COHERENCE.json").read_text(encoding="utf-8"))
    cycle_entries = [e for e in coh["ledger"] if isinstance(e.get("round"), int)]
    assert cycle_entries
    assert "trend" in cycle_entries[0]
    assert cycle_entries[0]["trend"]["not_acceptance"] is True
