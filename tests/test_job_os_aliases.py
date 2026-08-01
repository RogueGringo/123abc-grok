"""C6 channel aliases — inherited dictionary, never invent samples."""

from __future__ import annotations

from pathlib import Path

from realm.job_os.aliases import apply_channel_aliases
from realm.job_os.ingest_las import parse_las
from realm.job_os.pin import verify_job_pin

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_edr.las"


def test_wobx_aliases_to_wob_for_pin():
    series = {
        "depths": [1000.0, 1001.0, 1002.0],
        "channels": {
            "DEPT": [1000.0, 1001.0, 1002.0],
            "WOBX": [10.0, 11.0, 12.0],
            "RPM": [60.0, 61.0, 62.0],
        },
        "units": {"WOBX": "KLBF", "RPM": "RPM"},
        "n_rows": 3,
    }
    # Without alias, pin misses WOB
    pin0 = verify_job_pin(series, pack="surface_min")
    assert pin0["ok"] is False
    assert "WOB" in pin0["missing_channels"]

    aliased = apply_channel_aliases(series)
    assert "WOB" in aliased["channels"]
    assert aliased["channels"]["WOB"] == [10.0, 11.0, 12.0]
    assert any(a["canonical"] == "WOB" and a["from"] == "WOBX" for a in aliased["alias_applied"])
    pin1 = verify_job_pin(aliased, pack="surface_min")
    assert pin1["ok"] is True
    assert pin1["depth_mono_ok"] is True


def test_alias_does_not_overwrite_canonical():
    series = {
        "depths": [1.0, 2.0],
        "channels": {
            "DEPT": [1.0, 2.0],
            "WOB": [5.0, 6.0],
            "WOBX": [99.0, 99.0],
            "RPM": [1.0, 1.0],
        },
        "n_rows": 2,
    }
    out = apply_channel_aliases(series)
    assert out["channels"]["WOB"] == [5.0, 6.0]
    assert not any(a["canonical"] == "WOB" for a in out["alias_applied"])


def test_alias_never_invents_missing():
    series = {
        "depths": [1.0, 2.0],
        "channels": {"DEPT": [1.0, 2.0], "RPM": [1.0, 1.0]},
        "n_rows": 2,
    }
    out = apply_channel_aliases(series)
    assert "WOB" not in out["channels"]
    pin = verify_job_pin(out, pack="surface_min")
    assert pin["ok"] is False


def test_fixture_unchanged_after_alias():
    raw = parse_las(FIXTURE)
    out = apply_channel_aliases(raw)
    pin = verify_job_pin(out, pack="surface_min")
    assert pin["ok"] is True
    # mini fixture already has WOB — no alias needed for WOB
    assert not any(a["canonical"] == "WOB" for a in out.get("alias_applied") or [])


def test_gamma_and_tor_aliases():
    series = {
        "depths": [1.0, 2.0],
        "channels": {
            "DEPT": [1.0, 2.0],
            "WOB": [1.0, 1.0],
            "RPM": [1.0, 1.0],
            "TQA": [2.0, 3.0],
            "SPPA": [100.0, 101.0],
            "GAM": [40.0, 41.0],
        },
        "n_rows": 2,
    }
    out = apply_channel_aliases(series)
    assert out["channels"]["TOR"] == [2.0, 3.0]
    assert out["channels"]["SPP"] == [100.0, 101.0]
    assert out["channels"]["GAMMA"] == [40.0, 41.0]
