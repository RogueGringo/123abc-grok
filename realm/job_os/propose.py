"""Multi-section free-param propose + merge for Job Coherence OS.

Sections: export | verify | align | survey (P3) | physics
Merge ranks by priority; never proposes pin retune.

Priority (lower wins): export=1, verify=2, align=3, survey=4, physics=5

Hard pin (depth mono / unit sanity) is never negotiable.
Pack-completeness pin fails may negotiate channel_pack / null_policy only.
window_scale is a free-param field (recipe stability / later stalks) but is
not proposed until a stalk consumes it (honest free board).
P3 survey: survey_gate upgrades + survey_anchor when survey present/glue weak.
"""

from __future__ import annotations

import json
from typing import Any

from realm.job_os.types import (
    ALIGN_MODES,
    CHANNEL_PACKS,
    NULL_POLICIES,
    PIN_FORBIDDEN_KEYS,
    SECTION_PRIORITY,
    SURVEY_GATES,
    FreeParams,
    JobThresholds,
    Observations,
    SectionProposal,
)

# Pack richness order: index 0 = narrowest. Prefer narrowing when channels missing.
_PACK_RICHNESS = ("surface_min", "surface_full", "mwd_full", "job_union")


def _fresh(cand: FreeParams, tried: set[str]) -> FreeParams | None:
    c = cand.clamp()
    # Hard veto: free params must never carry pin fields
    d = c.to_dict()
    if PIN_FORBIDDEN_KEYS.intersection(d.keys()):
        return None
    ck = json.dumps(d, sort_keys=True)
    if ck in tried:
        return None
    return c


def _with_pack(
    p: FreeParams,
    pack: str,
    *,
    null_policy: str | None = None,
    align_mode: str | None = None,
    survey_gate: str | None = None,
) -> FreeParams:
    return FreeParams(
        align_mode=align_mode if align_mode is not None else p.align_mode,
        window_scale=p.window_scale,
        channel_pack=pack,
        null_policy=null_policy if null_policy is not None else p.null_policy,
        survey_gate=survey_gate if survey_gate is not None else p.survey_gate,
        regime_mode=p.regime_mode,
    )


