"""Job Coherence OS loop: observe → multi-section propose → merge → re-execute.

OS mode: RUN.json, ledger.jsonl, stability-K fixed-point, PARTNER_RECIPE on SOLVED,
optional resume, optional post-SOLVED EOW ship (P5).

Fixed-point: is_solved ∧ empty free-param board for K consecutive cycles.
Pin re-checked every round and never written/adapted.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from realm.dynamical_topology import engine as dynamical_topology_engine
from realm.dynamical_topology.engine import run_dynamical_topology, topology_stable
from realm.dynamical_topology.stages_job import (
    build_stages_from_job_run,
    build_stages_from_structure_scores,
)
from realm.job_os.chunk_inspect import run_las_chunk_inspect
from realm.job_os.eow_ship import ship_eow_package
from realm.job_os.firewall import assert_firewall_invariants, build_job_firewall
from realm.job_os.glue import compute_glue
from realm.job_os.ingest_las import apply_null_policy, parse_las, select_channel_pack
from realm.job_os.ingest_micropulse import join_surface_micropulse, load_micropulse_bundle
from realm.job_os.observe import coherence_score, is_solved, observe_job
from realm.job_os.pin import verify_job_pin
from realm.job_os.propose import collect_section_proposals, negotiate
from realm.job_os.regime import evaluate_regime
from realm.job_os.science import evaluate_science
from realm.job_os.survey import evaluate_survey, load_survey
from realm.job_os.types import FreeParams, JobThresholds

logger = logging.getLogger(__name__)


def _utc_run_id() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _cycle_trend_fields(summary: dict[str, Any] | None) -> dict[str, Any]:
    """Extract informational multi-scale / λ1 fields for ledger trends.

    Never ACCEPTANCE. Graph λ1 is algebraic connectivity, not λ=γ ontology.
    """
    s = summary or {}
    reg = s.get("regime") or {}
    sci = s.get("science") or {}
    # Full regime report may live only on disk; summary is shallow.
    # Prefer nested multi_scale/graph if execute_job_cycle enriched summary.
    multi = reg.get("multi_scale") or s.get("multi_scale") or {}
    graph = reg.get("graph_labels") or s.get("graph_labels") or {}
    return {
        "not_acceptance": True,
        "regime_structure_score": reg.get("structure_score"),
        "regime_barcode_n_bars": reg.get("barcode_n_bars"),
        "multi_scale_n_long": multi.get("n_long"),
        "multi_scale_n_short": multi.get("n_short"),
        "multi_scale_dominant_phase": (multi.get("phases") or {}).get("dominant"),
        "graph_lambda_1": graph.get("lambda_1"),
        "rips_h0_n_long": graph.get("rips_h0_n_long"),
        "science_native_beats_decoy": sci.get("native_beats_decoy"),
        "science_native_score": sci.get("native_score"),
        "science_decoy_score": sci.get("decoy_score"),
        "note": "Trend fields informational; never pin retune; never SOLVED alone.",
    }


def build_trend_rollup(ledger: list[dict[str, Any]]) -> dict[str, Any]:
    """Relative λ1 / multi-scale trend across cycles (info only)."""
    rows: list[dict[str, Any]] = []
    lambdas: list[float] = []
    for e in ledger:
        if not isinstance(e.get("round"), int):
            continue
        t = e.get("trend") or {}
        lam = t.get("graph_lambda_1")
        row = {
            "round": e.get("round"),
            "graph_lambda_1": lam,
            "multi_scale_n_long": t.get("multi_scale_n_long"),
            "regime_structure_score": t.get("regime_structure_score"),
            "science_native_beats_decoy": t.get("science_native_beats_decoy"),
        }
        rows.append(row)
        if lam is not None:
            try:
                lambdas.append(float(lam))
            except (TypeError, ValueError):
                pass

    trend_dir = "flat"
    delta = None
    if len(lambdas) >= 2:
        delta = float(lambdas[-1] - lambdas[0])
        if delta > 1e-9:
            trend_dir = "non_decreasing"
        elif delta < -1e-9:
            trend_dir = "decreasing"
        else:
            trend_dir = "flat"

    return {
        "kind": "trend_rollup",
        "not_acceptance": True,
        "ontology": "job_trend_rollup_not_lambda_eq_gamma",
        "n_cycles": len(rows),
        "cycles": rows,
        "lambda_1_series": lambdas,
        "lambda_1_delta": delta,
        "lambda_1_trend": trend_dir,
        "guidance": (
            "Prefer relative λ1 trend across cycles over absolute floors "
            "(parent KB threshold guidance). Never ACCEPTANCE."
        ),
        "kb_source": "Parent KB threshold_guidance + Academic KB multi-scale",
    }


def _structure_scores_from_ledger(ledger: list[dict[str, Any]]) -> list[float]:
    scores: list[float] = []
    for e in ledger:
        if not isinstance(e.get("round"), int):
            continue
        t = e.get("trend") or {}
        if t.get("regime_structure_score") is not None:
            scores.append(float(t["regime_structure_score"]))
            continue
        obs = e.get("observations") or {}
        if obs.get("regime_structure_score") is not None:
            scores.append(float(obs["regime_structure_score"]))
    return scores


def _compute_dynamical_topology_report(
    out_root: Path,
    ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build stages from job run / ledger scores and run the measure engine.

    Never writes pin / soft_T / ACCEPTANCE.
    """
    stages = build_stages_from_job_run(out_root)
    if len(stages) < 2:
        scores = _structure_scores_from_ledger(ledger)
        if len(scores) >= 1 and len(stages) < 1:
            stages = build_stages_from_structure_scores(scores)
        elif len(scores) >= 2 and len(stages) < 2:
            stages = build_stages_from_structure_scores(scores)
    return run_dynamical_topology(stages)


