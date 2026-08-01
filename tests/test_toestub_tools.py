from pathlib import Path

from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.types import FreeParams, JobThresholds
from toestub.tools_job import tool_firewall_read, tool_job_audit, tool_job_catalog

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_edr.las"


def test_firewall_read_and_audit_after_run(tmp_path):
    result = run_job_coherence_loop(
        las_path=FIXTURE,
        out_root=tmp_path / "os",
        initial=FreeParams(channel_pack="surface_min"),
        thresholds=JobThresholds(),
        max_rounds=4,
        os_mode=True,
        stability_k=1,
    )
    assert result["solved"] is True
    fr = tool_firewall_read(result["out_root"])
    assert fr["ok"] is True
    assert fr["certified"] is True
    assert fr["pin_writable"] is False
    au = tool_job_audit(result["out_root"])
    assert au["ok"] is True


def test_catalog(tmp_path):
    # run one job under tmp_path first or empty catalog
    cat = tool_job_catalog(str(tmp_path))
    assert cat["ok"] is True
    assert cat["certified"] is None
