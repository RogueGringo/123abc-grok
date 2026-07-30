from pathlib import Path

from realm.validate.pdb_io import parse_ca_trace


def test_parse_fixture():
    text = Path("tests/fixtures/mini_cyclic.pdb").read_text(encoding="utf-8")
    xyz = parse_ca_trace(text, chain="A")
    assert xyz.ndim == 2 and xyz.shape[1] == 3 and xyz.shape[0] >= 3
