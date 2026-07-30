"""Project ontology — substrate vs projection vs operator (AXiomZ G1).

ζ is **not** the target identity (never λ=γ). It is the generative *substrate*
field whose known ordinates seed SpectralAction → Crit(θ*). Operational
evidence lives on:

  1. Projection — Crit-induced geometry vs external CA rings (ranking)
  2. Operator   — MaxOp/numpy connection Laplacian L(A(θ)) dual fingerprints

AXiomZ anchors:
  G1 Ontological selection — choose this dual, not eigenvalue matching
  G2 Value genesis — S_Λ warps holonomy into Crit geometry
  G3 Least resistance — Crit + mold fit as geodesic on operational geometry
  2.4 Operational geometry — Kabsch softmin mold is M_v
  4.1 Topological invariance — L spectrum / H0 / frustration
  6.2 Continuity guard — full multi-seed batch before defaults
  12.3 Commit vs resolve — projection claims only after verification
"""

from __future__ import annotations

ONTOLOGY = {
    "name": "substrate_projection_operator_dual",
    "zeta_role": "substrate_seed_field_not_physical_eigenvalues",
    "never": ["lambda_eq_gamma", "residual_seating_as_zeta_preference"],
    "layers": {
        "substrate": "arithmetic base / ζ ordinates → SpectralAction S_Λ(θ) (generative seed)",
        "dynamics": "Witten–Morse: Crit(S) selects preferred holonomies θ*",
        "operator": "cellular sheaf over C_N; L=δ*δ connection Laplacian (MaxOp); fibers R^d",
        "monodromy": "SO(2) restriction map on cut edge carries holonomy θ",
        "projection": "Crit embeds → 3D cyclic geometry → Kabsch softmin ranking",
        "aqft_proxy": "local observables {gap,frustration,logZ} on Crit cycle net",
    },
    "external_goal": "cyclic_native_vs_decoy_enrichment_under_crit_projection",
    "fold_protocol": "substrate→Crit(S)→MaxOp L net→mold bank→projection ranking",
    "axioms_primary": ["G1", "G2", "G3", "1.1", "2.4", "4.1", "5.2", "6.2", "12.3"],
    "math_refs_informal": [
        "Witten 1982 Supersymmetry and Morse Theory (Morse deformation analogy)",
        "cellular sheaves / connection Laplacian (discrete geometric analysis)",
        "Haag–Kastler local nets (combinatorial proxy only on Crit cycle)",
    ],
}


def ontology_note() -> str:
    return (
        "ζ=substrate seed only; operational goal=Crit→geometry projection "
        "(+ MaxOp L dual). Never λ=γ."
    )
