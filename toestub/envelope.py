"""ToeStub response envelope builder with explore not_acceptance guard."""

from __future__ import annotations

from typing import Any


def build_envelope(
    *,
    ok: bool,
    surface: str,
    certified: bool | None = None,
    near_miss: bool | None = None,
    branch: str | None = None,
    paths: dict | None = None,
    explore: dict | None = None,
    error: str | None = None,
    extra: dict | None = None,
) -> dict[str, Any]:
    """Build a ToeStub response envelope.

    Always sets top-level ``pin_writable=False`` and
    ``ontology="toestub_envelope_v1"``. If ``explore`` is provided, forces
    ``not_acceptance=True`` and ``pin_writable=False`` on the explore payload.
    """
    explore_out: dict[str, Any] | None = None
    if explore is not None:
        explore_out = dict(explore)
        explore_out["not_acceptance"] = True
        explore_out["pin_writable"] = False

    env: dict[str, Any] = {
        "ok": ok,
        "surface": surface,
        "certified": certified,
        "near_miss": near_miss,
        "branch": branch,
        "paths": paths,
        "explore": explore_out,
        "error": error,
        "pin_writable": False,
        "ontology": "toestub_envelope_v1",
    }
    if extra:
        env.update(extra)
    return env
