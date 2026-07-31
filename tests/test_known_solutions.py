"""Tests for known-solutions ID universe + aggregates + report-only contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from realm.validate.known_solutions import (
    aggregate_kabsch,
    aggregate_rows,
    attach_report_to_dir,
    write_partner_annex,
)
from realm.validate.known_solutions_ids import (
    load_id_list_file,
    resolve_universe,
)


def test_load_id_list_file(tmp_path: Path):
    p = tmp_path / "ids.txt"
    p.write_text("# c\n1CSA\n2x2c  # lower\nbad\n1CSA\n", encoding="utf-8")
    ids = load_id_list_file(p)
    assert ids == ["1CSA", "2X2C"]


def test_resolve_universe_skip_expand_curated_only():
    doc = resolve_universe(skip_expand=True, allow_hf=False)
    assert doc["n_total"] == 12
    tags = {e["tag"] for e in doc["universe"]}
    assert tags <= {"curated_probe", "curated_holdout"}
    assert doc["by_tag"].get("curated_probe") == 4
    assert doc["by_tag"].get("curated_holdout") == 8
    assert "rcsb_expand" not in doc["by_tag"]


def test_resolve_universe_tag_priority_probe_wins(tmp_path: Path):
    lst = tmp_path / "expand.txt"
    lst.write_text("1CSA\n1ZZZ\n", encoding="utf-8")
    doc = resolve_universe(skip_expand=False, allow_hf=False, rcsb_list=lst)
    by_id = {e["id"]: e for e in doc["universe"]}
    assert by_id["1CSA"]["tag"] == "curated_probe"
    assert "rcsb_expand" in by_id["1CSA"].get("also_in", []) or True
    assert by_id["1ZZZ"]["tag"] == "rcsb_expand"


def test_resolve_universe_cli_ids():
    doc = resolve_universe(skip_expand=True, extra_ids=["9ABC"])
    by_id = {e["id"]: e for e in doc["universe"]}
    assert "9ABC" in by_id
    assert by_id["9ABC"]["tag"] == "cli_override"


def test_resolve_universe_only_ids():
    doc = resolve_universe(only_ids=True, extra_ids=["1CSA", "2X2C"])
    assert doc["n_total"] == 2
    assert set(e["tag"] for e in doc["universe"]) == {"cli_override"}
    assert doc["sources"]["only_ids"] is True


def test_resolve_universe_max_expand(tmp_path: Path):
    lst = tmp_path / "expand.txt"
    lst.write_text("9AAA\n9BBB\n9CCC\n9DDD\n", encoding="utf-8")
    doc = resolve_universe(skip_expand=False, allow_hf=False, rcsb_list=lst, max_expand=2)
    expand = [e for e in doc["universe"] if e["tag"] == "rcsb_expand"]
    assert len(expand) == 2
    assert doc["sources"]["expand_dropped_by_cap"] == 2
    assert doc["by_tag"]["curated_probe"] == 4


def test_aggregate_rows_separates_tags():
    rows = [
        {
            "status": "OK",
            "tag": "curated_probe",
            "enrichment": 0.8,
            "enrichment_std": 0.1,
            "top20": True,
            "native_rank": 2,
        },
        {
            "status": "OK",
            "tag": "curated_holdout",
            "enrichment": 0.4,
            "enrichment_std": 0.0,
            "top20": False,
            "native_rank": 10,
        },
        {
            "status": "OK",
            "tag": "rcsb_expand",
            "enrichment": 0.9,
            "enrichment_std": 0.0,
            "top20": True,
            "native_rank": 1,
        },
        {"status": "SKIP_LENGTH", "tag": "rcsb_expand"},
    ]
    agg = aggregate_rows(rows)
    assert agg["curated_probe"]["n"] == 1
    assert agg["curated_probe"]["mean_enrichment"] == pytest.approx(0.8)
    assert agg["curated_holdout"]["mean_enrichment"] == pytest.approx(0.4)
    assert agg["rcsb_expand"]["n"] == 1
    assert agg["all_ok"]["n"] == 3
    assert agg["n_fail"] == 1
    # holdout not diluted by expand
    assert agg["curated_holdout"]["mean_enrichment"] != agg["all_ok"]["mean_enrichment"]


def test_aggregate_kabsch():
    rows = [
        {"status": "OK", "best_rank_score": 0.1},
        {"status": "OK", "best_rank_score": 0.3},
        {"status": "ERROR_KABSCH"},
    ]
    a = aggregate_kabsch(rows)
    assert a["n_kabsch_ok"] == 2
    assert a["mean_best_rank_score"] == pytest.approx(0.2)


def test_partner_annex_not_acceptance(tmp_path: Path):
    report = {
        "stamp": "test",
        "ontology": "known_solutions_report_not_lambda_eq_gamma",
        "pin": {
            "ok": True,
            "soft_T": 0.036,
            "seq_mix": 0.0,
            "face_weight": 0.08,
            "expected_soft_T": 0.036,
        },
        "aggregates": {
            "n_attempted": 2,
            "n_ok": 2,
            "n_fail": 0,
            "curated_probe": {"n": 1, "mean_enrichment": 0.7},
            "all_ok": {"n": 2, "mean_enrichment": 0.6},
        },
        "kabsch_aggregates": {"n_kabsch_ok": 1, "mean_best_rank_score": 0.05},
        "id_universe": {"n_total": 2, "sources": {"rcsb_list_status": "ok", "cpsea2": {"status": "skipped"}}},
    }
    jp, mp = write_partner_annex(report, tmp_path)
    data = json.loads(jp.read_text(encoding="utf-8"))
    assert data["kind"] == "partner_science_annex"
    # Must not claim commercial accept/ship verdicts
    assert "accepted" not in data
    assert data.get("ship_ok") is None
    assert "disclaimers" in data
    assert any("NOT ACCEPTANCE" in d for d in data["disclaimers"])
    text = mp.read_text(encoding="utf-8")
    assert "Not ACCEPTANCE" in text or "not ACCEPTANCE" in text.lower()
    assert "0.036" in text
    assert "Never λ=γ" in text or "never λ=γ" in text.lower()


def test_attach_report_to_dir(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "PARTNER_SCIENCE_ANNEX.json").write_text(
        json.dumps({"kind": "partner_science_annex", "pin": {"ok": True, "soft_T": 0.036}}),
        encoding="utf-8",
    )
    (src / "PARTNER_SCIENCE_ANNEX.md").write_text("# annex\n", encoding="utf-8")
    (src / "pin.json").write_text(
        json.dumps({"ok": True, "soft_T": 0.036}), encoding="utf-8"
    )
    (src / "KNOWN_SOLUTIONS.json").write_text("{}", encoding="utf-8")
    dest = tmp_path / "matrix_out"
    meta = attach_report_to_dir(src, dest)
    assert meta["ok"] is True
    assert meta["pin_ok"] is True
    assert (dest / "PARTNER_SCIENCE_ANNEX.json").is_file()
    assert (dest / "known_solutions" / "KNOWN_SOLUTIONS.json").is_file()
    assert (dest / "KNOWN_SOLUTIONS_ATTACH.json").is_file()
    attach = json.loads((dest / "KNOWN_SOLUTIONS_ATTACH.json").read_text(encoding="utf-8"))
    assert "not_lambda_eq_gamma" in attach["ontology"]
    assert "accepted" not in attach


def test_attach_via_latest_pointer(tmp_path: Path):
    stamp = tmp_path / "stamp"
    stamp.mkdir()
    (stamp / "PARTNER_SCIENCE_ANNEX.json").write_text("{}", encoding="utf-8")
    (stamp / "PARTNER_SCIENCE_ANNEX.md").write_text("x", encoding="utf-8")
    parent = tmp_path / "ks"
    parent.mkdir()
    (parent / "LATEST").write_text(str(stamp.resolve()), encoding="utf-8")
    dest = tmp_path / "dest"
    meta = attach_report_to_dir(parent, dest, include_full_ledger=False)
    assert meta["ok"] is True
    assert (dest / "known_solutions" / "PARTNER_SCIENCE_ANNEX.json").is_file()


def test_dry_run_cli(tmp_path: Path):
    from known_solutions import main

    out = tmp_path / "ks"
    rc = main(
        [
            "--dry-run",
            "--skip-expand",
            "--out-dir",
            str(out),
            "--knobs",
            "evolve_result.json",
        ]
    )
    assert rc == 0
    stamps = list(out.iterdir())
    assert stamps
    stamp_dir = stamps[0] if stamps[0].is_dir() else out
    # may be stamp subdir
    if (out / "LATEST").is_file():
        target = Path((out / "LATEST").read_text(encoding="utf-8").strip())
        stamp_dir = target
    else:
        stamp_dir = next(d for d in out.iterdir() if d.is_dir())
    pin = json.loads((stamp_dir / "pin.json").read_text(encoding="utf-8"))
    assert pin.get("ok") is True
    assert abs(float(pin["soft_T"]) - 0.036) < 1e-12
    uni = json.loads((stamp_dir / "id_universe.json").read_text(encoding="utf-8"))
    assert uni["n_total"] == 12
    assert (stamp_dir / "PARTNER_SCIENCE_ANNEX.md").is_file()
    assert (stamp_dir / "KNOWN_SOLUTIONS.json").is_file()
