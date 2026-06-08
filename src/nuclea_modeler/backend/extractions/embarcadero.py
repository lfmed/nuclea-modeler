"""Parser Embarcadero ER/Studio .DM1 → ExtractionSnapshot.

O formato .DM1 do ER/Studio é texto ASCII multi-seção (CSV interno). Cada
seção tem uma linha-cabeçalho com o nome (ex: ``Entity``), uma linha de
colunas CSV e N linhas de dados. Nomes (Entity/Attribute) ficam em
``SmallString`` / ``LargeString`` e são referenciados por ``*NameId`` que é
direto o ``String_Id``.

Public API:
    parse_dm1(text, system_id) -> (snapshot, warnings)
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime

from .models import (
    ExtractedAttribute,
    ExtractedEntity,
    ExtractedIndex,
    ExtractedIndexColumn,
    ExtractionSnapshot,
)

# ─── Mapping DatatypeId → nome canônico ──────────────────────────────────────
# IDs observados em exports reais de IDEF1 / Generic do ER/Studio. Lista não
# é exaustiva — IDs desconhecidos viram "UNKNOWN" e um aviso é emitido. O
# usuário pode ajustar depois pelo TypePicker do app.
_DATATYPE_MAP: dict[int, str] = {
    # IDs observados em exports reais (calibrado contra arquivos da Núclea).
    # Quando o ER/Studio usa Length > 0, o tipo é parametrizado.
    1: "CHAR",
    2: "VARCHAR",
    3: "LONG",
    4: "NUMBER",
    5: "DATE",
    6: "BLOB",
    7: "CLOB",
    8: "INTEGER",
    9: "SMALLINT",
    10: "VARCHAR",
    11: "TEXT",
    12: "TEXT",
    13: "NUMERIC",
    14: "REAL",
    15: "FLOAT",
    16: "DOUBLE PRECISION",
    17: "BIT",
    18: "TIME",
    19: "TIMESTAMP",
    20: "DATETIME",
    25: "DATE",
    31: "INTEGER",
    65: "TIMESTAMP",
    84: "NUMERIC",
    89: "BOOLEAN",
    101: "BIGINT",
}

_SECTION_HEADER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


# ─── Section splitter ───────────────────────────────────────────────────────


def _parse_sections(text: str) -> dict[str, list[dict[str, str]]]:
    """Splita texto DM1 em dict {nome_seção: [row_dict, ...]}.

    Acumula seções com mesmo nome (algumas, como ``Model``, aparecem
    múltiplas vezes). Linhas malformadas (count de colunas diferente do
    header) são descartadas.
    """
    lines = text.splitlines()
    sections: dict[str, list[dict[str, str]]] = {}
    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        # Próxima seção: linha com só um identificador
        if s and _SECTION_HEADER_RE.match(s):
            section_name = s
            if i + 1 >= n:
                break
            header_line = lines[i + 1]
            try:
                headers = next(csv.reader(io.StringIO(header_line)))
            except Exception:
                i += 1
                continue
            i += 2
            rows: list[dict[str, str]] = []
            while i < n:
                row_line = lines[i]
                if not row_line.strip():
                    i += 1
                    continue
                # Próxima seção? Pára sem consumir.
                stripped = row_line.strip()
                if _SECTION_HEADER_RE.match(stripped):
                    break
                try:
                    row = next(csv.reader(io.StringIO(row_line)))
                    if len(row) == len(headers):
                        rows.append(dict(zip(headers, row)))
                except Exception:
                    pass
                i += 1
            sections.setdefault(section_name, []).extend(rows)
        else:
            i += 1
    return sections


# ─── Helpers ────────────────────────────────────────────────────────────────


def _to_int(value: str | None, default: int = 0) -> int:
    if value is None:
        return default
    v = str(value).strip()
    if not v or v.lower() == "null":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _build_string_pool(sections: dict[str, list[dict[str, str]]]) -> dict[str, str]:
    """Funde SmallString + LargeString num único índice ``String_Id → Data``."""
    pool: dict[str, str] = {}
    for r in sections.get("SmallString", []):
        sid = r.get("String_Id", "").strip()
        if sid:
            pool[sid] = r.get("Data", "") or ""
    for r in sections.get("LargeString", []):
        sid = r.get("String_Id", "").strip()
        if sid:
            pool[sid] = r.get("Data", "") or ""
    return pool


def _native_type(
    datatype_id: int,
    length: int,
    scale: int,
    unknown_types: set[int],
) -> str | None:
    """Compõe nome canônico do tipo a partir do DatatypeId + Length/Scale.

    Retorna ``None`` se o DatatypeId for desconhecido E sem Length útil
    (deixa o app decidir o tipo default no DER).
    """
    base = _DATATYPE_MAP.get(datatype_id)
    if base is None:
        unknown_types.add(datatype_id)
        # Sem mapping conhecido, tenta inferir grosseiramente pelo Length
        if length > 0 and scale > 0:
            return f"NUMERIC({length},{scale})"
        if length > 0:
            return f"VARCHAR({length})"
        return None

    # Aceita Length quando tipo aceita parâmetro
    if base in ("VARCHAR", "CHAR", "VARCHAR2"):
        if length > 0:
            return f"{base}({length})"
        return base
    if base in ("NUMERIC", "NUMBER", "DECIMAL"):
        if length > 0 and scale >= 0:
            return f"{base}({length},{scale})"
        if length > 0:
            return f"{base}({length})"
        return base
    return base


# ─── Parser ─────────────────────────────────────────────────────────────────


def parse_dm1(text: str, system_id: str) -> tuple[ExtractionSnapshot, list[str]]:
    """Parse um arquivo .DM1 (Embarcadero ER/Studio) em ``ExtractionSnapshot``.

    Args:
        text: Conteúdo do arquivo .DM1 já decodificado (ASCII/Latin-1).
        system_id: ID do sistema-alvo do snapshot.

    Returns:
        ``(snapshot, warnings)``. ``snapshot.entities`` pode ser vazio se o
        arquivo não tiver seção ``Entity`` reconhecível — chamador deve
        checar antes de gerar diff.
    """
    warnings: list[str] = []
    if text is None or not text.strip():
        raise ValueError("Arquivo .DM1 vazio")

    # BOM e CRLF são tolerados (splitlines() lida com ambos)
    cleaned = text.lstrip("﻿")

    sections = _parse_sections(cleaned)
    if not sections.get("Entity"):
        # Não encontrou nem a seção Entity — provavelmente não é DM1
        raise ValueError(
            "Formato não reconhecido: seção 'Entity' não encontrada. "
            "Esperado: arquivo .DM1 exportado pelo Embarcadero ER/Studio."
        )

    strings = _build_string_pool(sections)

    # Entity rows → dict por EntityId pra cruzar com Attribute/PK/FK
    entities_raw = sections.get("Entity", [])
    attrs_raw = sections.get("Attribute", [])
    pks_raw = sections.get("PrimaryKey", [])
    fks_raw = sections.get("ForeignKey", [])

    # Index attributes por (EntityId, AttributeId) e por EntityId
    attrs_by_entity: dict[str, list[dict[str, str]]] = {}
    attr_name_by_key: dict[tuple[str, str], str] = {}
    for a in attrs_raw:
        eid = a.get("EntityId", "")
        attrs_by_entity.setdefault(eid, []).append(a)
        attr_name_by_key[(eid, a.get("AttributeId", ""))] = (
            strings.get(a.get("AttributeNameId", ""), "").strip()
        )

    # Index PKs por (EntityId, AttributeId)
    pk_set: set[tuple[str, str]] = set()
    for p in pks_raw:
        pk_set.add((p.get("EntityId", ""), p.get("AttributeId", "")))

    # Index Indexes + IndexColumn por (EntityId, IndexId).
    # Skip KeyType=="P" (primary keys já cobertas pela seção PrimaryKey).
    idx_rows = sections.get("Indexes", [])
    idx_col_rows = sections.get("IndexColumn", [])
    # ER/Studio duplica rows entre modelo lógico (ModelId=1) e físico (=2).
    # Dedup por (EntityId, IndexId) e (EntityId, IndexId, AttributeId).
    idx_cols_by_key: dict[tuple[str, str], list[dict[str, str]]] = {}
    seen_idx_col: set[tuple[str, str, str]] = set()
    for c in idx_col_rows:
        ck = (c.get("EntityId", ""), c.get("IndexId", ""), c.get("AttributeId", ""))
        if ck in seen_idx_col:
            continue
        seen_idx_col.add(ck)
        key = (c.get("EntityId", ""), c.get("IndexId", ""))
        idx_cols_by_key.setdefault(key, []).append(c)
    indexes_by_entity: dict[str, list[ExtractedIndex]] = {}
    seen_idx: set[tuple[str, str]] = set()
    for ix in idx_rows:
        if ix.get("KeyType") == "P":
            continue
        ent_id = ix.get("EntityId", "")
        idx_id = ix.get("IndexId", "")
        if (ent_id, idx_id) in seen_idx:
            continue
        seen_idx.add((ent_id, idx_id))
        idx_name = strings.get(ix.get("IndexNameId", ""), "").strip()
        if not idx_name:
            continue
        cols_for_idx = sorted(
            idx_cols_by_key.get((ent_id, idx_id), []),
            key=lambda r: _to_int(r.get("SequenceNo"), default=0),
        )
        index_cols: list[ExtractedIndexColumn] = []
        for c in cols_for_idx:
            cname = attr_name_by_key.get((ent_id, c.get("AttributeId", "")), "").strip()
            if not cname:
                continue
            direction = "DESC" if (c.get("SortOrdering") or "A").upper() == "D" else "ASC"
            index_cols.append(ExtractedIndexColumn(name=cname, direction=direction))
        if not index_cols:
            continue
        # KeyType="U" → UNIQUE constraint. is_unique é flag separada
        # (não duplica em index_type pra evitar redundância na UI).
        is_unique = (ix.get("KeyType") or "").upper() == "U"
        indexes_by_entity.setdefault(ent_id, []).append(
            ExtractedIndex(
                index_name=idx_name,
                index_type="BTREE",
                is_unique=is_unique,
                columns=index_cols,
            )
        )

    # Index entity name por EntityId pra resolver FKs
    entity_name_by_id: dict[str, str] = {}
    unknown_types: set[int] = set()
    entities: list[ExtractedEntity] = []

    for e in entities_raw:
        eid = e.get("EntityId", "")
        name = strings.get(e.get("EntityNameId", ""), "").strip()
        table_name = strings.get(e.get("TableNameId", ""), "").strip()
        physical = (table_name or name).strip()
        if not physical:
            warnings.append(f"entity sem nome (EntityId={eid}) — ignorada")
            continue
        entity_name_by_id[eid] = physical

        # Owner/schema: tem OwnerId mas pode não estar mapeado. Default 'dbo'
        # — ER/Studio usa por convenção quando não configurado.
        owner_id = e.get("OwnerId", "")
        schema = strings.get(owner_id, "").strip() or "dbo"

        definition = strings.get(e.get("DefinitionId", ""), "").strip() or None

        # Attributes desta entity (dedupe por nome — ER/Studio propaga FK
        # como linhas extras na seção Attribute; mantemos a 1ª ocorrência).
        ent_attrs: list[ExtractedAttribute] = []
        seen_attr_names: set[str] = set()
        idx = 0
        for a in attrs_by_entity.get(eid, []):
            aid = a.get("AttributeId", "")
            attr_name = strings.get(a.get("AttributeNameId", ""), "").strip()
            if not attr_name:
                warnings.append(
                    f"attribute sem nome (EntityId={eid}, AttributeId={aid}) — ignorado"
                )
                continue
            if attr_name in seen_attr_names:
                continue
            seen_attr_names.add(attr_name)
            idx += 1
            dt_id = _to_int(a.get("DatatypeId"))
            length = _to_int(a.get("Length"), default=-1)
            scale = _to_int(a.get("Scale"), default=-1)
            native = _native_type(dt_id, length, scale, unknown_types)
            nullable_raw = (a.get("Nullable") or "").strip().upper()
            # ER/Studio: "Y"/"N" ou "1"/"0"
            if nullable_raw in ("Y", "1", "TRUE"):
                nullable = True
            elif nullable_raw in ("N", "0", "FALSE"):
                nullable = False
            else:
                nullable = None
            ent_attrs.append(
                ExtractedAttribute(
                    technical_name=attr_name,
                    ordinal_position=idx,
                    native_data_type=native,
                    is_nullable=nullable,
                    default_value=None,
                    is_primary_key=(eid, aid) in pk_set,
                    native_comment=strings.get(a.get("DefinitionId", ""), "").strip()
                    or None,
                )
            )

        entities.append(
            ExtractedEntity(
                schema_name=schema,
                technical_name=physical,
                entity_type="TABLE",
                native_comment=definition,
                attributes=ent_attrs,
                indexes=indexes_by_entity.get(eid, []),
            )
        )

    # Relationships: emitidas como warnings (parser ainda não persiste
    # estruturalmente — alinhado com comportamento anterior do .erx).
    rel_count = 0
    for fk in fks_raw:
        parent_id = fk.get("ParentEntityId", "")
        child_id = fk.get("ChildEntityId", "")
        parent_name = entity_name_by_id.get(parent_id, f"<{parent_id}>")
        child_name = entity_name_by_id.get(child_id, f"<{child_id}>")
        if parent_id and child_id:
            rel_count += 1
            warnings.append(f"relationship detected: {parent_name} → {child_name}")

    if rel_count:
        warnings.insert(
            0,
            f"{rel_count} relacionamento(s) detectado(s) — não persistidos nesta versão",
        )

    if unknown_types:
        warnings.append(
            "DatatypeIds desconhecidos (revisar tipos no DER): "
            + ", ".join(str(x) for x in sorted(unknown_types))
        )

    # Dedup por (schema, technical_name): ER/Studio armazena cada entity 2x
    # — uma no modelo lógico (ModelId=1) e outra no físico (ModelId=2). A
    # representação física vem depois e geralmente tem tipos mais corretos,
    # então mantemos a última ocorrência por chave (e mesclamos índices,
    # que podem aparecer no lógico mas não no físico ou vice-versa).
    deduped: dict[tuple[str, str], ExtractedEntity] = {}
    for e in entities:
        key = (e.schema_name, e.technical_name)
        prev = deduped.get(key)
        if prev:
            # Mescla índices que faltam (dedup por nome) sem sobrescrever atributos.
            seen_idx_names = {ix.index_name for ix in e.indexes}
            for ix in prev.indexes:
                if ix.index_name not in seen_idx_names:
                    e.indexes.append(ix)
        deduped[key] = e

    snapshot = ExtractionSnapshot(
        source_kind="EMBARCADERO",
        system_id=system_id,
        captured_at=datetime.utcnow(),
        schemas=sorted({e.schema_name for e in deduped.values()}),
        entities=list(deduped.values()),
    )
    return snapshot, warnings
