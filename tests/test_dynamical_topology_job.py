from pathlib import Path
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.types import FreeParams, JobThresholds
import json


def test_job_loop_writes_dynamical_topology(tmp_path):
    result = run_job_coherence_loop(
        las_path=Path("tests/fixtures/mini_edr.las"),
        out_root=tmp_path / "j",
        initial=FreeParams(channel_pack="surface_min", regime_mode="persist_h0"),
        thresholds=JobThresholds(),
        max_rounds=2,
        os_mode=True,
        run_id="dt1",
        with_regime=True,
        with_dynamical_topology=True,
        stability_k=1,
    )
    root = Path(result["out_root"])
    p = root / "DYNAMICAL_TOPOLOGY.json"
    if not p.is_file():
        found = list(root.glob("cycle_*/DYNAMICAL_TOPOLOGY.json"))
        assert found, "missing dynamical topology report"
        p = found[0]
    body = json.loads(p.read_text(encoding="utf-8"))
    assert body["not_acceptance"] is True
    assert body["pin_writable"] is False
