"""Job Coherence OS free params, thresholds, observations, proposals.

Pin fields are NEVER part of FreeParams. Proposals must not carry pin knobs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Free-parameter domains (closed sets — no open-ended retune of QC pin)
ALIGN_MODES = ("none", "depth_primary", "time_primary", "survey_anchor")
WINDOW_SCALE_BOUNDS = (1, 8)
CHANNEL_PACKS = ("surface_min", "surface_full", "mwd_full", "job_union")
NULL_POLICIES = ("drop", "hold_last", "mark_only")
SURVEY_GATES = ("off", "qc_only", "holonomy")  # P3 stalk; default off in P1
REGIME_MODES = ("off", "persist_h0", "dual_gate_windows")  # P4 stalk; default off

# Required channels per pack (uppercase curve mnemonics).
# P2: mwd_full / job_union require downhole MicroPulse fibers (GAMMA/SHOCK/VIBE…).
# surface_* remain surface-only so LAS-only jobs still solve without MP.
PACK_REQUIRED: dict[str, tuple[str, ...]] = {
    "surface_min": ("DEPT", "WOB", "RPM"),
    "surface_full": ("DEPT", "WOB", "RPM", "TOR", "SPP", "SSSI"),
    "mwd_full": ("DEPT", "WOB", "RPM", "TOR", "SPP", "GAMMA"),
    "job_union": (
        "DEPT",
        "WOB",
        "RPM",
        "TOR",
        "SPP",
        "SSSI",
        "GAMMA",
        "SHOCK",
        "VIBE",
    ),
}

# Downhole mnemonics recognized for pack / select (MicroPulse join)
DOWNHOLE_PACK_CHANNELS = ("GAMMA", "SHOCK", "VIBE", "PULSE", "TELEM", "TEMP", "FLOW")

# Merge priority: lower number wins when proposals conflict
SECTION_PRIORITY = {
    "pin": 0,  # only abort; never param
    "export": 1,
    "verify": 2,
    "align": 3,
    "survey": 4,  # P3
    "physics": 5,
    "regime": 6,  # P4
    "science": 7,
}


@dataclass
class FreeParams:
    """Negotiable job-routine knobs (not QC pin / SOP thresholds)."""

    align_mode: str = "depth_primary"
    window_scale: int = 1
    channel_pack: str = "surface_min"
    null_policy: str = "mark_only"
    # Stalks defaulted off for later PRs; present as fields for recipe stability
    survey_gate: str = "off"
    regime_mode: str = "off"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def clamp(self) -> FreeParams:
        am = str(self.align_mode or "depth_primary").lower().strip()
        if am not in ALIGN_MODES:
            am = "depth_primary"
        ws = int(self.window_scale)
        ws = max(WINDOW_SCALE_BOUNDS[0], min(WINDOW_SCALE_BOUNDS[1], ws))
        cp = str(self.channel_pack or "surface_min").lower().strip()
        if cp not in CHANNEL_PACKS:
            cp = "surface_min"
        np_ = str(self.null_policy or "mark_only").lower().strip()
        if np_ not in NULL_POLICIES:
            np_ = "mark_only"
        sg = str(self.survey_gate or "off").lower().strip()
        if sg not in SURVEY_GATES:
            sg = "off"
        rm = str(self.regime_mode or "off").lower().strip()
        if rm not in REGIME_MODES:
            rm = "off"
        return FreeParams(
            align_mode=am,
            window_scale=ws,
            channel_pack=cp,
            null_policy=np_,
            survey_gate=sg,
            regime_mode=rm,
        )


@dataclass
class JobThresholds:
    """What 'solved' means for the commercial job routine (not ROP score)."""

    min_export_ok_fraction: float = 1.0
    max_physics_fail: int = 0
    min_align_score: float = 0.5
    require_verify_ok: bool = True
    require_pin: bool = True
    depth_mono_eps: float = 1e-6  # pin config (locked for a run — not free)
    require_align: bool = False  # if True, align_mode=none not coherent for multi-src

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Observations:
    """What the cycle measured after one execute (ingest/align/pin/physics)."""

    pin_ok: bool
    n_rows: int
    n_channels: int
    n_required: int
    n_required_present: int
    export_ok_fraction: float
    verify_ok: bool | None
    align_score: float
    physics_n_ok: int
    physics_n_warn: int
    physics_n_fail: int
    depth_mono_ok: bool
    unit_sanity_ok: bool
    out_dir: str
    notes: list[str] = field(default_factory=list)
    # Optional stalk channels (informational / later PRs)
    survey_n_stations: int = 0
    survey_qc_fail: int = 0
    regime_note: str | None = None
    # P2 MicroPulse / multi-source glue (structural — not ROP score)
    has_micropulse: bool = False
    glue_score: float = 0.0
    glue_method: str | None = None
    mp_n_fibers: int = 0
    mp_kinds: list[str] = field(default_factory=list)
    glue_notes: list[str] = field(default_factory=list)
    # Domain availability for honest align free-param proposals
    glue_has_depth_domain: bool = False
    glue_has_time_domain: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SectionProposal:
    """One section's proposed free-param move (never pin)."""

    section: str
    params: FreeParams
    reason: str
    priority: int = 99

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "params": self.params.to_dict(),
            "reason": self.reason,
            "priority": self.priority,
        }


# Pin field names that must never appear in proposals / free-param dicts
PIN_FORBIDDEN_KEYS = frozenset(
    {
        "depth_mono_eps",
        "soft_T",
        "seq_mix",
        "face_weight",
        "sop",
        "pin",
        "qc_band",
        "unit_convert_force",
    }
)
