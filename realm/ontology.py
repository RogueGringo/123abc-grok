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
        "substrate": "ZetaField / make_seed → SpectralAction S_Λ(θ)",
        "dynamics": "Crit(S) preferred holonomies θ*",
        "projection": "Crit multimode/planar C_N ⊂ R³ → Kabsch softmin ranking",
        "operator": "MaxOp CellularSheaf connection Laplacian L(A(θ))",
    },
    "external_goal": "cyclic_native_vs_decoy_enrichment_under_crit_projection",
    "axioms_primary": ["G1", "G2", "G3", "1.1", "2.4", "4.1", "5.2", "6.2", "12.3"],
}


def ontology_note() -> str:
    return (
        "ζ=substrate seed only; operational goal=Crit→geometry projection "
        "(+ MaxOp L dual). Never λ=γ."
    )
