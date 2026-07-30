"""JSON report helpers for validation ladder CLIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(path: Path | str, payload: dict[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def load_knobs(path: Path | str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("best_knobs") or data.get("meet_knobs") or data.get("knobs") or data
