from toestub.envelope import build_envelope


def test_envelope_forces_explore_not_acceptance():
    env = build_envelope(
        ok=True,
        surface="ok",
        certified=False,
        explore={"looks_promising": True, "not_acceptance": False, "pin_writable": True},
    )
    assert env["explore"]["not_acceptance"] is True
    assert env["explore"]["pin_writable"] is False
    assert env["pin_writable"] is False


def test_envelope_error():
    env = build_envelope(ok=False, surface="fail", error="missing las")
    assert env["ok"] is False
    assert env["error"] == "missing las"
    assert env["certified"] is None
