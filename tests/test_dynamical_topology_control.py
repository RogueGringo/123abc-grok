from pathlib import Path
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.types import FreeParams, JobThresholds


def test_topo_stability_off_preserves_solve(tmp_path):
    result = run_job_coherence_loop(
        las_path=Path("tests/fixtures/mini_edr.las"),
        out_root=tmp_path / "off",
        initial=FreeParams(channel_pack="surface_min", regime_mode="persist_h0"),
        thresholds=JobThresholds(),
        max_rounds=3,
        os_mode=True,
        run_id="ctrl_off",
        with_regime=True,
        with_dynamical_topology=False,
        topo_stability=False,
        stability_k=1,
    )
    assert result["solved"] is True


def test_topo_stability_blocks_when_unstable(monkeypatch, tmp_path):
    import realm.dynamical_topology.engine as eng
    monkeypatch.setattr(eng, "topology_stable", lambda *a, **k: False)
    result = run_job_coherence_loop(
        las_path=Path("tests/fixtures/mini_edr.las"),
        out_root=tmp_path / "on",
        initial=FreeParams(channel_pack="surface_min", regime_mode="persist_h0"),
        thresholds=JobThresholds(),
        max_rounds=2,
        os_mode=True,
        run_id="ctrl_on",
        with_regime=True,
        with_dynamical_topology=True,
        topo_stability=True,
        stability_k=1,
    )
    assert result["solved"] is False
