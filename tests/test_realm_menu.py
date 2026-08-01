"""Non-interactive unit tests for realm_menu navigator (pure builders only)."""

from __future__ import annotations

from realm.menu.app import build_job_smoke_argv, menu_items


def test_menu_items_include_core():
    labels = [x["label"] for x in menu_items()]
    assert any("Job OS" in L for L in labels)
    assert any("Catalog" in L for L in labels)
    assert any("topology" in L.lower() for L in labels)


def test_smoke_argv_contains_fixture():
    argv = build_job_smoke_argv("out/x")
    joined = " ".join(argv)
    assert "--os" in argv or "--os" in joined
    assert "mini_edr.las" in joined


def test_menu_items_ids_stable():
    items = menu_items()
    by_id = {x["id"]: x["label"] for x in items}
    assert by_id["job_smoke"].startswith("Job OS")
    assert by_id["job_wizard"].startswith("Job OS")
    assert "Catalog" in by_id["catalog"]
    assert "topology" in by_id["topology"].lower()
    assert "Handoff" in by_id["handoff"]
    assert "docs" in by_id["docs"].lower() or "LATEST" in by_id["docs"]
    assert by_id["exit"] == "Exit"
    assert set(by_id) >= {
        "job_smoke",
        "job_wizard",
        "catalog",
        "topology",
        "handoff",
        "docs",
        "exit",
    }


def test_smoke_argv_core_flags():
    argv = build_job_smoke_argv("out/menu_test")
    joined = " ".join(str(a) for a in argv)
    assert "--with-regime" in argv or "--with-regime" in joined
    assert "--with-dynamical-topology" in argv or "--with-dynamical-topology" in joined
    assert "surface_min" in joined
    assert "persist_h0" in joined
    assert "menu_smoke" in joined
    assert "out/menu_test" in joined or "out\\menu_test" in joined
