"""Coherence protocol unit tests (negotiate + observe; no full export)."""

from __future__ import annotations

from realm.handoff.coherence import (
    CoherenceThresholds,
    FreeParams,
    Observations,
    coherence_score,
    is_solved,
    negotiate,
    observe,
)


def test_free_params_clamp():
    p = FreeParams(decorate="weird", physics="nope", top_k=99).clamp()
    assert p.decorate == "sequence"
    assert p.physics == "geometry"
    assert p.top_k == 8


def test_is_solved_and_score():
    thr = CoherenceThresholds()
    params = FreeParams(decorate="sequence", physics="geometry", top_k=2)
    good = Observations(
        pin_ok=True,
        soft_T=0.036,
        n_ids=1,
        n_export_ok=1,
        n_pdb_ontology=4,
        verify_ok=True,
        decorate_n_ok=2,
        decorate_n_molds=2,
        decorate_n_paths=2,
        physics_n_ok=2,
        physics_n_warn=0,
        physics_n_fail=0,
        out_dir="/tmp",
    )
    assert is_solved(good, thr, params) is True
    assert coherence_score(good, thr, params) > 0.9

    bad = Observations(
        pin_ok=True,
        soft_T=0.036,
        n_ids=1,
        n_export_ok=1,
        n_pdb_ontology=4,
        verify_ok=True,
        decorate_n_ok=0,
        decorate_n_molds=2,
        decorate_n_paths=0,
        physics_n_ok=0,
        physics_n_warn=0,
        physics_n_fail=0,
        out_dir="/tmp",
        notes=["decorate_zero"],
    )
    assert is_solved(bad, thr, params) is False


def test_negotiate_enable_sequence():
    thr = CoherenceThresholds(require_decorate=True)
    params = FreeParams(decorate="null", physics="geometry", top_k=2)
    obs = Observations(
        pin_ok=True,
        soft_T=0.036,
        n_ids=1,
        n_export_ok=1,
        n_pdb_ontology=2,
        verify_ok=True,
        decorate_n_ok=0,
        decorate_n_molds=0,
        decorate_n_paths=0,
        physics_n_ok=2,
        physics_n_warn=0,
        physics_n_fail=0,
        out_dir="/tmp",
        notes=["decorate_zero"],
    )
    assert is_solved(obs, thr, params) is False
    tried: set[str] = set()
    nxt, reason, board = negotiate(obs, params, thr, tried=tried)
    assert nxt is not None
    assert nxt.decorate == "sequence"
    assert "sequence" in reason
    assert board and board[0]["section"] == "decorate"


def test_negotiate_never_suggests_pin_change_on_pin_fail():
    thr = CoherenceThresholds()
    params = FreeParams(decorate="null", physics="geometry", top_k=2)
    obs = Observations(
        pin_ok=False,
        soft_T=0.04,
        n_ids=1,
        n_export_ok=0,
        n_pdb_ontology=0,
        verify_ok=False,
        decorate_n_ok=0,
        decorate_n_molds=0,
        decorate_n_paths=0,
        physics_n_ok=0,
        physics_n_warn=0,
        physics_n_fail=0,
        out_dir="/tmp",
        notes=["pin_fail"],
    )
    nxt, reason, board = negotiate(obs, params, thr, tried=set())
    assert nxt is None
    assert "pin" in reason
    assert board == []


def test_multi_section_merge_priority():
    from realm.handoff.coherence import collect_section_proposals, merge_proposals

    thr = CoherenceThresholds(require_decorate=True, max_physics_fail=0)
    params = FreeParams(decorate="null", physics="geometry", top_k=2)
    obs = Observations(
        pin_ok=True,
        soft_T=0.036,
        n_ids=2,
        n_export_ok=1,  # incomplete export
        n_pdb_ontology=2,
        verify_ok=True,
        decorate_n_ok=0,
        decorate_n_molds=0,
        decorate_n_paths=0,
        physics_n_ok=0,
        physics_n_warn=0,
        physics_n_fail=1,  # physics wants a move too
        out_dir="/tmp",
        notes=["export_incomplete", "physics_fail", "decorate_zero"],
    )
    tried: set[str] = set()
    props = collect_section_proposals(obs, params, thr, tried=tried)
    sections = {p.section for p in props}
    assert "export" in sections or "decorate" in sections or "physics" in sections
    nxt, reason, board = merge_proposals(props, params)
    assert nxt is not None
    assert reason.startswith("merge[")
    assert len(board) >= 1
    # export priority beats decorate/science when both present
    if any(p.section == "export" for p in props):
        assert "export" in reason


