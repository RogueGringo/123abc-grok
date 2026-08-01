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


def test_job_run_fixture_certified(tmp_path):
    from toestub.tools_job import tool_job_run
    env = tool_job_run(
        las_path=str(FIXTURE),
        out_root=str(tmp_path / "run"),
        max_rounds=4,
        free_params={"channel_pack": "surface_min"},
    )
    assert env["ok"] is True
    assert env["certified"] is True
    assert Path(env["paths"]["firewall"]).is_file()


def test_job_run_rejects_pin_in_free(tmp_path):
    from toestub.tools_job import tool_job_run
    env = tool_job_run(
        las_path=str(FIXTURE),
        out_root=str(tmp_path / "bad"),
        free_params={"depth_mono_eps": 0.1},
    )
    assert env["ok"] is False
    assert "free" in (env.get("error") or "").lower() or "valid" in (env.get("error") or "").lower()
