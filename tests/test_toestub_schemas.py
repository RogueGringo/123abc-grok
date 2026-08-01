# tests/test_toestub_schemas.py
from pathlib import Path
import pytest
from toestub.schemas import (
    validate_free_params,
    validate_pin_config,
    ToeStubValidationError,
    resolve_path,
    check_allow_roots,
)


def test_free_params_accepts_closed_set():
    out = validate_free_params({"channel_pack": "surface_min", "align_mode": "depth_primary"})
    assert out["channel_pack"] == "surface_min"


def test_free_params_rejects_unknown():
    with pytest.raises(ToeStubValidationError):
        validate_free_params({"depth_mono_eps": 1e-3})


def test_free_params_rejects_pin_writable():
    with pytest.raises(ToeStubValidationError):
        validate_free_params({"pin_writable": True})


def test_pin_config_accepts_mono_violations():
    out = validate_pin_config({"max_depth_mono_violations": 5})
    assert out["max_depth_mono_violations"] == 5


def test_pin_config_rejects_channel_pack():
    with pytest.raises(ToeStubValidationError):
        validate_pin_config({"channel_pack": "surface_min"})


def test_resolve_relative(tmp_path, monkeypatch):
    monkeypatch.setenv("TOESTUB_REPO_ROOT", str(tmp_path))
    p = resolve_path("tests/fixtures/mini_edr.las")
    assert p == tmp_path / "tests/fixtures/mini_edr.las"


def test_allow_roots_blocks(tmp_path):
    outside = Path("C:/Windows") if Path("C:/Windows").exists() else tmp_path.parent
    with pytest.raises(ToeStubValidationError):
        check_allow_roots(outside / "x.las", [tmp_path])