def test_observe_from_summary():
    pin = {"ok": True, "soft_T": 0.036}
    summary = {
        "n_ids": 2,
        "n_ok": 2,
        "decorate_rollup": {"n_ok": 4, "n_with_path": 4, "n_molds": 4},
        "physics_rollup": {"n_ok": 4, "n_warn": 0, "n_fail": 0},
    }
    v = {"ok": True, "ontology_remarks": {"n_pdb": 8}}
    obs = observe(pin=pin, export_summary=summary, verify_report=v, out_dir="/x")
    assert obs.pin_ok and obs.n_export_ok == 2
    assert obs.decorate_n_ok == 4
    assert obs.physics_n_fail == 0


def test_run_genotype_phase_structure():
    """Genotype phase returns pin-safe report shape (may be slow if network)."""
    from realm.handoff.coherence import run_genotype_phase

    # Minimal knobs dict — may skip if Keymaker/probe fails in offline env
    knobs = {
        "Lambda": 1.0,
        "omega_scale": 1.0,
        "weight_power": 1.0,
        "tier_split": 0.45,
        "low_boost": 1.0,
        "w1_mult": 1.0,
        "w2_mult": 1.0,
        "w3_mult": 1.0,
    }
    try:
        rep = run_genotype_phase(
            knobs,
            probe_ids=["1CSA"],
            n_zeros=14,
            n_pop=2,
            n_epochs=1,
            n_decoys=4,
        )
    except Exception as exc:  # noqa: BLE001
        import pytest

        pytest.skip(f"genotype phase unavailable: {exc}")
    assert rep.get("ran") is True
    assert "baseline_probe_enrichment" in rep
    assert "champion_knobs" in rep
    assert "not_lambda" in (rep.get("ontology") or "") or "not_lambda" in (
        rep.get("note") or ""
    )


def test_partner_recipe_shape(tmp_path):
    from realm.handoff.coherence import FreeParams, write_partner_recipe

    path = write_partner_recipe(
        tmp_path / "PARTNER_RECIPE.json",
        pin={"ok": True, "soft_T": 0.036, "seq_mix": 0.0, "face_weight": 0.08},
        free_params=FreeParams(decorate="sequence", physics="geometry", top_k=2),
        run_id="test_run",
        pdb_ids=["1CSA"],
        solved=True,
    )
    import json

    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["kind"] == "partner_recipe"
    assert body["pin"]["expected_soft_T"] == 0.036
    assert body["free_params"]["decorate"] == "sequence"
    assert "not_lambda" in body["ontology"]
    assert "Not ACCEPTANCE" in body["disclaimers"][1]


def test_fixed_point_k_requires_empty_board():
    """is_solved alone is not fixed-point when free moves remain (negotiate path)."""
    thr = CoherenceThresholds(require_decorate=True)
    # null decorate is NOT solved when require_decorate
    params = FreeParams(decorate="null", physics="geometry", top_k=2)
    obs = Observations(
        pin_ok=True,
        soft_T=0.036,
        n_ids=1,
        n_export_ok=1,
        n_pdb_ontology=2,
        verify_ok=True,
        decorate_n_ok=0,
        decorate_n_molds=0,
        decorate_n_paths=0,
        physics_n_ok=2,
        physics_n_warn=0,
        physics_n_fail=0,
        out_dir="/tmp",
    )
    assert is_solved(obs, thr, params) is False
    nxt, reason, board = negotiate(obs, params, thr, tried=set())
    assert nxt is not None and board


