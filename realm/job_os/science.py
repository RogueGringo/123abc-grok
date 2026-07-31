"""Science-info channel for Job Coherence OS P4 (dual-gate windows).

Native windowed regime barcode vs time-scramble decoy under locked pin.
**Informational only** — never sets SOLVED / ACCEPTANCE / SHIP alone.

Triggered by ``--with-science`` and/or ``regime_mode=dual_gate_windows``.
"""

from __future__ import annotations

import random
from typing import Any

from realm.job_os.regime import (
    channel_h0_summary,
    resolve_regime_channels,
    structure_score,
)


def _scramble_list(vals: list[float], rng: random.Random) -> list[float]:
    """Time-scramble (shuffle) a 1-D series in place-copy."""
    out = list(vals)
    rng.shuffle(out)
    return out


def dual_gate_windows(
    series: dict[str, Any] | None,
    *,
    window_scale: int = 1,
    seed: int = 42,
    pin_ok: bool | None = None,
) -> dict[str, Any]:
    """Native vs time-scramble decoy structure scores on regime channels.

    Pin is reported as context only (must already be locked by the OS);
    this function never retunes pin thresholds.
    """
    ws = max(1, int(window_scale))
    channels = (series or {}).get("channels") or {}
    native_chs = resolve_regime_channels(channels)

    notes: list[str] = []
    if not native_chs:
        notes.append("science_no_regime_channels")
        return {
            "enabled": True,
            "kind": "dual_gate_windows",
            "informational_only": True,
            "window_scale": ws,
            "seed": int(seed),
            "pin_ok_context": pin_ok,
            "channels_used": [],
            "native": {"channel_summaries": {}, "structure_score": 0.0},
            "decoy": {
                "kind": "time_scramble",
                "channel_summaries": {},
                "structure_score": 0.0,
            },
            "native_score": 0.0,
            "decoy_score": 0.0,
            "native_beats_decoy": False,
            "margin": 0.0,
            "notes": notes,
            "ontology": "job_science_info_not_acceptance",
            "disclaimers": [
                "Science annex is informational only.",
                "Never sets SOLVED / ACCEPTANCE / SHIP alone.",
                "Never retunes QC pin for score.",
            ],
        }

    rng = random.Random(int(seed))

    native_summaries: dict[str, dict[str, Any]] = {}
    decoy_summaries: dict[str, dict[str, Any]] = {}
    for name, vals in native_chs.items():
        native_summaries[name] = channel_h0_summary(vals, window_scale=ws)
        decoy_summaries[name] = channel_h0_summary(
            _scramble_list(vals, rng), window_scale=ws
        )

    native_score = structure_score(native_summaries)
    decoy_score = structure_score(decoy_summaries)
    margin = float(native_score - decoy_score)
    beats = native_score > decoy_score + 1e-12

    notes.append(f"channels:{','.join(sorted(native_chs))}")
    notes.append(f"native={native_score:.4f}")
    notes.append(f"decoy_scramble={decoy_score:.4f}")
    notes.append("native_beats_decoy" if beats else "decoy_not_beaten")

    return {
        "enabled": True,
        "kind": "dual_gate_windows",
        "informational_only": True,
        "window_scale": ws,
        "seed": int(seed),
        "pin_ok_context": pin_ok,
        "channels_used": sorted(native_chs.keys()),
        "native": {
            "channel_summaries": native_summaries,
            "structure_score": float(native_score),
            "barcode_n_bars": int(
                sum(int(s.get("barcode_n_bars") or 0) for s in native_summaries.values())
            ),
        },
        "decoy": {
            "kind": "time_scramble",
            "channel_summaries": decoy_summaries,
            "structure_score": float(decoy_score),
            "barcode_n_bars": int(
                sum(int(s.get("barcode_n_bars") or 0) for s in decoy_summaries.values())
            ),
        },
        "native_score": float(native_score),
        "decoy_score": float(decoy_score),
        "native_beats_decoy": bool(beats),
        "margin": margin,
        "notes": notes,
        "ontology": "job_science_info_not_acceptance",
        "disclaimers": [
            "Science annex is informational only.",
            "Never sets SOLVED / ACCEPTANCE / SHIP alone.",
            "Never retunes QC pin for score.",
            "Decoy = time-scramble of same channels under locked pin context.",
        ],
    }


def evaluate_science(
    series: dict[str, Any] | None,
    *,
    regime_mode: str = "off",
    window_scale: int = 1,
    with_science: bool = False,
    pin_ok: bool | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Science annex when ``--with-science`` or ``regime_mode=dual_gate_windows``."""
    mode = str(regime_mode or "off").lower().strip()
    run = bool(with_science) or mode == "dual_gate_windows"
    if not run:
        return {
            "enabled": False,
            "kind": None,
            "informational_only": True,
            "native_score": None,
            "decoy_score": None,
            "native_beats_decoy": None,
            "notes": ["science_off"],
            "ontology": "job_science_info_not_acceptance",
        }
    return dual_gate_windows(
        series,
        window_scale=window_scale,
        seed=seed,
        pin_ok=pin_ok,
    )
