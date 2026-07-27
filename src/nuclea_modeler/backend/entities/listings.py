"""Helpers das listagens de sistema — coluna de flags + agregação em lote.

Contexto (ponto 5 do plano feedback-cliente-jul2026): as listagens de
entidades e atributos passaram a exibir uma coluna de flags e a permitir
filtro "por flag". Buscar as flags de cada linha com uma query por linha
explodiria o número de round-trips ao SQL warehouse (N+1). Este módulo
resolve isso com **uma única query agregada por página**, filtrada pelos
ids da página via lista de parâmetros nomeados (`:id0, :id1, …`).

Os ids de entidade/atributo são UUIDs gerados pelo servidor (`delta.new_id`),
mas ainda assim usamos parâmetros — nunca interpolação — por disciplina de
segurança consistente com o resto do backend.

Exporta também `flag_filter_exists_clause`, que monta o predicado
`EXISTS (SELECT 1 FROM …_flags …)` reutilizado tanto no COUNT quanto na query
de página das listagens, garantindo que total e itens fiquem coerentes quando
há filtro por flag.
"""
from __future__ import annotations

from ..core import delta
from ..core._nuclea_config import get_settings
from .models import FlagBadge


def _named_in_params(prefix: str, ids: list[str]) -> tuple[str, list]:
    """Monta um placeholder `(:p0, :p1, …)` + a lista de parâmetros delta.

    Retorna (placeholders_sql, params). Lista vazia → ("(NULL)", []) para que
    o `IN` seja válido e não case com nada.
    """
    if not ids:
        return "(NULL)", []
    names = [f"{prefix}{i}" for i in range(len(ids))]
    placeholders = "(" + ", ".join(f":{n}" for n in names) + ")"
    params = [delta.param(n, v) for n, v in zip(names, ids)]
    return placeholders, params


def flags_by_entity(sql, entity_ids: list[str]) -> dict[str, list[FlagBadge]]:
    """Retorna {entity_id: [FlagBadge, …]} para os ids dados (1 query só).

    Inclui flags propagadas (is_propagated=true) — o objetivo da coluna é dar
    visibilidade de "esta entidade tem flag X", inclusive as herdadas de colunas.
    """
    if not entity_ids:
        return {}
    s = get_settings()
    placeholders, params = _named_in_params("e", entity_ids)
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT ef.entity_id, f.flag_id, f.flag_key, f.display_name,
               f.color_hex, f.category
        FROM {s.fq_table('entity_flags')} ef
        JOIN {s.fq_table('flags')} f ON f.flag_id = ef.flag_id
        WHERE ef.entity_id IN {placeholders}
        ORDER BY f.category, f.display_name
        """,
        params,
    )
    out: dict[str, list[FlagBadge]] = {}
    for r in rows:
        out.setdefault(r[0], []).append(
            FlagBadge(
                flag_id=r[1], flag_key=r[2], display_name=r[3],
                color_hex=r[4], category=r[5],
            )
        )
    return out


def flags_by_attribute(sql, attribute_ids: list[str]) -> dict[str, list[FlagBadge]]:
    """Retorna {attribute_id: [FlagBadge, …]} para os ids dados (1 query só)."""
    if not attribute_ids:
        return {}
    s = get_settings()
    placeholders, params = _named_in_params("a", attribute_ids)
    rows = delta.fetch_all_params(
        sql,
        f"""
        SELECT af.attribute_id, f.flag_id, f.flag_key, f.display_name,
               f.color_hex, f.category
        FROM {s.fq_table('attribute_flags')} af
        JOIN {s.fq_table('flags')} f ON f.flag_id = af.flag_id
        WHERE af.attribute_id IN {placeholders}
        ORDER BY f.category, f.display_name
        """,
        params,
    )
    out: dict[str, list[FlagBadge]] = {}
    for r in rows:
        out.setdefault(r[0], []).append(
            FlagBadge(
                flag_id=r[1], flag_key=r[2], display_name=r[3],
                color_hex=r[4], category=r[5],
            )
        )
    return out


def escape_like(q: str) -> str:
    """Escape de wildcards SQL LIKE (%, _, \\). Aspas ficam por conta dos
    parâmetros. Mesma lógica de search/router._escape_like — duplicada aqui
    para não acoplar listagens ao módulo de busca."""
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
