"""Tests para validate_indexes — regras semânticas de índices/partição."""
from __future__ import annotations

from nuclea_modeler.backend.entities.index_validation import validate_indexes


def _attr(name: str, pk: bool = False, nullable: bool | None = False) -> dict:
    return {"technical_name": name, "is_primary_key": pk, "is_nullable": nullable}


def _ix(name: str, cols: list[str], idx_id: str = "") -> dict:
    return {
        "index_id": idx_id or f"idx-{name}",
        "index_name": name,
        "columns": [{"name": c, "direction": "ASC"} for c in cols],
    }


# ─── PK duplicate / leading ─────────────────────────────────────────────────


def test_warns_on_pk_duplicate():
    attrs = [_attr("id", pk=True), _attr("nome")]
    warns = validate_indexes(
        attributes=attrs,
        indexes=[_ix("ix_id", ["id"])],
        partitioning=None,
    )
    assert any(w.code == "PK_DUPLICATE" for w in warns)


def test_warns_on_pk_leading():
    attrs = [_attr("id", pk=True), _attr("data")]
    warns = validate_indexes(
        attributes=attrs,
        indexes=[_ix("ix_id_data", ["id", "data"])],
        partitioning=None,
    )
    assert any(w.code == "PK_LEADING" for w in warns)


def test_no_warn_when_index_unrelated_to_pk():
    attrs = [_attr("id", pk=True), _attr("email")]
    warns = validate_indexes(
        attributes=attrs,
        indexes=[_ix("ix_email", ["email"])],
        partitioning=None,
    )
    assert not warns


# ─── Subset ─────────────────────────────────────────────────────────────────


def test_warns_when_index_is_prefix_of_another():
    warns = validate_indexes(
        attributes=[_attr("a"), _attr("b"), _attr("c")],
        indexes=[
            _ix("ix_a", ["a"]),
            _ix("ix_a_b_c", ["a", "b", "c"]),
        ],
        partitioning=None,
    )
    codes = [w.code for w in warns]
    assert codes.count("INDEX_SUBSET") == 1
    # Garante que o warning referencia ambos os índices
    subset = next(w for w in warns if w.code == "INDEX_SUBSET")
    assert len(subset.related_index_ids) == 2


def test_no_subset_for_independent_indexes():
    warns = validate_indexes(
        attributes=[_attr("a"), _attr("b")],
        indexes=[
            _ix("ix_a", ["a"]),
            _ix("ix_b", ["b"]),
        ],
        partitioning=None,
    )
    assert not any(w.code == "INDEX_SUBSET" for w in warns)


# ─── Particionamento ────────────────────────────────────────────────────────


def test_warns_partition_nullable_column():
    warns = validate_indexes(
        attributes=[
            _attr("id", pk=True),
            _attr("data", nullable=True),
        ],
        indexes=[],
        partitioning={"strategy": "RANGE", "columns": ["data"]},
    )
    assert any(w.code == "PARTITION_NULLABLE" for w in warns)


def test_warns_partition_unknown_column():
    warns = validate_indexes(
        attributes=[_attr("id", pk=True)],
        indexes=[],
        partitioning={"strategy": "RANGE", "columns": ["typo_data"]},
    )
    assert any(w.code == "PARTITION_UNKNOWN_COLUMN" for w in warns)


def test_no_partition_warning_when_strategy_none():
    warns = validate_indexes(
        attributes=[_attr("a", nullable=True)],
        indexes=[],
        partitioning={"strategy": "NONE", "columns": ["a"]},
    )
    assert not warns
