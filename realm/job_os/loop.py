"""Job Coherence OS loop: observe → multi-section propose → merge → re-execute.

OS mode: RUN.json, ledger.jsonl, stability-K fixed-point, PARTNER_RECIPE on SOLVED,
optional resume.

Fixed-point: is_solved ∧ empty free-param board for K consecutive cycles.
Pin re-checked every round and never written/adapted.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

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
        "",
        "## Ontology",
        "",
        "- Substrate: raw multi-channel series",
        "- Pin: QC locked (depth mono, required channels, unit sanity)",
        "- Free: align_mode, window_scale, channel_pack, null_policy, survey_gate, regime_mode",
        "- Survey stalk (B): QC total G/MagF + optional discrete holonomy",
        "- Regime stalk (C): windowed H0 on SSSI/TOR/RPM; dual-gate science info",
        "- Fixed-point: is_solved ∧ empty board × K",
        "- Science score never sets SOLVED alone (unless --require-regime stalk)",
        "- Never retune pin for score. Never invent Inc/Azi. Never ζ→ROP.",
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
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    """Ingest LAS (+ optional MicroPulse/survey/regime) → pin → observe."""
    cycle_dir.mkdir(parents=True, exist_ok=True)
    p = params.clamp()
    raw = parse_las(las_path)
    # Null-policy on surface skeleton first; then join presence-only MP fibers
    # so length-mismatched channels never drive surface row drops.
    series = apply_null_policy(raw, p.null_policy)
    series = join_surface_micropulse(series, mp_bundle)
    series = select_channel_pack(series, p.channel_pack)

    pin = verify_job_pin(
        series,
        pack=p.channel_pack,
        depth_mono_eps=float(thr.depth_mono_eps),
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
        },
        "science": {
            "enabled": science_report.get("enabled"),
            "native_score": science_report.get("native_score"),
            "decoy_score": science_report.get("decoy_score"),
            "native_beats_decoy": science_report.get("native_beats_decoy"),
            "informational_only": True,
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
) -> dict[str, Any]:
    """Execute cyclic observe→multi-section propose→merge→ingest until coherent.

    QC pin is re-checked every round and never written/adapted.

    OS mode (os_mode=True): RUN.json, ledger.jsonl, stability-K fixed-point,
    PARTNER_RECIPE on SOLVED, optional resume.

    Fixed-point: is_solved ∧ empty free-param board for K consecutive cycles.

    P2: optional micropulse_path (dir of CSVs or single file) joins downhole fibers.
    P3: optional survey_path and/or SURVEY fiber in MicroPulse; survey_gate free param.
    P4: --with-regime / --with-science dual-gate info; --require-regime optional gate.
    """
    thr = thresholds or JobThresholds()
    params = (initial or FreeParams()).clamp()
    out_root = Path(out_root)
    stability_k = max(1, int(stability_k))
    parent_for_latest: Path | None = None
    with_regime = bool(with_regime)
    with_science = bool(with_science)

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

            if solved_slice and empty_board:
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
                "cycle_dir": str(cycle_dir.resolve()),
                "proposals": [pr.to_dict() for pr in board_props],
                "sources": summary,
            }

            # Fixed-point: is_solved ∧ empty board × K consecutive cycles
            if solved_slice and empty_board and stability_streak >= stability_k:
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
                    "job SOLVED at round %s score=%.3f streak=%s/%s",
                    rnd,
                    score,
                    stability_streak,
                    stability_k,
                )
                break

            if solved_slice and empty_board and stability_streak < stability_k:
                entry["action"] = "stability_hold"
                entry["reason"] = f"streak_{stability_streak}_of_{stability_k}"
                entry["next_params"] = params.to_dict()
                _commit_entry(entry, cycle_dir)
                logger.info(
                    "stability hold round %s streak=%s/%s",
                    rnd,
                    stability_streak,
                    stability_k,
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
        _write_run_json(out_root, run_doc)
        if parent_for_latest is not None:
            _write_latest_run_pointer(parent_for_latest, out_root)

    result = {
        "ontology": (
            "job_coherence_os_p4_not_rop_score"
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
        "micropulse_n_fibers": (mp_bundle or {}).get("n_fibers") if mp_bundle else 0,
        "micropulse_kinds": (mp_bundle or {}).get("kinds") if mp_bundle else [],
        "note": (
            "Cyclic observe→multi-section propose→merge→ingest. "
            "Fixed-point: is_solved ∧ empty board × K. "
            "Free params: align_mode/window_scale/channel_pack/null_policy/"
            "survey_gate/regime_mode. "
            "P2: MicroPulse fiber join + structural glue. "
            "P3: survey stalk QC + optional discrete holonomy (never invent Inc/Azi). "
            "P4: regime H0 barcode + dual-gate science info (not accept gate). "
            "QC pin locked. Not ROP score-chase. Never ζ→ROP."
        ),
    }
    (out_root / "COHERENCE.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    _write_coherence_md(result, out_root / "COHERENCE.md")
    return result
