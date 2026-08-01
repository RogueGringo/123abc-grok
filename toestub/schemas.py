"""Free-param / pin_config allowlists, path resolve, and env helpers for ToeStub."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Exact FreeParams field names (realm.job_os.types.FreeParams)
FREE_PARAM_KEYS: frozenset[str] = frozenset(
    {
        "align_mode",
        "window_scale",
        "channel_pack",
        "null_policy",
        "survey_gate",
        "regime_mode",
    }
)

# Pin / JobThresholds keys allowed only via explicit pin_config
PIN_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "depth_mono_eps",
        "max_depth_mono_violations",
        "require_survey",
        "require_regime",
        "min_align_score",
        "survey_total_g_tol",
        "survey_magf_lo",
        "survey_magf_hi",
        "regime_shock_k",
        "science_seed",
    }
)

# Keys that must never appear inside free_params (pin-as-free + dual-gate soft knobs)
_FREE_PARAMS_FORBIDDEN: frozenset[str] = frozenset(
    {
        "pin_writable",
        "depth_mono_eps",
        "soft_T",
        "seq_mix",
        "face_weight",
    }
)


class ToeStubValidationError(ValueError):
    """Invalid free_params, pin_config, or path allow-root check."""


def validate_free_params(d: dict | None) -> dict:
    """Return only allowed FreeParams keys; raise on unknown or forbidden keys."""
    if d is None:
        return {}
    if not isinstance(d, dict):
        raise ToeStubValidationError(f"free_params must be a dict or None, got {type(d).__name__}")
    out: dict[str, Any] = {}
    for key, value in d.items():
        sk = str(key)
        if sk in _FREE_PARAMS_FORBIDDEN or sk not in FREE_PARAM_KEYS:
            raise ToeStubValidationError(
                f"free_params key not allowed: {sk!r} "
                f"(allowed: {sorted(FREE_PARAM_KEYS)}; "
                f"forbidden pin/dual-gate keys must use pin_config)"
            )
        out[sk] = value
    return out


def validate_pin_config(d: dict | None) -> dict:
    """Return only PIN_CONFIG_KEYS; empty dict if None."""
    if d is None:
        return {}
    if not isinstance(d, dict):
        raise ToeStubValidationError(f"pin_config must be a dict or None, got {type(d).__name__}")
    out: dict[str, Any] = {}
    for key, value in d.items():
        sk = str(key)
        if sk not in PIN_CONFIG_KEYS:
            raise ToeStubValidationError(
                f"pin_config key not allowed: {sk!r} (allowed: {sorted(PIN_CONFIG_KEYS)})"
            )
        out[sk] = value
    return out


def get_repo_root() -> Path:
    """Env TOESTUB_REPO_ROOT or current working directory."""
    raw = os.environ.get("TOESTUB_REPO_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve()


def get_timeout_s() -> float:
    """Env TOESTUB_TIMEOUT_S; default 300.0."""
    raw = os.environ.get("TOESTUB_TIMEOUT_S")
    if raw is None or str(raw).strip() == "":
        return 300.0
    try:
        return float(raw)
    except (TypeError, ValueError) as e:
        raise ToeStubValidationError(f"TOESTUB_TIMEOUT_S must be a float, got {raw!r}") from e


def get_allow_roots() -> list[Path] | None:
    """Parse TOESTUB_ALLOW_ROOTS comma-separated; None if unset."""
    raw = os.environ.get("TOESTUB_ALLOW_ROOTS")
    if raw is None or str(raw).strip() == "":
        return None
    roots: list[Path] = []
    for part in str(raw).split(","):
        p = part.strip()
        if not p:
            continue
        roots.append(Path(p).expanduser().resolve())
    return roots if roots else None


def resolve_path(path: str | None, *, repo_root: Path | None = None) -> Path | None:
    """None stays None; absolute returned as-is; relative joined to repo root or cwd."""
    if path is None:
        return None
    p = Path(path).expanduser()
    if p.is_absolute():
        return p
    root = repo_root if repo_root is not None else get_repo_root()
    return root / p


def check_allow_roots(path: Path, allow_roots: list[Path] | None) -> None:
    """Raise if allow_roots is set and path is not under any allowed root."""
    if allow_roots is None:
        return
    if not allow_roots:
        raise ToeStubValidationError("allow_roots is empty; no path is permitted")
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser()
    for root in allow_roots:
        try:
            r = root.expanduser().resolve()
        except OSError:
            r = root.expanduser()
        try:
            resolved.relative_to(r)
            return
        except ValueError:
            continue
    raise ToeStubValidationError(
        f"path {resolved} is not under any allow_roots: {[str(x) for x in allow_roots]}"
    )
