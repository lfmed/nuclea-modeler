"""Tests for the env-driven feature flag module."""
from __future__ import annotations

from unittest.mock import patch

from nuclea_modeler.backend.core.features import (
    KNOWN_FLAGS,
    _env_key,
    get_features,
    is_enabled,
)


def _clear_cache():
    get_features.cache_clear()


def test_env_key_uppercases_with_prefix():
    assert _env_key("foo_bar") == "NUCLEA_FEATURE_FOO_BAR"
    assert _env_key("der_minimap") == "NUCLEA_FEATURE_DER_MINIMAP"


def test_all_flags_default_off():
    _clear_cache()
    with patch.dict("os.environ", {}, clear=False):
        # Ensure no NUCLEA_FEATURE_* vars leak from the host environment
        keys_to_clear = [k for k in __import__("os").environ if k.startswith("NUCLEA_FEATURE_")]
        for k in keys_to_clear:
            del __import__("os").environ[k]
        _clear_cache()
        features = get_features()
    assert set(features.keys()) == set(KNOWN_FLAGS)
    assert all(v is False for v in features.values())


def test_truthy_values_enable_flag():
    _clear_cache()
    for value in ["true", "TRUE", "1", "yes", "on", "True"]:
        with patch.dict("os.environ", {"NUCLEA_FEATURE_DER_MINIMAP": value}, clear=False):
            _clear_cache()
            assert is_enabled("der_minimap"), f"value={value!r} should enable"


def test_falsy_values_keep_flag_off():
    _clear_cache()
    for value in ["false", "0", "no", "off", "", "anything-else"]:
        with patch.dict("os.environ", {"NUCLEA_FEATURE_DER_MINIMAP": value}, clear=False):
            _clear_cache()
            assert not is_enabled("der_minimap"), f"value={value!r} should NOT enable"


def test_unknown_flag_returns_false():
    _clear_cache()
    assert is_enabled("not_a_real_flag") is False


def test_get_features_is_cached():
    """Repeat calls within a process must not re-read env (lru_cache).

    Why: avoids the cost of os.getenv * len(KNOWN_FLAGS) on every request and
    guarantees a stable snapshot per process.
    """
    _clear_cache()
    first = get_features()
    second = get_features()
    assert first is second  # same object reference proves cache hit


def test_known_flags_naming_convention():
    """All declared flags must be snake_case ASCII."""
    import string
    allowed = set(string.ascii_lowercase + string.digits + "_")
    for flag in KNOWN_FLAGS:
        assert set(flag) <= allowed, f"flag {flag!r} has illegal characters"
        assert not flag.startswith("_") and not flag.endswith("_")
        assert "__" not in flag
