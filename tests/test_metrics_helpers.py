"""Tests unit para core/metrics.py helpers — _percentile + reset/snapshot.

Diferente de test_metrics_and_exceptions.py (integration via Starlette/FastAPI
TestClient), aqui são tests unit do core funcional sem app real.
"""
from __future__ import annotations

import pytest

from nuclea_modeler.backend.core.metrics import (
    _percentile,
    reset as reset_metrics,
    snapshot,
)


# ─── _percentile ────────────────────────────────────────────────────────────


def test_percentile_empty_list_returns_none():
    assert _percentile([], 50) is None
    assert _percentile([], 95) is None
    assert _percentile([], 99) is None


def test_percentile_single_value_returns_it():
    """Edge case: 1 sample. Qualquer pct retorna esse valor."""
    assert _percentile([100.0], 50) == 100.0
    assert _percentile([100.0], 95) == 100.0
    assert _percentile([42.5], 99) == 42.5


def test_percentile_50_is_median():
    """p50 sempre usa median() — não index-based."""
    assert _percentile([1.0, 2.0, 3.0], 50) == 2.0
    # Even count → average dos dois do meio
    assert _percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5


def test_percentile_95_of_100_values():
    """p95 de 0..99 deve retornar valor próximo de 95."""
    values = [float(i) for i in range(100)]
    result = _percentile(values, 95)
    # k = 95/100 * 99 = 94.05 → int = 94 → sorted[94] = 94.0
    assert result == 94.0


def test_percentile_99_of_100_values():
    values = [float(i) for i in range(100)]
    assert _percentile(values, 99) == 98.0  # k = 99/100 * 99 ≈ 98


def test_percentile_rounds_to_2_decimals():
    """Saída arredondada para 2 casas — evita float lixo no JSON."""
    result = _percentile([1.123456], 50)
    assert result == 1.12


def test_percentile_unsorted_input_handled():
    """Função deve aceitar valores em qualquer ordem."""
    assert _percentile([3.0, 1.0, 2.0], 50) == 2.0  # median funciona unsorted
    # Para p95 (não median), a função sorta internamente
    assert _percentile([10.0, 1.0, 5.0, 3.0, 8.0], 95) == 10.0


def test_percentile_max_pct_returns_max():
    """p100 retorna o max value."""
    values = [1.0, 5.0, 10.0]
    # k clamped to len-1 = 2 → sorted[2] = 10.0
    assert _percentile(values, 100) == 10.0


# ─── reset + snapshot ──────────────────────────────────────────────────────


def test_reset_clears_all_counters():
    """reset() limpa counters E latencies — snapshot retorna empty routes."""
    # Garante state limpo do teste anterior
    reset_metrics()
    snap = snapshot()
    assert snap["routes"] == {}


def test_snapshot_includes_uptime():
    reset_metrics()
    snap = snapshot()
    assert "uptime_seconds" in snap
    assert isinstance(snap["uptime_seconds"], (int, float))
    assert snap["uptime_seconds"] >= 0