def collect_section_proposals(
    obs: Observations,
    params: FreeParams,
    thr: JobThresholds,
    *,
    tried: set[str],
) -> list[SectionProposal]:
    """Each section proposes free-param moves (never pin)."""
    p = params.clamp()
    props: list[SectionProposal] = []
    pack_incomplete = obs.n_required_present < obs.n_required

    # --- export: incomplete → prefer narrowing pack when channels missing ---
    if obs.export_ok_fraction + 1e-12 < thr.min_export_ok_fraction:
        if pack_incomplete and p.channel_pack != "surface_min":
            # Prefer surface_min first (highest export precedence among pack moves)
            cand = _fresh(_with_pack(p, "surface_min"), tried)
            if cand:
                props.append(
                    SectionProposal(
                        "export",
                        cand,
                        "narrow_to_surface_min_missing_channels",
                        SECTION_PRIORITY["export"],
                    )
                )
            # Also offer single-step narrow if richer than surface_full intermediate
            try:
                idx = _PACK_RICHNESS.index(p.channel_pack)
            except ValueError:
                idx = 0
            if idx > 1:
                step = _PACK_RICHNESS[idx - 1]
                if step != "surface_min":
                    cand = _fresh(_with_pack(p, step), tried)
                    if cand:
                        props.append(
                            SectionProposal(
                                "export",
                                cand,
                                "narrow_channel_pack_one_step",
                                SECTION_PRIORITY["export"] + 1,
                            )
                        )
        elif not pack_incomplete:
            # All required present; export incomplete for another reason (e.g. empty rows)
            # — may broaden only when nothing is missing
            try:
                idx = _PACK_RICHNESS.index(p.channel_pack)
            except ValueError:
                idx = 0
            if idx + 1 < len(_PACK_RICHNESS):
                cand = _fresh(_with_pack(p, _PACK_RICHNESS[idx + 1]), tried)
                if cand:
                    props.append(
                        SectionProposal(
                            "export",
                            cand,
                            "broaden_channel_pack_export_incomplete",
                            SECTION_PRIORITY["export"] + 2,
                        )
                    )

        # null_policy adjust (does not change required set)
        if p.null_policy == "mark_only":
            cand = _fresh(_with_pack(p, p.channel_pack, null_policy="hold_last"), tried)
            if cand:
                props.append(
                    SectionProposal(
                        "export",
                        cand,
                        "null_policy_hold_last_export_incomplete",
                        SECTION_PRIORITY["export"] + 3,
                    )
                )

    # --- verify: pin hard ok but verify_ok false → adjust pack/null ---
    if obs.verify_ok is False and obs.depth_mono_ok and obs.unit_sanity_ok and obs.n_rows > 0:
        if p.channel_pack != "surface_min":
            cand = _fresh(_with_pack(p, "surface_min"), tried)
            if cand:
                props.append(
                    SectionProposal(
                        "verify",
                        cand,
                        "surface_min_after_verify_fail",
                        SECTION_PRIORITY["verify"],
                    )
                )
        elif p.null_policy != "drop":
            cand = _fresh(_with_pack(p, p.channel_pack, null_policy="drop"), tried)
            if cand:
                props.append(
                    SectionProposal(
                        "verify",
                        cand,
                        "null_drop_after_verify_fail",
                        SECTION_PRIORITY["verify"],
                    )
                )

    # --- align: weak glue → free-param align_mode only when domain exists ---
    # P2: multi-source glue_incomplete triggers; do NOT burn budget on
    # unusable mode flips (e.g. time_primary without surface TIME) or
    # null_policy moves that cannot change glue (glue uses immutable axes).
    align_weak = (
        obs.align_score + 1e-12 < thr.min_align_score
        or "align_weak" in obs.notes
        or "glue_incomplete" in obs.notes
        or (
            getattr(obs, "glue_score", 1.0) + 1e-12 < thr.min_align_score
            and getattr(obs, "has_micropulse", False)
        )
    )
    has_mp = bool(getattr(obs, "has_micropulse", False))
    has_time_domain = bool(getattr(obs, "glue_has_time_domain", False))
    has_depth_domain = bool(getattr(obs, "glue_has_depth_domain", False))
    if align_weak:
        if p.align_mode == "none":
            cand = _fresh(
                FreeParams(
                    align_mode="depth_primary",
                    window_scale=p.window_scale,
                    channel_pack=p.channel_pack,
                    null_policy=p.null_policy,
                    survey_gate=p.survey_gate,
                    regime_mode=p.regime_mode,
                ),
                tried,
            )
            if cand:
                props.append(
                    SectionProposal(
                        "align",
                        cand,
                        "enable_depth_primary_align",
                        SECTION_PRIORITY["align"],
                    )
                )
        elif p.align_mode == "survey_anchor":
            # P3: keep survey_anchor when stations present; else fall back
            if not getattr(obs, "survey_present", False):
                cand = _fresh(
                    FreeParams(
                        align_mode="depth_primary",
                        window_scale=p.window_scale,
                        channel_pack=p.channel_pack,
                        null_policy=p.null_policy,
                        survey_gate=p.survey_gate,
                        regime_mode=p.regime_mode,
                    ),
                    tried,
                )
                if cand:
                    props.append(
                        SectionProposal(
                            "align",
                            cand,
                            "fallback_depth_primary_no_survey",
                            SECTION_PRIORITY["align"],
                        )
                    )
        elif p.align_mode == "depth_primary" and has_mp:
            # Only propose time_primary when a shared time domain actually exists
            if has_time_domain:
                cand = _fresh(
                    FreeParams(
                        align_mode="time_primary",
                        window_scale=p.window_scale,
                        channel_pack=p.channel_pack,
                        null_policy=p.null_policy,
                        survey_gate=p.survey_gate,
                        regime_mode=p.regime_mode,
                    ),
                    tried,
                )
                if cand:
                    props.append(
                        SectionProposal(
                            "align",
                            cand,
                            "try_time_primary_glue_incomplete",
                            SECTION_PRIORITY["align"],
                        )
                    )
            # null_policy does not affect glue axes — do not propose for glue alone
        elif p.align_mode == "time_primary" and has_mp:
            # Only propose depth_primary when a shared depth domain exists
            if has_depth_domain:
                cand = _fresh(
                    FreeParams(
                        align_mode="depth_primary",
                        window_scale=p.window_scale,
                        channel_pack=p.channel_pack,
                        null_policy=p.null_policy,
                        survey_gate=p.survey_gate,
                        regime_mode=p.regime_mode,
                    ),
                    tried,
                )
                if cand:
                    props.append(
                        SectionProposal(
                            "align",
                            cand,
                            "try_depth_primary_glue_incomplete",
                            SECTION_PRIORITY["align"],
                        )
                    )
        elif (not has_mp) and p.null_policy == "mark_only":
            # Single-source weak align: null fill may still help export/physics
            cand = _fresh(_with_pack(p, p.channel_pack, null_policy="hold_last"), tried)
            if cand:
                props.append(
                    SectionProposal(
                        "align",
                        cand,
                        "hold_last_nulls_for_align",
                        SECTION_PRIORITY["align"],
                    )
                )

    # --- survey (P3): gate upgrades + survey_anchor when stations present / glue weak ---
    survey_present = bool(getattr(obs, "survey_present", False))
    survey_n = int(getattr(obs, "survey_n_stations", 0) or 0)
    survey_stalk_ok = bool(getattr(obs, "survey_stalk_ok", True))
    survey_qc_fail = int(getattr(obs, "survey_qc_fail", 0) or 0)
    survey_defects = int(getattr(obs, "survey_defect_count", 0) or 0)
    require_survey = bool(getattr(thr, "require_survey", False))
    gate_on = p.survey_gate != "off"

    # Only engage survey proposals when stalk is requested or stations exist
    if require_survey or gate_on or survey_present:
        # Upgrade gate when survey required / missing gate
        if require_survey and p.survey_gate == "off":
            cand = _fresh(_with_pack(p, p.channel_pack, survey_gate="qc_only"), tried)
            if cand:
                props.append(
                    SectionProposal(
                        "survey",
                        cand,
                        "enable_survey_gate_qc_only_require_survey",
                        SECTION_PRIORITY["survey"],
                    )
                )
        # qc_only → holonomy only when QC clean and holonomy not yet engaged
        # (honest deepen; skipped when already stalk_ok under holonomy)
        if (
            survey_present
            and p.survey_gate == "qc_only"
            and survey_qc_fail == 0
            and survey_defects == 0
            and not survey_stalk_ok
        ):
            cand = _fresh(_with_pack(p, p.channel_pack, survey_gate="holonomy"), tried)
            if cand:
                props.append(
                    SectionProposal(
                        "survey",
                        cand,
                        "upgrade_survey_gate_qc_only_to_holonomy",
                        SECTION_PRIORITY["survey"] + 1,
                    )
                )
        # Explicit deepen: allow one holonomy upgrade when require_survey and
        # gate is qc_only and board would otherwise be empty only if user set
        # holonomy — do not block fixed-point under qc_only (no auto deepen).
        # Survey present but glue weak → survey_anchor
        if survey_present and survey_n > 0 and align_weak and p.align_mode != "survey_anchor":
            cand = _fresh(
                FreeParams(
                    align_mode="survey_anchor",
                    window_scale=p.window_scale,
                    channel_pack=p.channel_pack,
                    null_policy=p.null_policy,
                    survey_gate=p.survey_gate if p.survey_gate != "off" else "qc_only",
                    regime_mode=p.regime_mode,
                ),
                tried,
            )
            if cand:
                props.append(
                    SectionProposal(
                        "survey",
                        cand,
                        "align_mode_survey_anchor_survey_present_glue_weak",
                        SECTION_PRIORITY["survey"],
                    )
                )
        # Bad stations: mark_only null_policy (do not invent / do not drop silently)
        if survey_present and survey_qc_fail > 0 and p.null_policy != "mark_only":
            cand = _fresh(
                _with_pack(p, p.channel_pack, null_policy="mark_only"),
                tried,
            )
            if cand:
                props.append(
                    SectionProposal(
                        "survey",
                        cand,
                        "null_policy_mark_only_bad_survey_stations",
                        SECTION_PRIORITY["survey"] + 2,
                    )
                )
        # Gate off but survey present and QC fails → enable qc
        if survey_present and p.survey_gate == "off" and survey_qc_fail > 0:
            cand = _fresh(_with_pack(p, p.channel_pack, survey_gate="qc_only"), tried)
            if cand:
                props.append(
                    SectionProposal(
                        "survey",
                        cand,
                        "enable_survey_gate_qc_only_on_qc_fail",
                        SECTION_PRIORITY["survey"],
                    )
                )
        # Stalk not ok under active gate with QC ok but defects under holonomy —
        # no free-param can invent Inc/Azi; leave board empty → honest stuck.
        _ = survey_stalk_ok  # used by is_solved; proposals never retune QC bands

    # --- physics: hard fails → null_policy only (never pin eps; no window_scale in P1) ---
    # window_scale is not consumed by P1 observe/execute; do not propose no-op moves.
    if obs.physics_n_fail > thr.max_physics_fail:
        if p.null_policy != "drop":
            cand = _fresh(_with_pack(p, p.channel_pack, null_policy="drop"), tried)
            if cand:
                props.append(
                    SectionProposal(
                        "physics",
                        cand,
                        "drop_nulls_after_physics_fail",
                        SECTION_PRIORITY["physics"],
                    )
                )
        # If pack incomplete is driving physics missing-channel fails, narrow pack
        if pack_incomplete and p.channel_pack != "surface_min":
            cand = _fresh(_with_pack(p, "surface_min"), tried)
            if cand:
                props.append(
                    SectionProposal(
                        "physics",
                        cand,
                        "narrow_pack_after_physics_fail",
                        SECTION_PRIORITY["physics"] + 1,
                    )
                )

    # Veto any proposal that somehow includes forbidden pin keys
    clean: list[SectionProposal] = []
    for pr in props:
        keys = set(pr.params.to_dict().keys())
        if keys & PIN_FORBIDDEN_KEYS:
            continue
        # Double-check param values stay in free domain
        d = pr.params.clamp().to_dict()
        if d["align_mode"] not in ALIGN_MODES:
            continue
        if d["channel_pack"] not in CHANNEL_PACKS:
            continue
        if d["null_policy"] not in NULL_POLICIES:
            continue
        if d.get("survey_gate", "off") not in SURVEY_GATES:
            continue
        clean.append(pr)
    return clean


