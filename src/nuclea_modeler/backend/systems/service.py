"""Serviço de sistemas — purge/limpeza do modelo retendo histórico.

"Limpar" e "Excluir" um sistema removem o CONTEÚDO DE MODELO (entities,
attributes, relationships, schemas, diagramas, índices, flags, lineage e code
objects). O HISTÓRICO é retido de propósito:

- antes do purge, um **snapshot de versão** (M8, tabela `model_versions`) é
  publicado — recuperável via "Versões" (restore);
- `reconciliation_tickets`, `sync_log`, `extractions`, `audit_log` e `connections`
  NÃO são apagados (registro histórico do que foi feito);
- as tabelas Delta têm Change Data Feed + time-travel, então as linhas apagadas
  seguem recuperáveis por `VERSION AS OF` em caso de engano.

A ordem dos DELETEs é child→parent porque os filhos usam subquery nas tabelas
pai (entities/attributes/diagrams) — elas precisam existir até o passo final.
"""
from __future__ import annotations

from ..core import delta
from ..core._nuclea_config import get_settings
from ..core.sql import Sql


def purge_system_model(sql: Sql, system_id: str) -> None:
    """Apaga todo o conteúdo de modelo de um sistema (mantém o histórico).

    Não toca em `systems`, `model_versions`, `reconciliation_tickets`,
    `sync_log`, `extractions`, `connections`, `glossary_terms`, `flags`.
    """
    s = get_settings()
    p = [delta.param("sid", system_id)]

    ent_sub = f"(SELECT entity_id FROM {s.fq_table('entities')} WHERE system_id = :sid)"
    attr_sub = (
        f"(SELECT a.attribute_id FROM {s.fq_table('attributes')} a "
        f"JOIN {s.fq_table('entities')} e ON e.entity_id = a.entity_id "
        f"WHERE e.system_id = :sid)"
    )
    diag_sub = f"(SELECT diagram_id FROM {s.fq_table('diagrams')} WHERE system_id = :sid)"

    # Ordem importa: filhos (que referenciam pais por subquery) primeiro.
    statements = [
        f"DELETE FROM {s.fq_table('attribute_flags')} WHERE attribute_id IN {attr_sub}",
        f"DELETE FROM {s.fq_table('glossary_mappings')} WHERE attribute_id IN {attr_sub}",
        f"DELETE FROM {s.fq_table('attributes')} WHERE entity_id IN {ent_sub}",
        f"DELETE FROM {s.fq_table('entity_flags')} WHERE entity_id IN {ent_sub}",
        f"DELETE FROM {s.fq_table('entity_indexes')} WHERE entity_id IN {ent_sub}",
        f"DELETE FROM {s.fq_table('entity_partitioning')} WHERE entity_id IN {ent_sub}",
        f"DELETE FROM {s.fq_table('lineage_upstream')} WHERE entity_id IN {ent_sub}",
        f"DELETE FROM {s.fq_table('lineage_downstream')} WHERE entity_id IN {ent_sub}",
        f"DELETE FROM {s.fq_table('views_catalog')} WHERE view_entity_id IN {ent_sub}",
        f"DELETE FROM {s.fq_table('diagram_entities')} WHERE diagram_id IN {diag_sub}",
        f"DELETE FROM {s.fq_table('diagrams')} WHERE system_id = :sid",
        f"DELETE FROM {s.fq_table('relationships')} WHERE system_id = :sid",
        f"DELETE FROM {s.fq_table('schemas')} WHERE system_id = :sid",
        f"DELETE FROM {s.fq_table('der_layouts')} WHERE system_id = :sid",
        f"DELETE FROM {s.fq_table('procedures_catalog')} WHERE system_id = :sid",
        f"DELETE FROM {s.fq_table('triggers_catalog')} WHERE system_id = :sid",
        f"DELETE FROM {s.fq_table('sequences_catalog')} WHERE system_id = :sid",
        f"DELETE FROM {s.fq_table('entities')} WHERE system_id = :sid",
    ]
    for stmt in statements:
        delta.run_params(sql, stmt, p)


def count_entities(sql: Sql, system_id: str) -> int:
    s = get_settings()
    row = delta.fetch_one_params(
        sql,
        f"SELECT COUNT(*) FROM {s.fq_table('entities')} WHERE system_id = :sid",
        [delta.param("sid", system_id)],
    )
    return int(row[0]) if row else 0
