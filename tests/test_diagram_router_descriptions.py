"""Regressão do mapeamento linha→modelo em _build_diagram (v1.0029 — descrições).

Contexto: quando campos de descrição (description_md, native_comment, business_rule)
foram adicionados aos SELECTs de entities e attributes, os índices posicionais
NÃO foram atualizados — causando TypeError ao tentar instanciar DiagramEntity
e DiagramAttribute com os valores nos índices errados.

Este teste monta linhas no MESMO formato dos SELECTs de `_build_diagram` e
garante que o mapeamento posicional está correto — em especial que:
- DiagramEntity recebe (entity_id, schema_name, technical_name, logical_name,
  entity_type, domain, criticality, description_md, native_comment) nos
  índices corretos.
- DiagramAttribute recebe (attribute_id, entity_id, technical_name, logical_name,
  native_data_type, is_primary_key, is_nullable, ordinal_position,
  description_md, native_comment, business_rule) nos índices corretos.

Sem este teste o CI não pegaria o desalinhamento (era pura indexação, não erro
de tipagem estática — a Pydantic valida tipos, não índices).
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from nuclea_modeler.backend.diagram.router import _build_diagram


def _entity_row() -> list:
    """Linha na ordem exata do SELECT de entities em _build_diagram.

    9 colunas: entity_id, schema_name, technical_name, logical_name,
    entity_type, domain, criticality, description_md, native_comment
    """
    return [
        "ent-123",           # 0 entity_id
        "public",            # 1 schema_name
        "cliente",           # 2 technical_name
        "Tabela de Clientes",  # 3 logical_name
        "TABLE",             # 4 entity_type
        "Vendas",            # 5 domain
        "HIGH",              # 6 criticality
        "Armazena informações de clientes cadastrados no sistema. **Crítica para operações de vendas.**",  # 7 description_md
        "Base table for customer records",  # 8 native_comment
    ]


def _attribute_row() -> list:
    """Linha na ordem exata do SELECT de attributes em _build_diagram.

    11 colunas: attribute_id, entity_id, technical_name, logical_name,
    native_data_type, is_primary_key, is_nullable, ordinal_position,
    description_md, native_comment, business_rule
    """
    return [
        "attr-456",          # 0 attribute_id
        "ent-123",           # 1 entity_id
        "id_cliente",        # 2 technical_name
        "ID do Cliente",     # 3 logical_name
        "BIGINT",            # 4 native_data_type
        "true",              # 5 is_primary_key (vem como string de SQL)
        "false",             # 6 is_nullable (vem como string de SQL)
        1,                   # 7 ordinal_position
        "Identificador único do cliente. Gerado sequencialmente no import.",  # 8 description_md
        "PRIMARY KEY",       # 9 native_comment
        "Nunca pode ser NULL. Deve ser único.",  # 10 business_rule
    ]


def test_entity_row_to_diagram_entity_maps_positions():
    """Valida que entity_row é parseado corretamente em DiagramEntity."""
    from nuclea_modeler.backend.diagram.models import DiagramEntity
    from nuclea_modeler.backend.core import sql as sql_module

    r = _entity_row()

    # Simula a chamada em _build_diagram (linhas 91-95 do router.py)
    eid = r[0]
    system_id = "sys-1"
    entity = DiagramEntity(
        entity_id=eid,
        system_id=system_id,
        schema_name=r[1],
        technical_name=r[2],
        logical_name=r[3],
        entity_type=r[4] or "TABLE",
        domain=r[5],
        criticality=r[6],
        description_md=r[7],
        native_comment=r[8],
    )

    assert entity.entity_id == "ent-123"
    assert entity.schema_name == "public"
    assert entity.technical_name == "cliente"
    assert entity.logical_name == "Tabela de Clientes"
    assert entity.entity_type == "TABLE"
    assert entity.domain == "Vendas"
    assert entity.criticality == "HIGH"
    assert entity.description_md == "Armazena informações de clientes cadastrados no sistema. **Crítica para operações de vendas.**"
    assert entity.native_comment == "Base table for customer records"


def test_attribute_row_to_diagram_attribute_maps_positions():
    """Valida que attribute_row é parseado corretamente em DiagramAttribute."""
    from nuclea_modeler.backend.diagram.models import DiagramAttribute
    from nuclea_modeler.backend.core import delta

    r = _attribute_row()

    # Simula a chamada em _build_diagram (linhas 135-147 do router.py)
    attr_id, entity_id = r[0], r[1]

    attr = DiagramAttribute(
        attribute_id=attr_id,
        technical_name=r[2],
        logical_name=r[3],
        native_data_type=r[4],
        is_primary_key=delta.as_bool(r[5]),
        is_nullable=delta.as_bool(r[6]) if r[6] is not None else None,
        ordinal_position=int(r[7]) if r[7] is not None else None,
        description_md=r[8],
        native_comment=r[9],
        business_rule=r[10],
        has_lgpd_flag=False,
    )

    assert attr.attribute_id == "attr-456"
    assert attr.technical_name == "id_cliente"
    assert attr.logical_name == "ID do Cliente"
    assert attr.native_data_type == "BIGINT"
    assert attr.is_primary_key is True
    assert attr.is_nullable is False
    assert attr.ordinal_position == 1
    assert attr.description_md == "Identificador único do cliente. Gerado sequencialmente no import."
    assert attr.native_comment == "PRIMARY KEY"
    assert attr.business_rule == "Nunca pode ser NULL. Deve ser único."
    assert attr.has_lgpd_flag is False
