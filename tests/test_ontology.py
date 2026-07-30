from realm.ontology import ONTOLOGY, ontology_note


def test_ontology_substrate_not_target():
    assert "substrate" in ONTOLOGY["zeta_role"]
    assert "lambda_eq_gamma" in ONTOLOGY["never"]
    assert "projection" in ONTOLOGY["layers"]
    assert "operator" in ONTOLOGY["layers"]
    note = ontology_note()
    assert "substrate" in note.lower() or "ζ=substrate" in note
