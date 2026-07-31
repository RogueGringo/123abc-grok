"""Multi-section free-param propose + merge for Job Coherence OS.

Sections (P1): export | verify | align | physics
Merge ranks by priority; never proposes pin retune.

Priority (lower wins): export=1, verify=2, align=3, physics=5
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
    WINDOW_SCALE_BOUNDS,
    FreeParams,
    JobThresholds,
    Observations,
    SectionProposal,
)


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


def collect_section_proposals(
    obs: Observations,
    params: FreeParams,
    thr: JobThresholds,
    *,
    tried: set[str],
) -> list[SectionProposal]:
    """Each section proposes at most one free-param move (never pin)."""
    p = params.clamp()
    props: list[SectionProposal] = []

    # --- export: incomplete channel pack → broaden pack or change null policy ---
    if obs.export_ok_fraction + 1e-12 < thr.min_export_ok_fraction:
        # Prefer stepping up pack if current missing optional channels
        pack_order = list(CHANNEL_PACKS)
        try:
            idx = pack_order.index(p.channel_pack)
        except ValueError:
            idx = 0
        if idx + 1 < len(pack_order):
            cand = _fresh(
                FreeParams(
                    align_mode=p.align_mode,
                    window_scale=p.window_scale,
                    channel_pack=pack_order[idx + 1],
                    null_policy=p.null_policy,
                    survey_gate=p.survey_gate,
                    regime_mode=p.regime_mode,
                ),
                tried,
            )
            if cand:
                props.append(
                    SectionProposal(
                        "export",
                        cand,
                        "broaden_channel_pack_export_incomplete",
                        SECTION_PRIORITY["export"],
                    )
                )
        # Also try hold_last if mark_only and nulls likely
        if p.null_policy == "mark_only":
            cand = _fresh(
                FreeParams(
                    align_mode=p.align_mode,
                    window_scale=p.window_scale,
                    channel_pack=p.channel_pack,
                    null_policy="hold_last",
                    survey_gate=p.survey_gate,
                    regime_mode=p.regime_mode,
                ),
                tried,
            )
            if cand:
                props.append(
                    SectionProposal(
                        "export",
                        cand,
                        "null_policy_hold_last_export_incomplete",
                        SECTION_PRIORITY["export"] + 1,
                    )
                )
        # If pack is too rich and missing, try surface_min
        if p.channel_pack != "surface_min" and obs.n_required_present < obs.n_required:
            cand = _fresh(
                FreeParams(
                    align_mode=p.align_mode,
                    window_scale=p.window_scale,
                    channel_pack="surface_min",
                    null_policy=p.null_policy,
                    survey_gate=p.survey_gate,
                    regime_mode=p.regime_mode,
                ),
                tried,
            )
            if cand:
                props.append(
                    SectionProposal(
                        "export",
                        cand,
                        "fallback_surface_min_export_incomplete",
                        SECTION_PRIORITY["export"],
                    )
                )

    # --- verify: pin ok but verify_ok false → adjust pack/null ---
    if obs.verify_ok is False and obs.pin_ok and obs.n_rows > 0:
        if p.channel_pack != "surface_min":
            cand = _fresh(
                FreeParams(
                    align_mode=p.align_mode,
                    window_scale=p.window_scale,
                    channel_pack="surface_min",
                    null_policy=p.null_policy,
                    survey_gate=p.survey_gate,
                    regime_mode=p.regime_mode,
                ),
                tried,
            )
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
            cand = _fresh(
                FreeParams(
                    align_mode=p.align_mode,
                    window_scale=p.window_scale,
                    channel_pack=p.channel_pack,
                    null_policy="drop",
                    survey_gate=p.survey_gate,
                    regime_mode=p.regime_mode,
                ),
                tried,
            )
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
            cand = _fresh(
                FreeParams(
                    align_mode=p.align_mode,
                    window_scale=p.window_scale,
                    channel_pack=p.channel_pack,
                    null_policy="hold_last",
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
                        "hold_last_nulls_for_align",
                        SECTION_PRIORITY["align"],
                    )
                )

    # --- physics: hard fails → window_scale nudge or null_policy (never pin eps) ---
    if obs.physics_n_fail > thr.max_physics_fail:
        if p.window_scale < WINDOW_SCALE_BOUNDS[1]:
            cand = _fresh(
                FreeParams(
                    align_mode=p.align_mode,
                    window_scale=min(WINDOW_SCALE_BOUNDS[1], p.window_scale + 1),
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
                        "physics",
                        cand,
                        "increase_window_scale_after_physics_fail",
                        SECTION_PRIORITY["physics"],
                    )
                )
        if p.null_policy != "drop":
            cand = _fresh(
                FreeParams(
                    align_mode=p.align_mode,
                    window_scale=p.window_scale,
                    channel_pack=p.channel_pack,
                    null_policy="drop",
                    survey_gate=p.survey_gate,
                    regime_mode=p.regime_mode,
                ),
                tried,
            )
            if cand:
                props.append(
                    SectionProposal(
                        "physics",
                        cand,
                        "drop_nulls_after_physics_fail",
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

    Returns (next_params|None, reason, proposal_board).
    """
    from realm.job_os.observe import is_solved

    p = params.clamp()
    key = json.dumps(p.to_dict(), sort_keys=True)
    tried.add(key)

    if thr.require_pin and not obs.pin_ok:
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
