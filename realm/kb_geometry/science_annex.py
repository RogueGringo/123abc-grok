"""Science annex holdout language (Stalk B).

Transfer from: ACADEMIC Mathematics of Machine Learning (PAC / holdout /
model selection language) + in-repo dual-gate known-solutions discipline.

Every science annex must carry:
  - not_acceptance: true
  - split tags for probe vs holdout when available
  - claim_class: informational

Never writes LengthPolicy pin. Never sets ACCEPTANCE / SHIP.
"""

from __future__ import annotations

from typing import Any

SCIENCE_ANNEX_KIND = "science_theory_annex"
KB_SOURCE = (
    "ACADEMIC/Mathematics of Machine Learning (Petersen) + "
    "dual-gate known-solutions path"
)
TRANSFER_NOTE = (
    "PAC/holdout language for science splits; never train pin; "
    "never ACCEPTANCE from enrichment"
)

_REQUIRED_DISCLAIMERS = (
    "Science annex is informational only.",
    "NOT ACCEPTANCE / NOT SHIP success.",
    "Commercial success remains openable PDBs + dual-gate pin (or Job OS glue+QC pin).",
    "Probe metrics must not be confused with holdout generalization.",
    "Never λ=γ. Never retune pin for score.",
)


def build_science_annex_base(
    *,
    kind: str = SCIENCE_ANNEX_KIND,
    split: str | None = None,
    extra_disclaimers: list[str] | None = None,
) -> dict[str, Any]:
    """Canonical science-theory fields required on every science annex."""
    split_norm = (split or "unspecified").lower().strip()
    if split_norm not in (
        "probe",
        "holdout",
        "expand",
        "mixed",
        "unspecified",
        "all_ok",
    ):
        split_norm = "unspecified"

    disclaimers = list(_REQUIRED_DISCLAIMERS)
    if extra_disclaimers:
        for d in extra_disclaimers:
            if d not in disclaimers:
                disclaimers.append(str(d))

    return {
        "kind": kind,
        "claim_class": "informational",
        "not_acceptance": True,
        "split": split_norm,
        "kb_source": KB_SOURCE,
        "transfer_note": TRANSFER_NOTE,
        "ontology": "science_annex_not_lambda_eq_gamma",
        "disclaimers": disclaimers,
        "pin_writable": False,
        "acceptance_writable": False,
    }


def attach_science_theory(
    annex: dict[str, Any],
    *,
    split: str | None = None,
    mean_by_split: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge theory fields into an existing science annex dict (in-place + return)."""
    base = build_science_annex_base(
        kind=str(annex.get("kind") or SCIENCE_ANNEX_KIND),
        split=split or annex.get("split"),
    )
    # Preserve existing keys; force hard fields
    out = dict(annex)
    out["claim_class"] = "informational"
    out["not_acceptance"] = True
    out["pin_writable"] = False
    out["acceptance_writable"] = False
    out["split"] = base["split"] if split is None and not annex.get("split") else (
        (split or annex.get("split") or base["split"])
    )
    if "kb_source" not in out:
        out["kb_source"] = base["kb_source"]
    if "transfer_note" not in out:
        out["transfer_note"] = base["transfer_note"]
    if "ontology" not in out or "not_lambda" not in str(out.get("ontology") or ""):
        out["ontology"] = base["ontology"]

    # Merge disclaimers
    existing = list(out.get("disclaimers") or [])
    for d in base["disclaimers"]:
        if d not in existing:
            existing.append(d)
    out["disclaimers"] = existing

    if mean_by_split is not None:
        out["mean_by_split"] = mean_by_split
        # Explicit probe vs holdout separation for PAC-style reading
        out["generalization"] = {
            "probe": mean_by_split.get("curated_probe")
            or mean_by_split.get("probe"),
            "holdout": mean_by_split.get("curated_holdout")
            or mean_by_split.get("holdout"),
            "note": (
                "Holdout is the generalization check; probe is development signal. "
                "Neither is ACCEPTANCE."
            ),
            "not_acceptance": True,
        }
    return out


def is_informational_only(annex: dict[str, Any] | None) -> bool:
    """True iff annex asserts not_acceptance and informational claim class."""
    if not annex:
        return False
    if annex.get("not_acceptance") is not True and annex.get("informational_only") is not True:
        return False
    # pin must not be writable
    if annex.get("pin_writable") is True:
        return False
    if annex.get("acceptance_writable") is True:
        return False
    return True


def assert_science_not_acceptance(annex: dict[str, Any]) -> None:
    """Raise ValueError if annex could be misread as ACCEPTANCE."""
    if not is_informational_only(annex):
        raise ValueError(
            "science annex missing not_acceptance / informational guards "
            "(would violate dual-gate science discipline)"
        )
    if annex.get("not_acceptance") is not True:
        raise ValueError("science annex requires not_acceptance=true")
