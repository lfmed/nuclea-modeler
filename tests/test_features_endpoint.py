"""Integration tests para o GET /api/features endpoint.

Diferente de test_features.py (unit-level), aqui montamos um FastAPI mínimo
com o endpoint real e validamos: response shape, JSON content-type,
flags ativadas via env são refletidas, flags ausentes default false.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

starlette = pytest.importorskip("starlette")
fastapi = pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nuclea_modeler.backend.core.features import KNOWN_FLAGS, get_features
from nuclea_modeler.backend.models import FeaturesOut


def _make_app() -> FastAPI:
    """FastAPI app mínimo com só o /features endpoint real."""
    app = FastAPI()

    @app.get("/api/features", response_model=FeaturesOut)
    async def features() -> FeaturesOut:
        return FeaturesOut(features=get_features())

    return app


@pytest.fixture(autouse=True)
def _clear_features_cache():
    """Limpa lru_cache antes de cada teste para que env mudanças sejam vistas."""
    get_features.cache_clear()
    yield
    get_features.cache_clear()


# ─── Response shape ─────────────────────────────────────────────────────────


def test_returns_200_with_features_dict():
    client = TestClient(_make_app())
    r = client.get("/api/features")
    assert r.status_code == 200
    body = r.json()
    assert "features" in body
    assert isinstance(body["features"], dict)


def test_response_contains_all_known_flags():
    """A response deve listar TODAS as flags declaradas em KNOWN_FLAGS,
    para que o frontend tenha um set completo (default false p/ desconhecidas)."""
    client = TestClient(_make_app())
    r = client.get("/api/features")
    body = r.json()
    assert set(body["features"].keys()) == set(KNOWN_FLAGS)


def test_response_is_json():
    client = TestClient(_make_app())
    r = client.get("/api/features")
    assert "application/json" in r.headers.get("content-type", "")


def test_all_flags_false_by_default():
    """Sem env vars setadas, todas as flags retornam false."""
    import os
    # Limpa qualquer NUCLEA_FEATURE_* do env do host
    keys = [k for k in os.environ if k.startswith("NUCLEA_FEATURE_")]
    with patch.dict(os.environ, {}, clear=False):
        for k in keys:
            del os.environ[k]
        get_features.cache_clear()
        client = TestClient(_make_app())
        r = client.get("/api/features")
        body = r.json()
        assert all(v is False for v in body["features"].values())


# ─── Env var → endpoint reflection ──────────────────────────────────────────


def test_env_var_enables_flag_via_endpoint():
    with patch.dict("os.environ", {"NUCLEA_FEATURE_DER_MINIMAP": "true"}, clear=False):
        get_features.cache_clear()
        client = TestClient(_make_app())
        r = client.get("/api/features")
        body = r.json()
        assert body["features"]["der_minimap"] is True
        # Outras continuam false
        assert body["features"]["embarcadero_v2"] is False


def test_multiple_env_vars_enable_multiple_flags():
    with patch.dict(
        "os.environ",
        {
            "NUCLEA_FEATURE_DER_MINIMAP": "true",
            "NUCLEA_FEATURE_EMBARCADERO_V2": "1",
            "NUCLEA_FEATURE_VERSIONS_SIGNED": "yes",
        },
        clear=False,
    ):
        get_features.cache_clear()
        client = TestClient(_make_app())
        body = client.get("/api/features").json()
        assert body["features"]["der_minimap"] is True
        assert body["features"]["embarcadero_v2"] is True
        assert body["features"]["versions_signed"] is True


def test_unknown_env_var_ignored():
    """NUCLEA_FEATURE_NOT_DECLARED não deve aparecer no response."""
    with patch.dict(
        "os.environ", {"NUCLEA_FEATURE_NOT_DECLARED": "true"}, clear=False
    ):
        get_features.cache_clear()
        client = TestClient(_make_app())
        body = client.get("/api/features").json()
        assert "not_declared" not in body["features"]


# ─── Multi-call stability ───────────────────────────────────────────────────


def test_repeated_calls_return_same_snapshot():
    """get_features tem lru_cache — chamadas seguidas no mesmo processo
    devolvem o mesmo snapshot. Isso é essencial para evitar skew entre
    requests durante uma única session do worker."""
    with patch.dict("os.environ", {"NUCLEA_FEATURE_DER_MINIMAP": "true"}, clear=False):
        get_features.cache_clear()
        client = TestClient(_make_app())
        r1 = client.get("/api/features").json()
        r2 = client.get("/api/features").json()
        r3 = client.get("/api/features").json()
        assert r1 == r2 == r3