def test_load_resume_state(tmp_path):
    import json

    from realm.handoff.coherence import load_resume_state

    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "RUN.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "max_rounds": 6,
                "stability_k": 2,
                "final_params": {
                    "decorate": "sequence",
                    "physics": "geometry",
                    "top_k": 2,
                },
                "thresholds": {},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "ledger.jsonl").write_text(
        json.dumps(
            {
                "round": 1,
                "params": {"decorate": "null", "physics": "geometry", "top_k": 2},
                "next_params": {
                    "decorate": "sequence",
                    "physics": "geometry",
                    "top_k": 2,
                },
                "stability_streak": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    state = load_resume_state(run_dir)
    assert state["run"]["run_id"] == "run1"
    assert len(state["ledger"]) == 1
    assert state["ledger"][0]["next_params"]["decorate"] == "sequence"


def test_os_run_identity_artifacts(tmp_path, monkeypatch):
    """OS mode writes RUN.json + ledger.jsonl without full export (mocked)."""
    import json
    from pathlib import Path

    from realm.handoff import coherence as coh

    def fake_export(ids, knobs, **kwargs):
        out = Path(kwargs["out_root"])
        out.mkdir(parents=True, exist_ok=True)
        (out / "batch_index.json").write_text("{}", encoding="utf-8")
        return {
            "n_ids": 1,
            "n_ok": 1,
            "decorate_rollup": {
                "n_ok": 2,
                "n_with_path": 2,
                "n_molds": 2,
            },
            "physics_rollup": {"n_ok": 2, "n_warn": 0, "n_fail": 0},
            "rows": [],
        }

    def fake_verify(tree, **kwargs):
        return {"ok": True, "ontology_remarks": {"n_pdb": 4}}

    def fake_pin():
        return {
            "ok": True,
            "soft_T": 0.036,
            "seq_mix": 0.0,
            "face_weight": 0.08,
        }

    monkeypatch.setattr(
        "realm.handoff.pipeline.export_structure_batch", fake_export
    )
    monkeypatch.setattr(coh, "verify_handoff_tree", fake_verify)
    monkeypatch.setattr(coh, "verify_dual_gate_pin", fake_pin)

    result = coh.run_coherence_loop(
        pdb_ids=["1CSA"],
        knobs={"Lambda": 1.0},
        out_root=tmp_path / "os_parent",
        initial=FreeParams(decorate="sequence", physics="geometry", top_k=2),
        thresholds=CoherenceThresholds(require_decorate=True),
        max_rounds=3,
        verify=True,
        os_mode=True,
        stability_k=1,
        run_id="test_os_run",
    )
    assert result["solved"] is True
    assert result["os_mode"] is True
    assert result["run_id"] == "test_os_run"
    run_dir = Path(result["out_root"])
    assert (run_dir / "RUN.json").is_file()
    assert (run_dir / "ledger.jsonl").is_file()
    assert (run_dir / "PARTNER_RECIPE.json").is_file()
    assert (run_dir / "COHERENCE.json").is_file()
    run = json.loads((run_dir / "RUN.json").read_text(encoding="utf-8"))
    assert run["status"] == "solved"
    assert run["pin_locked"]["soft_T_n12"] == 0.036
    lines = [
        ln
        for ln in (run_dir / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert len(lines) >= 1
    recipe = json.loads((run_dir / "PARTNER_RECIPE.json").read_text(encoding="utf-8"))
    assert recipe["free_params"]["decorate"] == "sequence"
    latest = json.loads(
        (tmp_path / "os_parent" / "LATEST").read_text(encoding="utf-8")
    )
    assert latest["run_id"] == "test_os_run"


def test_stability_k2_needs_two_holds(tmp_path, monkeypatch):
    """K=2 requires two consecutive is_solved ∧ empty-board cycles."""
    from pathlib import Path

    from realm.handoff import coherence as coh

    calls = {"n": 0}

    def fake_export(ids, knobs, **kwargs):
        calls["n"] += 1
        out = Path(kwargs["out_root"])
        out.mkdir(parents=True, exist_ok=True)
        return {
            "n_ids": 1,
            "n_ok": 1,
            "decorate_rollup": {"n_ok": 2, "n_with_path": 2, "n_molds": 2},
            "physics_rollup": {"n_ok": 2, "n_warn": 0, "n_fail": 0},
            "rows": [],
        }

    monkeypatch.setattr(
        "realm.handoff.pipeline.export_structure_batch", fake_export
    )
    monkeypatch.setattr(
        coh,
        "verify_handoff_tree",
        lambda *a, **k: {"ok": True, "ontology_remarks": {"n_pdb": 4}},
    )
    monkeypatch.setattr(
        coh,
        "verify_dual_gate_pin",
        lambda: {
            "ok": True,
            "soft_T": 0.036,
            "seq_mix": 0.0,
            "face_weight": 0.08,
        },
    )

    result = coh.run_coherence_loop(
        pdb_ids=["1CSA"],
        knobs={"Lambda": 1.0},
        out_root=tmp_path / "k2",
        initial=FreeParams(decorate="sequence", physics="geometry", top_k=2),
        thresholds=CoherenceThresholds(require_decorate=True),
        max_rounds=5,
        verify=True,
        os_mode=True,
        stability_k=2,
        run_id="k2_run",
    )
    assert result["solved"] is True
    assert result["n_rounds"] == 2
    assert calls["n"] == 2
    actions = [e.get("action") for e in result["ledger"] if isinstance(e.get("round"), int)]
    assert "stability_hold" in actions
    assert "halt" in actions
