"""Multi-section free-param propose + merge for Job Coherence OS.

Sections (P1): export | verify | align | physics
Merge ranks by priority; never proposes pin retune.

Priority (lower wins): export=1, verify=2, align=3, physics=5

Hard pin (depth mono / unit sanity) is never negotiable.
Pack-completeness pin fails may negotiate channel_pack / null_policy only.
window_scale is a free-param field (recipe stability / later stalks) but is
not proposed in P1 until a stalk consumes it (honest free board).
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


def _with_pack(p: FreeParams, pack: str, *, null_policy: str | None = None) -> FreeParams:
    return FreeParams(
        align_mode=p.align_mode,
        window_scale=p.window_scale,
        channel_pack=pack,
        null_policy=null_policy if null_policy is not None else p.null_policy,
        survey_gate=p.survey_gate,
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

    # --- align: weak glue → enable depth_primary or change null_policy ---
    if obs.align_score + 1e-12 < thr.min_align_score or "align_weak" in obs.notes:
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
            # P1 has no survey — fall back to depth_primary
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
        elif p.null_policy == "mark_only":
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
