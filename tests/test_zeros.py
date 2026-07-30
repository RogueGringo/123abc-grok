"""Real ζ ordinates must be computed and verified, never extrapolated or recalled."""

from __future__ import annotations

import numpy as np
import pytest

from realm.validate.zeros import (
    ZeroVerificationError,
    real_zeros,
    verify_zeros,
    window,
)
from realm.zeta_field import ZETA_ZEROS_IMAG


def test_agrees_with_repo_table():
    g = real_zeros(ZETA_ZEROS_IMAG.size)
    assert np.allclose(g, ZETA_ZEROS_IMAG, atol=1e-8)


def test_extends_beyond_repo_table():
    """The whole point: genuine ordinates past γ_15, where seeds.py would extrapolate."""
    g = real_zeros(30)
    assert g.size == 30
    assert np.all(np.diff(g) > 0)
    # γ_16 is a real zero, not the mean-gap continuation seeds.py:41 would produce
    mean_gap = float(np.mean(np.diff(ZETA_ZEROS_IMAG)))
    extrapolated = ZETA_ZEROS_IMAG[-1] + mean_gap
    assert abs(g[15] - extrapolated) > 1e-3


def test_window_is_one_indexed_and_disjoint():
    first = window(1, 14)
    second = window(15, 14)
    assert np.allclose(first, real_zeros(14))
    assert first.size == second.size == 14
    assert second[0] > first[-1]
    assert not set(np.round(first, 6)) & set(np.round(second, 6))


def test_window_rejects_zero_index():
    with pytest.raises(ValueError):
        window(0, 4)


def test_verify_rejects_non_zeros():
    """A shifted table must fail verification rather than be silently accepted."""
    g = real_zeros(10) + 0.4
    with pytest.raises(ZeroVerificationError):
        verify_zeros(g)


def test_verify_rejects_unsorted():
    g = real_zeros(10)[::-1]
    with pytest.raises(ZeroVerificationError):
        verify_zeros(g)


def test_verify_accepts_real_zeros():
    report = verify_zeros(real_zeros(20))
    assert report["verified"] is True
    assert report["max_abs_siegelz"] < 1e-6
    assert abs(report["N_T_asymptotic"] - 20) < 2.0


def test_cache_hit_still_verifies(tmp_path):
    """verify=True must verify even when the value comes from cache (PR #2 review).

    A cache hit previously returned unverified values, so correctness depended on
    the cache file never being edited or truncated.
    """
    cache = tmp_path / "z.json"
    good = real_zeros(20, cache=cache)  # writes a verified cache
    assert np.allclose(real_zeros(20, cache=cache), good)

    # Tamper with the values but keep the verified stamp.
    import json as _json

    blob = _json.loads(cache.read_text(encoding="utf-8"))
    blob["gammas"][5] += 0.5
    cache.write_text(_json.dumps(blob), encoding="utf-8")
    # Must not return the tampered value: verification fails, cache is rebuilt.
    out = real_zeros(20, cache=cache)
    assert np.allclose(out, good), "tampered cache was trusted"


def test_cache_without_verified_stamp_is_rebuilt(tmp_path):
    import json as _json

    cache = tmp_path / "z.json"
    good = real_zeros(18, cache=cache)
    blob = _json.loads(cache.read_text(encoding="utf-8"))
    blob["verification"] = {}  # stamp removed
    cache.write_text(_json.dumps(blob), encoding="utf-8")
    assert np.allclose(real_zeros(18, cache=cache), good)


def test_verify_sets_precision_explicitly():
    """Ambient mpmath precision must not be able to cause a false failure."""
    import mpmath as mp

    mp.mp.dps = 5  # deliberately too low
    report = verify_zeros(real_zeros(15))
    assert report["verified"] is True
    assert mp.mp.dps == 30
