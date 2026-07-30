from realm.validate import hf_io


def test_hf_available_bool():
    assert isinstance(hf_io.hf_available(), bool)


def test_list_cpsea_ids_from_text(tmp_path):
    p = tmp_path / "demo.tsv"
    p.write_text("id\n1CSA\n2MYY\nnotanid\n1CSA\n", encoding="utf-8")
    ids = hf_io.list_cpsea_demo_pdb_ids(p, limit=10)
    assert "1CSA" in ids