def write_partner_recipe(
    path: Path | str,
    *,
    pin: dict[str, Any],
    free_params: FreeParams,
    run_id: str,
    las_path: str | None,
    solved: bool,
    micropulse_path: str | None = None,
    survey_path: str | None = None,
    require_survey: bool = False,
    require_regime: bool = False,
    with_regime: bool = False,
    with_science: bool = False,
) -> Path:
    """Machine-readable free-param recipe for partner re-run (not ACCEPTANCE)."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    mp_cli = f" --micropulse {micropulse_path}" if micropulse_path else ""
    sv_cli = f" --survey {survey_path}" if survey_path else ""
    req_cli = " --require-survey" if require_survey else ""
    reg_cli = " --require-regime" if require_regime else ""
    wr_cli = " --with-regime" if with_regime else ""
    ws_cli = " --with-science" if with_science else ""
    body = {
        "kind": "partner_recipe",
        "ontology": "job_partner_recipe_not_rop_score",
        "run_id": run_id,
        "solved": solved,
        "pin": {
            "ok": pin.get("ok"),
            "depth_mono_ok": pin.get("depth_mono_ok"),
            "unit_sanity_ok": pin.get("unit_sanity_ok"),
            "required_channels": pin.get("required_channels"),
            "missing_channels": pin.get("missing_channels"),
            "reasons": pin.get("reasons"),
            "note": "QC pin locked; not negotiated by job coherence OS",
        },
        "free_params": free_params.to_dict(),
        "las_path": las_path,
        "micropulse_path": micropulse_path,
        "survey_path": survey_path,
        "require_survey": require_survey,
        "require_regime": require_regime,
        "with_regime": with_regime,
        "with_science": with_science,
        "re_run_cli": (
            f"python job_coherence.py --os --las {las_path or '<LAS>'}"
            f"{mp_cli}{sv_cli}{req_cli}{reg_cli}{wr_cli}{ws_cli} "
            f"--align-mode {free_params.align_mode} "
            f"--window-scale {free_params.window_scale} "
            f"--channel-pack {free_params.channel_pack} "
            f"--null-policy {free_params.null_policy} "
            f"--survey-gate {free_params.survey_gate} "
            f"--regime-mode {free_params.regime_mode}"
        ),
        "disclaimers": [
            "PARTNER_RECIPE is free-param + pin stamp for re-run fidelity.",
            "Not ACCEPTANCE / not SHIP success / not ROP prediction.",
            "Commercial success remains gluing sources + QC pin.",
            "Never retune SOP pin for score. Never ζ→ROP claim.",
            "Glue is structural (depth/time proximity); not score-chase.",
            "Survey stalk never invents Inc/Azi.",
            "Regime/science are informational unless --require-regime.",
        ],
    }
    dest.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return dest


def append_ledger(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def load_resume_state(run_dir: Path) -> dict[str, Any]:
    """Load RUN.json + ledger to resume OS batch."""
    run_path = run_dir / "RUN.json"
    if not run_path.is_file():
        raise FileNotFoundError(f"no RUN.json under {run_dir}")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    ledger_path = run_dir / "ledger.jsonl"
    entries: list[dict[str, Any]] = []
    if ledger_path.is_file():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return {"run": run, "ledger": entries, "run_dir": run_dir}


def _write_run_json(out_root: Path, doc: dict[str, Any]) -> None:
    (out_root / "RUN.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8"
    )


def _write_latest_run_pointer(parent: Path, run_dir: Path) -> None:
    parent.mkdir(parents=True, exist_ok=True)
    body = {
        "run_id": run_dir.name,
        "path": str(run_dir.resolve()),
        "ontology": "job_coherence_os_v1_latest_not_rop",
    }
    (parent / "LATEST").write_text(
        json.dumps(body, indent=2) + "\n", encoding="utf-8"
    )


def _write_coherence_md(result: dict[str, Any], path: Path) -> Path:
    fw = result.get("firewall") or {}
    near = (fw.get("near_miss") or {}) if isinstance(fw, dict) else {}
    lines = [
        "# Job Coherence OS ledger",
        "",
        f"- **solved:** {result.get('solved')}",
        f"- **stop:** `{result.get('stop_reason')}`",
        f"- **run_id:** `{result.get('run_id')}`",
        f"- **os_mode:** `{result.get('os_mode')}`",
        f"- **stability_k:** {result.get('stability_k')}",
        f"- **n_rounds:** {result.get('n_rounds')}",
        f"- **final_params:** `{json.dumps(result.get('final_params') or {})}`",
        f"- **partner_recipe:** `{result.get('partner_recipe')}`",
        f"- **eow_ship:** `{result.get('eow_ship_status')}`",
        f"- **firewall.certified:** `{fw.get('certified') if fw else None}`",
        f"- **firewall.near_miss:** `{near.get('verdict') if near else None}`",
        "",
        "## Ontology",
        "",
        "- Substrate: raw multi-channel series",
        "- Pin: QC locked (depth mono, required channels, unit sanity)",
        "- Free: align_mode, window_scale, channel_pack, null_policy, survey_gate, regime_mode",
        "- Survey stalk (B): QC total G/MagF + optional discrete holonomy",
        "- Regime stalk (C): windowed H0 on SSSI/TOR/RPM; dual-gate science info",
        "- EOW ship (D): post-SOLVED package inventory + PARTNER_RECIPE attach",
        "- Fixed-point: is_solved ∧ empty board × K",
        "- Science score never sets SOLVED alone (unless --require-regime stalk)",
        "- Never retune pin for score. Never invent Inc/Azi. Never ζ→ROP.",
        "",
        "## Job QC Firewall (explore vs certify)",
        "",
        "- **EXPLORE (Tier-E analog):** science / dynamical topology measure / λ1 trends — "
        "`not_acceptance`; may look promising.",
        "- **CERTIFY (Tier-C analog):** pin hard seal + is_solved ∧ empty free-param board × K.",
        "- **Near-miss:** explore promising + certify fail → **REJECT** for ship "
        "(agreement is not verification).",
        "- Pin never writable from explore metrics. Never λ=γ.",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def execute_job_cycle(
    *,
    las_path: Path | str,
    params: FreeParams,
    thr: JobThresholds,
    cycle_dir: Path,
    mp_bundle: dict[str, Any] | None = None,
    survey: dict[str, Any] | None = None,
    with_regime: bool = False,
    with_science: bool = False,
    max_rows: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    """Ingest LAS (+ optional MicroPulse/survey/regime) → pin → observe."""
    cycle_dir.mkdir(parents=True, exist_ok=True)
    p = params.clamp()
    raw = parse_las(las_path, max_rows=max_rows)
    # Null-policy on surface skeleton first; then join presence-only MP fibers
    # so length-mismatched channels never drive surface row drops.
    series = apply_null_policy(raw, p.null_policy)
    series = join_surface_micropulse(series, mp_bundle)
    series = select_channel_pack(series, p.channel_pack)

    pin = verify_job_pin(
        series,
        pack=p.channel_pack,
        depth_mono_eps=float(thr.depth_mono_eps),
        max_depth_mono_violations=int(thr.max_depth_mono_violations),
    )
    (cycle_dir / "pin.json").write_text(
        json.dumps(pin, indent=2) + "\n", encoding="utf-8"
    )

    n_survey = int((survey or {}).get("n_stations") or 0)
    glue = compute_glue(
        series,
        mp_bundle,
        align_mode=p.align_mode,
        channel_pack=p.channel_pack,
        survey_n_stations=n_survey,
    )
    (cycle_dir / "glue.json").write_text(
        json.dumps(glue, indent=2) + "\n", encoding="utf-8"
    )

    survey_report = evaluate_survey(
        survey,
        survey_gate=p.survey_gate,
        total_g_tol=float(thr.survey_total_g_tol),
        magf_lo=float(thr.survey_magf_lo),
        magf_hi=float(thr.survey_magf_hi),
        dogleg_jump_deg=float(thr.survey_dogleg_jump_deg),
        dinc_jump_deg=float(thr.survey_dinc_jump_deg),
    )
    (cycle_dir / "survey_report.json").write_text(
        json.dumps(survey_report, indent=2) + "\n", encoding="utf-8"
    )

    # P4 regime stalk + science annex (when enabled by flags / free params)
    regime_enabled = bool(with_regime) or bool(thr.require_regime) or p.regime_mode != "off"
    regime_report = evaluate_regime(
        series,
        regime_mode=p.regime_mode,
        window_scale=p.window_scale,
        enabled=regime_enabled,
        require_regime=bool(thr.require_regime),
        shock_k=float(thr.regime_shock_k),
    )
    if regime_enabled:
        (cycle_dir / "regime_report.json").write_text(
            json.dumps(regime_report, indent=2) + "\n", encoding="utf-8"
        )

    science_report = evaluate_science(
        series,
        regime_mode=p.regime_mode,
        window_scale=p.window_scale,
        with_science=bool(with_science),
        pin_ok=bool(pin.get("ok")),
        seed=int(thr.science_seed),
    )
    if science_report.get("enabled"):
        (cycle_dir / "science_annex.json").write_text(
            json.dumps(science_report, indent=2) + "\n", encoding="utf-8"
        )

    # Store lightweight series summary (not full arrays in json for large files)
    mp_summary = None
    if series.get("micropulse"):
        mp = series["micropulse"]
        mp_summary = {
            "n_fibers": mp.get("n_fibers"),
            "kinds": mp.get("kinds"),
            "source_path": mp.get("source_path"),
            "pack_channels": mp.get("pack_channels"),
            "downhole_kinds_present": mp.get("downhole_kinds_present"),
            "n_times": len(mp.get("times_union") or []),
            "n_depths": len(mp.get("depths_union") or []),
        }
    summary = {
        "n_rows": series.get("n_rows"),
        "curve_names": series.get("curve_names"),
        "channel_pack": p.channel_pack,
        "null_policy": p.null_policy,
        "align_mode": p.align_mode,
        "survey_gate": p.survey_gate,
        "regime_mode": p.regime_mode,
        "window_scale": p.window_scale,
        "source_path": series.get("source_path"),
        "units": series.get("units"),
        "n_channels": len(series.get("channels") or {}),
        "pack_required": series.get("pack_required"),
        "has_micropulse": bool(series.get("has_micropulse")),
        "micropulse": mp_summary,
        "survey": {
            "n_stations": survey_report.get("n_stations"),
            "present": survey_report.get("present"),
            "qc_ok": survey_report.get("qc_ok"),
            "holonomy_ok": survey_report.get("holonomy_ok"),
            "defect_count": survey_report.get("defect_count"),
            "stalk_ok": survey_report.get("stalk_ok"),
            "source_path": survey_report.get("source_path"),
        },
        "regime": {
            "enabled": regime_report.get("enabled"),
            "present": regime_report.get("present"),
            "stalk_ok": regime_report.get("stalk_ok"),
            "channels_used": regime_report.get("channels_used"),
            "barcode_n_bars": regime_report.get("barcode_n_bars"),
            "structure_score": regime_report.get("structure_score"),
            "shock_exceedance": regime_report.get("shock_exceedance"),
            "multi_scale": regime_report.get("multi_scale"),
            "graph_labels": regime_report.get("graph_labels"),
        },
        "science": {
            "enabled": science_report.get("enabled"),
            "native_score": science_report.get("native_score"),
            "decoy_score": science_report.get("decoy_score"),
            "native_beats_decoy": science_report.get("native_beats_decoy"),
            "informational_only": True,
            "not_acceptance": True,
        },
        "glue": {
            "score": glue.get("score"),
            "method": glue.get("method"),
            "multi_source": glue.get("multi_source"),
            "shared_domain": glue.get("shared_domain"),
            "notes": glue.get("notes"),
        },
    }
    (cycle_dir / "sources_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    obs = observe_job(
        series=series,
        params=p,
        thr=thr,
        out_dir=cycle_dir,
        pin=pin,
        glue=glue,
        survey=survey,
        survey_report=survey_report,
        regime_report=regime_report,
        science_report=science_report,
        with_regime=bool(with_regime) or bool(thr.require_regime),
        with_science=bool(with_science),
    )
    (cycle_dir / "observations.json").write_text(
        json.dumps(obs.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    return pin, summary, obs


def run_job_coherence_loop(
    *,
    las_path: Path | str | None = None,
    micropulse_path: Path | str | None = None,
    survey_path: Path | str | None = None,
    out_root: Path | str = "out/job_os",
    initial: FreeParams | None = None,
    thresholds: JobThresholds | None = None,
    max_rounds: int = 6,
    stability_k: int = 1,
    os_mode: bool = False,
    resume_dir: Path | str | None = None,
    run_id: str | None = None,
    with_regime: bool = False,
    with_science: bool = False,
    with_dynamical_topology: bool = False,
    topo_stability: bool = False,
    eow_package: Path | str | None = None,
    force_ship: bool = False,
    chunk_rows: int | None = None,
    max_chunks: int = 32,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Execute cyclic observe→multi-section propose→merge→ingest until coherent.

    QC pin is re-checked every round and never written/adapted.

    OS mode (os_mode=True): RUN.json, ledger.jsonl, stability-K fixed-point,
    PARTNER_RECIPE on SOLVED, optional resume.

    Fixed-point: is_solved ∧ empty free-param board for K consecutive cycles.
    When ``topo_stability``: also require topology_stable for those K cycles
    (auto-enables dynamical topology measure; never pin / never ACCEPTANCE).

    P2: optional micropulse_path (dir of CSVs or single file) joins downhole fibers.
    P3: optional survey_path and/or SURVEY fiber in MicroPulse; survey_gate free param.
    P4: --with-regime / --with-science dual-gate info; --require-regime optional gate.
    P5: optional eow_package after SOLVED (or --force-ship → UNSOLVED_SHIP banner).
    KB D: chunk_rows / max_chunks → out-of-core CHUNK_INSPECT.json; max_rows caps LAS load.
    Dynamical topology (measure): optional stage-axis barcode report at run root
    when ``with_dynamical_topology``; never pin / never ACCEPTANCE.
    """
    thr = thresholds or JobThresholds()
    params = (initial or FreeParams()).clamp()
    out_root = Path(out_root)
    stability_k = max(1, int(stability_k))
    parent_for_latest: Path | None = None
    with_regime = bool(with_regime)
    with_science = bool(with_science)
    with_dynamical_topology = bool(with_dynamical_topology)
    topo_stability = bool(topo_stability)
    # Control gate requires measure; auto-enable when topo-stability is on.
    if topo_stability:
        with_dynamical_topology = True
    chunk_rows_i = int(chunk_rows) if chunk_rows is not None else None
    max_chunks_i = max(1, int(max_chunks))
    max_rows_i = int(max_rows) if max_rows is not None else None
    chunk_inspect_report: dict[str, Any] | None = None

    resume_ledger: list[dict[str, Any]] = []
    start_round = 1
    tried: set[str] = set()
    stability_streak = 0
    run_doc: dict[str, Any] | None = None
    las_str: str | None = str(las_path) if las_path is not None else None
    mp_str: str | None = str(micropulse_path) if micropulse_path is not None else None
    survey_str: str | None = str(survey_path) if survey_path is not None else None

    if resume_dir is not None:
        state = load_resume_state(Path(resume_dir))
        run_meta = state["run"]
        resume_ledger = list(state["ledger"])
        run_dir = Path(state["run_dir"])
        run_id = str(run_meta.get("run_id") or run_dir.name)
        params = FreeParams(
            **(run_meta.get("final_params") or params.to_dict())
        ).clamp()
        for e in reversed(resume_ledger):
            if e.get("next_params"):
                params = FreeParams(**e["next_params"]).clamp()
                break
            if e.get("params"):
                params = FreeParams(**e["params"]).clamp()
                break
        for e in resume_ledger:
            if e.get("params"):
                tried.add(json.dumps(e["params"], sort_keys=True))
            if e.get("next_params"):
                tried.add(json.dumps(e["next_params"], sort_keys=True))
            if e.get("stability_streak") is not None:
                stability_streak = int(e["stability_streak"])
        cycle_entries = [e for e in resume_ledger if isinstance(e.get("round"), int)]
        start_round = len(cycle_entries) + 1
        max_rounds = int(run_meta.get("max_rounds") or max_rounds)
        os_mode = True
        out_root = run_dir
        parent_for_latest = out_root.parent
        thr = JobThresholds(**(run_meta.get("thresholds") or thr.to_dict()))
        stability_k = max(1, int(run_meta.get("stability_k") or stability_k))
        if run_meta.get("las_path"):
            las_str = str(run_meta["las_path"])
            las_path = las_str
        if run_meta.get("micropulse_path"):
            mp_str = str(run_meta["micropulse_path"])
            micropulse_path = mp_str
        if run_meta.get("survey_path"):
            survey_str = str(run_meta["survey_path"])
            survey_path = survey_str
        if "with_regime" in run_meta:
            with_regime = bool(run_meta.get("with_regime"))
        if "with_science" in run_meta:
            with_science = bool(run_meta.get("with_science"))
        if "with_dynamical_topology" in run_meta:
            with_dynamical_topology = bool(run_meta.get("with_dynamical_topology"))
        if "topo_stability" in run_meta:
            topo_stability = bool(run_meta.get("topo_stability"))
        if topo_stability:
            with_dynamical_topology = True
        run_doc = dict(run_meta)
        run_doc["status"] = "resuming"
        logger.info(
            "resume run_id=%s start_round=%s budget=%s streak=%s",
            run_id,
            start_round,
            max_rounds,
            stability_streak,
        )
    else:
        if os_mode:
            rid = run_id or _utc_run_id()
            parent_for_latest = Path(out_root)
            out_root = Path(out_root) / rid
            run_id = rid
        else:
            run_id = run_id or "legacy"
        out_root.mkdir(parents=True, exist_ok=True)

    if las_path is None and las_str is None:
        raise ValueError("las_path required (or resume RUN.json with las_path)")
    las_path = Path(las_str or las_path)  # type: ignore[arg-type]
    if not las_path.is_file():
        raise FileNotFoundError(f"LAS not found: {las_path}")
    las_str = str(las_path.resolve())

    # Load MicroPulse bundle once (immutable sources; free params don't re-parse SOP)
    mp_bundle: dict[str, Any] | None = None
    if mp_str or micropulse_path is not None:
        mp_path = Path(mp_str or micropulse_path)  # type: ignore[arg-type]
        if not mp_path.exists():
            raise FileNotFoundError(f"MicroPulse path not found: {mp_path}")
        mp_str = str(mp_path.resolve())
        mp_bundle = load_micropulse_bundle(mp_path)
        logger.info(
            "micropulse fibers=%s kinds=%s",
            mp_bundle.get("n_fibers"),
            mp_bundle.get("kinds"),
        )

    # P3 survey: explicit path wins; else SURVEY fiber from MicroPulse bundle
    survey_table: dict[str, Any] | None = None
    if survey_str or survey_path is not None:
        sp = Path(survey_str or survey_path)  # type: ignore[arg-type]
        if not sp.is_file():
            raise FileNotFoundError(f"survey CSV not found: {sp}")
        survey_str = str(sp.resolve())
        survey_table = load_survey(survey_str, mp_bundle=None)
    else:
        survey_table = load_survey(None, mp_bundle=mp_bundle)
        if survey_table and survey_table.get("source_path"):
            survey_str = str(survey_table.get("source_path"))
    if survey_table:
        logger.info(
            "survey stations=%s source=%s",
            survey_table.get("n_stations"),
            survey_table.get("source_path"),
        )

    ledger: list[dict[str, Any]] = list(resume_ledger)
    solved = False
    stop_reason = "max_rounds"
    partner_recipe_path: str | None = None
    pin0: dict[str, Any] = {"ok": None}
    # Dual-spine control: previous dynamical topology report across cycles
    prev_topo_report: dict[str, Any] | None = None

    # Early exit if resume of already-solved run
    if resume_dir is not None and any(
        e.get("action") == "halt" and e.get("solved") for e in resume_ledger
    ):
        solved = True
        stop_reason = "coherent"
        for e in reversed(resume_ledger):
            if e.get("params"):
                params = FreeParams(**e["params"]).clamp()
                break

    if os_mode and resume_dir is None:
        run_doc = {
            "run_id": run_id,
            "ontology": "job_coherence_os_p4_not_rop_score",
            "las_path": las_str,
            "micropulse_path": mp_str,
            "survey_path": survey_str,
            "with_regime": with_regime,
            "with_science": with_science,
            "with_dynamical_topology": with_dynamical_topology,
            "topo_stability": topo_stability,
            "thresholds": thr.to_dict(),
            "stability_k": stability_k,
            "max_rounds": int(max_rounds),
            "initial_params": params.to_dict(),
            "final_params": params.to_dict(),
            "pin_locked": {
                "depth_mono": True,
                "required_channels_for_pack": True,
                "unit_sanity": True,
                "note": "QC pin never negotiated",
            },
            "n_rounds": 0,
            "status": "running",
            "stability_streak": 0,
        }
        _write_run_json(out_root, run_doc)
        (out_root / "ledger.jsonl").write_text("", encoding="utf-8")
        if parent_for_latest is not None:
            _write_latest_run_pointer(parent_for_latest, out_root)

    ledger_path = out_root / "ledger.jsonl"

    # KB D: out-of-core chunk inspect (optional) before negotiate loop
    if las_path is not None and chunk_rows_i is not None and chunk_rows_i > 0:
        try:
            chunk_inspect_report = run_las_chunk_inspect(
                las_path,
                chunk_rows=chunk_rows_i,
                max_chunks=max_chunks_i,
                pack=params.channel_pack,
                depth_mono_eps=float(thr.depth_mono_eps),
                max_depth_mono_violations=int(thr.max_depth_mono_violations),
                out_path=out_root / "CHUNK_INSPECT.json",
            )
            logger.info(
                "chunk inspect n_chunks=%s coverage=%.2f all_hard_ok=%s",
                chunk_inspect_report.get("n_chunks"),
                chunk_inspect_report.get("coverage_frac"),
                chunk_inspect_report.get("all_hard_ok"),
            )
            if run_doc is not None:
                run_doc["chunk_inspect"] = {
                    "chunk_rows": chunk_rows_i,
                    "max_chunks": max_chunks_i,
                    "n_chunks": chunk_inspect_report.get("n_chunks"),
                    "coverage_frac": chunk_inspect_report.get("coverage_frac"),
                    "all_hard_ok": chunk_inspect_report.get("all_hard_ok"),
                    "not_acceptance": True,
                }
                _write_run_json(out_root, run_doc)
            # P6: science annex attachment when with_science
            if with_science:
                sci_path = out_root / "CHUNK_SCIENCE_ANNEX.json"
                sci_body = dict(chunk_inspect_report)
                sci_body["kind"] = "chunk_science_annex"
                sci_body["with_science"] = True
                from realm.kb_geometry.science_annex import attach_science_theory

                sci_body = attach_science_theory(sci_body, split="unspecified")
                sci_path.write_text(
                    json.dumps(sci_body, indent=2) + "\n", encoding="utf-8"
                )
                chunk_inspect_report["science_annex_path"] = str(sci_path.resolve())
        except Exception as exc:  # noqa: BLE001
            logger.warning("chunk inspect skipped: %s", exc)
            chunk_inspect_report = {
                "enabled": False,
                "error": str(exc),
                "not_acceptance": True,
            }

    def _commit_entry(entry: dict[str, Any], cycle_dir: Path | None = None) -> None:
        ledger.append(entry)
        if os_mode:
            append_ledger(ledger_path, entry)
            if run_doc is not None:
                run_doc["n_rounds"] = len(
                    [e for e in ledger if isinstance(e.get("round"), int)]
                )
                run_doc["final_params"] = (
                    entry.get("next_params") or entry.get("params") or params.to_dict()
                )
                run_doc["stability_streak"] = int(entry.get("stability_streak") or 0)
                run_doc["status"] = (
                    "solved"
                    if entry.get("solved") and entry.get("action") == "halt"
                    else "running"
                )
                run_doc["last_round"] = entry.get("round")
                _write_run_json(out_root, run_doc)
        if cycle_dir is not None:
            cycle_dir.mkdir(parents=True, exist_ok=True)
            (cycle_dir / "coherence_round.json").write_text(
                json.dumps(entry, indent=2) + "\n", encoding="utf-8"
            )

    if not solved:
        for rnd in range(start_round, max(1, int(max_rounds)) + 1):
            cycle_dir = out_root / f"cycle_{rnd:02d}"
            logger.info(
                "job cycle %s/%s align=%s pack=%s regime=%s window=%s streak=%s/%s os=%s",
                rnd,
                max_rounds,
                params.align_mode,
                params.channel_pack,
                params.regime_mode,
                params.window_scale,
                stability_streak,
                stability_k,
                os_mode,
            )

            pin, summary, obs = execute_job_cycle(
                las_path=las_path,
                params=params,
                thr=thr,
                cycle_dir=cycle_dir,
                mp_bundle=mp_bundle,
                survey=survey_table,
                with_regime=with_regime,
                with_science=with_science,
                max_rows=max_rows_i,
            )
            pin0 = pin

            # Hard pin = depth mono / unit sanity (never free-param negotiable).
            # Pack incompleteness (missing channels for pack) is soft: free-param
            # channel_pack / null_policy may recover without retuning pin ε.
            hard_pin_fail = thr.require_pin and not bool(
                pin.get("hard_ok", pin.get("depth_mono_ok") and pin.get("unit_sanity_ok"))
            )
            if hard_pin_fail:
                stop_reason = "pin_fail"
                _commit_entry(
                    {
                        "round": rnd,
                        "params": params.to_dict(),
                        "pin": {
                            "ok": pin.get("ok"),
                            "hard_ok": pin.get("hard_ok"),
                            "pack_ok": pin.get("pack_ok"),
                            "reasons": pin.get("reasons"),
                            "depth_mono_ok": pin.get("depth_mono_ok"),
                            "unit_sanity_ok": pin.get("unit_sanity_ok"),
                        },
                        "observations": obs.to_dict(),
                        "solved": False,
                        "is_solved_slice": False,
                        "stability_streak": 0,
                        "action": "abort",
                        "reason": "job_qc_pin_failed_locked",
                        "proposals": [],
                    },
                    cycle_dir,
                )
                break

            score = coherence_score(obs, thr, params)
            solved_slice = is_solved(obs, thr, params)
            tried.add(json.dumps(params.to_dict(), sort_keys=True))
            board_props = collect_section_proposals(obs, params, thr, tried=tried)
            # When solved, board should already be empty (invariant); force-clear
            # mirrors handoff OS v2 so fixed-point cannot be blocked by drift.
            if solved_slice:
                board_props = []
            empty_board = len(board_props) == 0

            # Dual-spine control: topology_stable gate (optional; default off)
            topo_ok = True
            curr_topo: dict[str, Any] | None = None
            if topo_stability:
                try:
                    # provisional ledger includes this cycle for score fallback
                    provisional = list(ledger) + [
                        {
                            "round": rnd,
                            "trend": _cycle_trend_fields(summary),
                            "observations": obs.to_dict(),
                        }
                    ]
                    curr_topo = _compute_dynamical_topology_report(
                        out_root, provisional
                    )
                    # Call via engine module so tests can monkeypatch topology_stable
                    topo_ok = bool(
                        dynamical_topology_engine.topology_stable(
                            curr_topo, prev=prev_topo_report
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("topology_stable control skipped: %s", exc)
                    topo_ok = False
                    curr_topo = None
                prev_topo_report = curr_topo

            if solved_slice and empty_board and topo_ok:
                stability_streak += 1
            else:
                stability_streak = 0

            entry: dict[str, Any] = {
                "round": rnd,
                "params": params.to_dict(),
                "observations": obs.to_dict(),
                "coherence_score": score,
                "is_solved_slice": solved_slice,
                "solved": False,
                "stability_streak": stability_streak,
                "stability_k": stability_k,
                "topo_stability": topo_stability,
                "topology_stable": topo_ok if topo_stability else None,
                "pin": {
                    "ok": pin.get("ok"),
                    "hard_ok": pin.get("hard_ok"),
                    "pack_ok": pin.get("pack_ok"),
                    "reasons": pin.get("reasons"),
                    "depth_mono_ok": pin.get("depth_mono_ok"),
                    "unit_sanity_ok": pin.get("unit_sanity_ok"),
                    "missing_channels": pin.get("missing_channels"),
                },
                "export_ok_fraction": obs.export_ok_fraction,
                "n_rows": obs.n_rows,
                "glue_score": obs.glue_score,
                "glue_method": obs.glue_method,
                "has_micropulse": obs.has_micropulse,
                "survey_n_stations": obs.survey_n_stations,
                "survey_qc_fail": obs.survey_qc_fail,
                "survey_stalk_ok": obs.survey_stalk_ok,
                "survey_defect_count": obs.survey_defect_count,
                "regime_enabled": obs.regime_enabled,
                "regime_stalk_ok": obs.regime_stalk_ok,
                "regime_barcode_n_bars": obs.regime_barcode_n_bars,
                "regime_shock_exceedance": obs.regime_shock_exceedance,
                "science_enabled": obs.science_enabled,
                "science_native_beats_decoy": obs.science_native_beats_decoy,
                # Trend stalk (info only): λ1 / multi-scale from regime_report summary
                "trend": _cycle_trend_fields(summary),
                "cycle_dir": str(cycle_dir.resolve()),
                "proposals": [pr.to_dict() for pr in board_props],
                "sources": summary,
            }

            # Fixed-point: is_solved ∧ empty board [∧ topology_stable] × K
            if (
                solved_slice
                and empty_board
                and topo_ok
                and stability_streak >= stability_k
            ):
                entry["action"] = "halt"
                entry["reason"] = (
                    "fixed_point" if stability_k > 1 or os_mode else "coherent"
                )
                entry["solved"] = True
                entry["proposals"] = []
                _commit_entry(entry, cycle_dir)
                solved = True
                stop_reason = "coherent"
                logger.info(
                    "job SOLVED at round %s score=%.3f streak=%s/%s topo_ok=%s",
                    rnd,
                    score,
                    stability_streak,
                    stability_k,
                    topo_ok,
                )
                break

            if solved_slice and empty_board and stability_streak < stability_k:
                entry["action"] = "stability_hold"
                if topo_stability and not topo_ok:
                    entry["reason"] = (
                        f"topo_unstable_streak_{stability_streak}_of_{stability_k}"
                    )
                else:
                    entry["reason"] = f"streak_{stability_streak}_of_{stability_k}"
                entry["next_params"] = params.to_dict()
                _commit_entry(entry, cycle_dir)
                logger.info(
                    "stability hold round %s streak=%s/%s topo_ok=%s",
                    rnd,
                    stability_streak,
                    stability_k,
                    topo_ok,
                )
                continue

            # negotiate: hard pin already aborted; soft pack fail may recover
            nxt, reason, board = negotiate(obs, params, thr, tried=tried)

            entry["action"] = "negotiate" if nxt is not None else "stuck"
            entry["reason"] = reason
            entry["proposals"] = board
            entry["next_params"] = nxt.to_dict() if nxt is not None else None
            _commit_entry(entry, cycle_dir)

            if nxt is None:
                stop_reason = reason
                logger.info("job coherence stuck: %s", reason)
                break
            logger.info(
                "negotiate → %s (%s) board=%s",
                nxt.to_dict(),
                reason,
                [b.get("section") for b in board],
            )
            params = nxt

    # PARTNER_RECIPE on commercial fixed-point
    if solved:
        # Re-verify pin at final params
        pin_final, _, _ = execute_job_cycle(
            las_path=las_path,
            params=params,
            thr=thr,
            cycle_dir=out_root / "cycle_final_pin",
            mp_bundle=mp_bundle,
            survey=survey_table,
            with_regime=with_regime,
            with_science=with_science,
            max_rows=max_rows_i,
        )
        recipe_path = out_root / "PARTNER_RECIPE.json"
        write_partner_recipe(
            recipe_path,
            pin=pin_final,
            free_params=params,
            run_id=str(run_id),
            las_path=las_str,
            solved=True,
            micropulse_path=mp_str,
            survey_path=survey_str,
            require_survey=bool(thr.require_survey),
            require_regime=bool(thr.require_regime),
            with_regime=with_regime,
            with_science=with_science,
        )
        partner_recipe_path = str(recipe_path.resolve())

    # P5 EOW ship (D): package inventory after SOLVED (or force UNSOLVED_SHIP)
    eow_ship_result: dict[str, Any] | None = None
    eow_ship_status: str | None = None
    eow_package_str: str | None = (
        str(Path(eow_package).resolve()) if eow_package is not None else None
    )
    if eow_package is not None:
        eow_ship_result = ship_eow_package(
            run_dir=out_root,
            eow_package=eow_package,
            solved=bool(solved),
            force_ship=bool(force_ship),
            partner_recipe_path=partner_recipe_path,
            run_id=str(run_id) if run_id is not None else None,
            free_params=params.to_dict(),
            raise_on_refuse=False,
        )
        eow_ship_status = eow_ship_result.get("status")
        if eow_ship_result.get("refused"):
            logger.warning(
                "EOW SHIP refused (not SOLVED, no --force-ship): %s",
                eow_ship_result.get("reason"),
            )
        elif eow_ship_result.get("shipped") and os_mode:
            append_ledger(
                out_root / "ledger.jsonl",
                {
                    "action": "eow_ship",
                    "status": eow_ship_status,
                    "solved": solved,
                    "force_ship": bool(force_ship),
                    "eow_package": eow_package_str,
                    "package_index": eow_ship_result.get("package_index"),
                    "ship_md": eow_ship_result.get("ship_md"),
                    "partner_recipe": partner_recipe_path,
                    "n_files": (eow_ship_result.get("inventory") or {}).get("n_files"),
                },
            )

    if os_mode and run_doc is not None:
        run_doc["status"] = "solved" if solved else stop_reason
        run_doc["stop_reason"] = stop_reason
        run_doc["final_params"] = params.to_dict()
        run_doc["n_rounds"] = len(
            [e for e in ledger if isinstance(e.get("round"), int)]
        )
        run_doc["stability_streak"] = stability_streak
        run_doc["partner_recipe"] = partner_recipe_path
        run_doc["with_regime"] = with_regime
        run_doc["with_science"] = with_science
        run_doc["with_dynamical_topology"] = with_dynamical_topology
        run_doc["topo_stability"] = topo_stability
        run_doc["eow_package"] = eow_package_str
        run_doc["eow_ship_status"] = eow_ship_status
        run_doc["eow_ship"] = (
            {
                "status": eow_ship_status,
                "ok": eow_ship_result.get("ok"),
                "shipped": eow_ship_result.get("shipped"),
                "refused": eow_ship_result.get("refused"),
                "package_index": eow_ship_result.get("package_index"),
                "ship_md": eow_ship_result.get("ship_md"),
                "banner": eow_ship_result.get("banner"),
            }
            if eow_ship_result is not None
            else None
        )
        _write_run_json(out_root, run_doc)
        if parent_for_latest is not None:
            _write_latest_run_pointer(parent_for_latest, out_root)

    # Dynamical topology MEASURE wire (info only; never pin / never ACCEPTANCE)
    dynamical_topology_report: dict[str, Any] | None = None
    dynamical_topology_path: str | None = None
    if with_dynamical_topology:
        try:
            dynamical_topology_report = _compute_dynamical_topology_report(
                out_root, ledger
            )
            dt_path = out_root / "DYNAMICAL_TOPOLOGY.json"
            dt_path.write_text(
                json.dumps(dynamical_topology_report, indent=2) + "\n",
                encoding="utf-8",
            )
            dynamical_topology_path = str(dt_path.resolve())
            logger.info(
                "dynamical topology n_stages=%s n_long=%s path=%s",
                dynamical_topology_report.get("n_stages"),
                dynamical_topology_report.get("n_long"),
                dynamical_topology_path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("dynamical topology measure skipped: %s", exc)
            dynamical_topology_report = {
                "kind": "dynamical_topology",
                "not_acceptance": True,
                "pin_writable": False,
                "acceptance_writable": False,
                "error": str(exc),
                "n_stages": 0,
            }
            try:
                dt_path = out_root / "DYNAMICAL_TOPOLOGY.json"
                dt_path.write_text(
                    json.dumps(dynamical_topology_report, indent=2) + "\n",
                    encoding="utf-8",
                )
                dynamical_topology_path = str(dt_path.resolve())
            except Exception as write_exc:  # noqa: BLE001
                logger.warning("dynamical topology write failed: %s", write_exc)

    result = {
        "ontology": (
            "job_coherence_os_p5_not_rop_score"
            if os_mode
            else "job_coherence_protocol_not_rop_score"
        ),
        "run_id": run_id,
        "os_mode": bool(os_mode),
        "stability_k": stability_k,
        "stability_streak": stability_streak,
        "solved": solved,
        "stop_reason": stop_reason,
        "n_rounds": len([e for e in ledger if isinstance(e.get("round"), int)]),
        "max_rounds": int(max_rounds),
        "thresholds": thr.to_dict(),
        "final_params": params.to_dict(),
        "partner_recipe": partner_recipe_path,
        "eow_package": eow_package_str,
        "eow_ship_status": eow_ship_status,
        "eow_ship": eow_ship_result,
        "pin_locked": {
            "depth_mono": True,
            "required_channels_for_pack": True,
            "unit_sanity": True,
            "last_ok": pin0.get("ok"),
            "note": "QC pin never negotiated by this protocol",
        },
        "ledger": ledger,
        "out_root": str(out_root.resolve()),
        "las_path": las_str,
        "micropulse_path": mp_str,
        "survey_path": survey_str,
        "survey_n_stations": int((survey_table or {}).get("n_stations") or 0),
        "require_survey": bool(thr.require_survey),
        "require_regime": bool(thr.require_regime),
        "with_regime": with_regime,
        "with_science": with_science,
        "with_dynamical_topology": with_dynamical_topology,
        "topo_stability": topo_stability,
        "dynamical_topology": dynamical_topology_report,
        "dynamical_topology_path": dynamical_topology_path,
        "chunk_rows": chunk_rows_i,
        "max_chunks": max_chunks_i,
        "max_rows": max_rows_i,
        "chunk_inspect": chunk_inspect_report,
        "trend_rollup": None,  # filled below
        "micropulse_n_fibers": (mp_bundle or {}).get("n_fibers") if mp_bundle else 0,
        "micropulse_kinds": (mp_bundle or {}).get("kinds") if mp_bundle else [],
        "note": (
            "Cyclic observe→multi-section propose→merge→ingest. "
            "Fixed-point: is_solved ∧ empty board × K. "
            "Free params: align_mode/window_scale/channel_pack/null_policy/"
            "survey_gate/regime_mode. "
            "P2: MicroPulse fiber join + structural glue. "
            "P3: survey stalk QC + optional discrete holonomy (never invent Inc/Azi). "
            "P4: regime H0 barcode + multi-scale zigzag + dual-gate science info. "
            "P5: EOW SHIP after SOLVED (or --force-ship UNSOLVED_SHIP); "
            "KB D: optional chunk_rows inspect + max_rows cap. "
            "Dynamical topology measure optional (never pin). "
            "topo_stability control optional (topology_stable × K; never pin). "
            "Job QC Firewall: explore (science/topo/λ1) vs certify (pin+fixed-point); "
            "near-miss rejected; agreement is not verification. "
            "QC pin locked. Not ROP score-chase. Never ζ→ROP."
        ),
    }
    # Relative λ1 / multi-scale trend rollup (info only)
    trend_rollup = build_trend_rollup(ledger)
    if dynamical_topology_report is not None:
        # Optional fold: shallow summary only (never ACCEPTANCE)
        trend_rollup["dynamical_topology"] = {
            "not_acceptance": True,
            "pin_writable": False,
            "n_stages": dynamical_topology_report.get("n_stages"),
            "n_long": dynamical_topology_report.get("n_long"),
            "n_short": dynamical_topology_report.get("n_short"),
            "dominant_phase": (dynamical_topology_report.get("phases") or {}).get(
                "dominant"
            ),
            "path": dynamical_topology_path,
            "kind": dynamical_topology_report.get("kind"),
        }
    result["trend_rollup"] = trend_rollup
    try:
        (out_root / "TREND_ROLLUP.json").write_text(
            json.dumps(trend_rollup, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("trend rollup write skipped: %s", exc)

    # Job QC Firewall: explicit explore vs certify (PRIMON PCF restriction)
    firewall = build_job_firewall(
        result=result,
        ledger=ledger,
        pin=pin0 if isinstance(pin0, dict) else None,
        solved=bool(solved),
        run_id=str(run_id) if run_id is not None else None,
    )
    inv = assert_firewall_invariants(firewall)
    if inv:
        logger.warning("firewall invariant violations: %s", inv)
        firewall["invariant_violations"] = inv
    result["firewall"] = firewall
    result["firewall_certified"] = bool(firewall.get("certified"))
    result["firewall_near_miss"] = bool((firewall.get("near_miss") or {}).get("near_miss"))
    firewall_path: str | None = None
    try:
        fw_path = out_root / "FIREWALL.json"
        fw_path.write_text(
            json.dumps(firewall, indent=2) + "\n", encoding="utf-8"
        )
        firewall_path = str(fw_path.resolve())
    except Exception as exc:  # noqa: BLE001
        logger.warning("FIREWALL.json write skipped: %s", exc)
    result["firewall_path"] = firewall_path

    if os_mode and run_doc is not None:
        run_doc["firewall"] = {
            "certified": firewall.get("certified"),
            "near_miss_verdict": (firewall.get("near_miss") or {}).get("verdict"),
            "near_miss": (firewall.get("near_miss") or {}).get("near_miss"),
            "explore_looks_promising": (firewall.get("explore") or {}).get(
                "looks_promising"
            ),
            "path": firewall_path,
            "ontology": firewall.get("ontology"),
            "pin_writable": False,
            "laws": firewall.get("laws"),
        }
        run_doc["firewall_certified"] = bool(firewall.get("certified"))
        _write_run_json(out_root, run_doc)

    (out_root / "COHERENCE.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    _write_coherence_md(result, out_root / "COHERENCE.md")
    return result
