"""Validações semânticas pra índices + particionamento.

Roda lado servidor (resposta de um endpoint dedicado) pra detectar
configurações redundantes ou suspeitas — o usuário vê os warnings no card
de Índices e decide se ajusta ou ignora. Não bloqueia mutations.

Regras cobertas:
    - PK_DUPLICATE: índice tem exatamente as colunas da PK (mesma ordem)
    - PK_LEADING: índice começa com todas as colunas da PK (subset à frente)
    - INDEX_SUBSET: índice X é prefixo de outro índice Y (mesmas cols líderes)
    - PARTITION_NULLABLE: coluna de particionamento é nullable
    - PARTITION_UNKNOWN_COLUMN: coluna de particionamento não existe na tabela
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

WarningCode = Literal[
    "PK_DUPLICATE",
    "PK_LEADING",
    "INDEX_SUBSET",
    "PARTITION_NULLABLE",
    "PARTITION_UNKNOWN_COLUMN",
]

WarningSeverity = Literal["info", "warning"]


class IndexValidationWarning(BaseModel):
    code: WarningCode
    severity: WarningSeverity
    message: str
    # Ids relacionados ao warning. Frontend usa pra destacar o item
    # afetado no card.
    related_index_ids: list[str] = []


def _idx_col_names(index: dict) -> list[str]:
    """Extrai a lista de nomes de coluna (em ordem) de um índice."""
    out: list[str] = []
    for c in index.get("columns") or []:
        nm = c.get("name") if isinstance(c, dict) else None
        if nm:
            out.append(nm)
    return out


def validate_indexes(
    *,
    attributes: list[dict],
    indexes: list[dict],
    partitioning: dict | None,
) -> list[IndexValidationWarning]:
    """Roda todas as regras de validação. Retorna lista vazia se tudo limpo.

    Args:
        attributes: rows de attributes (dict com ``technical_name``,
            ``is_primary_key``, ``is_nullable``).
        indexes: rows de entity_indexes (dict com ``index_id``, ``index_name``,
            ``columns`` (lista de {name, direction})).
        partitioning: row de entity_partitioning ou None.
    """
    warnings: list[IndexValidationWarning] = []

    pk_cols = [
        a["technical_name"] for a in attributes
        if a.get("is_primary_key") and a.get("technical_name")
    ]
    attr_names = {a["technical_name"] for a in attributes if a.get("technical_name")}
    nullable_attrs = {
        a["technical_name"] for a in attributes
        if a.get("is_nullable") and a.get("technical_name")
    }

    # ─── Regras por índice ───────────────────────────────────────────────
    for ix in indexes:
        cols = _idx_col_names(ix)
        ix_id = ix.get("index_id") or ""
        ix_name = ix.get("index_name") or "(sem nome)"

        if pk_cols and cols == pk_cols:
            warnings.append(IndexValidationWarning(
                code="PK_DUPLICATE",
                severity="warning",
                message=(
                    f"Índice '{ix_name}' duplica a PK ({', '.join(pk_cols)}). "
                    "PKs já vêm com índice implícito no SGBD."
                ),
                related_index_ids=[ix_id],
            ))
        elif (
            pk_cols
            and len(cols) >= len(pk_cols)
            and cols[: len(pk_cols)] == pk_cols
        ):
            warnings.append(IndexValidationWarning(
                code="PK_LEADING",
                severity="info",
                message=(
                    f"Índice '{ix_name}' começa pela PK — possivelmente "
                    "redundante para consultas que já usam a chave primária."
                ),
                related_index_ids=[ix_id],
            ))

    # ─── Subset: índice X é prefixo de Y ────────────────────────────────
    for i, ix_a in enumerate(indexes):
        cols_a = _idx_col_names(ix_a)
        if not cols_a:
            continue
        for j, ix_b in enumerate(indexes):
            if i == j:
                continue
            cols_b = _idx_col_names(ix_b)
            if len(cols_b) <= len(cols_a):
                continue
            if cols_b[: len(cols_a)] == cols_a:
                warnings.append(IndexValidationWarning(
                    code="INDEX_SUBSET",
                    severity="info",
                    message=(
                        f"Índice '{ix_a.get('index_name')}' é prefixo de "
                        f"'{ix_b.get('index_name')}' — o segundo cobre o "
                        "mesmo padrão de query."
                    ),
                    related_index_ids=[
                        ix_a.get("index_id") or "",
                        ix_b.get("index_id") or "",
                    ],
                ))
                break  # 1 warning por A é suficiente

    # ─── Partição ───────────────────────────────────────────────────────
    if partitioning and partitioning.get("strategy") not in (None, "NONE"):
        for col in partitioning.get("columns") or []:
            if col not in attr_names:
                warnings.append(IndexValidationWarning(
                    code="PARTITION_UNKNOWN_COLUMN",
                    severity="warning",
                    message=(
                        f"Coluna de particionamento '{col}' não existe na "
                        "tabela — corrija antes de gerar o DDL."
                    ),
                    related_index_ids=[],
                ))
            elif col in nullable_attrs:
                warnings.append(IndexValidationWarning(
                    code="PARTITION_NULLABLE",
                    severity="warning",
                    message=(
                        f"Coluna de particionamento '{col}' é nullable. "
                        "PostgreSQL/Oracle exigem NOT NULL na chave de partição."
                    ),
                    related_index_ids=[],
                ))

    return warnings