def merge_proposals(
    proposals: list[SectionProposal],
    current: FreeParams,
) -> tuple[FreeParams | None, str, list[dict[str, Any]]]:
    """Sheaf-style merge: highest-priority (lowest number) proposal wins."""
    if not proposals:
        return None, "stuck_no_free_param_move", []
    ranked = sorted(proposals, key=lambda x: (x.priority, x.section, x.reason))
    winner = ranked[0]
    return (
        winner.params.clamp(),
        f"merge[{winner.section}]:{winner.reason}",
        [pr.to_dict() for pr in ranked],
    )


def negotiate(
    obs: Observations,
    params: FreeParams,
    thr: JobThresholds,
    *,
    tried: set[str],
) -> tuple[FreeParams | None, str, list[dict[str, Any]]]:
    """Multi-section propose + merge. Never proposes QC pin changes.

    Hard pin (depth mono / unit sanity): cannot negotiate.
    Pack-completeness pin fail (missing channels only): may negotiate free params
    (channel_pack / null_policy) so export can recover.

    Returns (next_params|None, reason, proposal_board).
    """
    from realm.job_os.observe import is_solved

    p = params.clamp()
    key = json.dumps(p.to_dict(), sort_keys=True)
    tried.add(key)

    # Hard pin locked — never free-param retune of mono/unit
    hard_pin_fail = thr.require_pin and (
        (not obs.depth_mono_ok) or (not obs.unit_sanity_ok)
    )
    if hard_pin_fail:
        return None, "pin_locked_fail_cannot_negotiate", []

    if is_solved(obs, thr, p):
        return None, "already_coherent", []

    proposals = collect_section_proposals(obs, p, thr, tried=tried)
    nxt, reason, board = merge_proposals(proposals, p)
    if nxt is not None:
        # Final pin-field veto on merged params
        if set(nxt.to_dict().keys()) & PIN_FORBIDDEN_KEYS:
            return None, "veto_pin_fields_in_proposal", board
        tried.add(json.dumps(nxt.to_dict(), sort_keys=True))
    return nxt, reason, board
