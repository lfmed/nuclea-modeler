"""Export CSV/XLSX de metadados enriquecido com tipo/nulabilidade/PK/FK (rodada 9, item 5).

O cliente pediu que os exports do Sync Catalog trouxessem tipagem, nulabilidade,
PK e FK. Estes testes documentam o contrato:

- CSV: as colunas canônicas de sempre + `fk_references` no FIM.
- XLSX: as 4 colunas do Embarcadero + schema/data_type/is_nullable/is_pk/fk_references.
- `fk_references` = "schema.tabela.coluna" do PAI, na linha da coluna-FK (filha).
- A orientação do relacionamento é decidida pela PK, não por source/target (dado
  legado vem invertido — mesmo gotcha do marcador FK do DER, v1.0057).
- As linhas chegam no formato REAL da Statement Execution API: booleanos e arrays
  como STRING (`"true"`, `'["attr-x"]'`) — lição do v1.0042 (CI verde, prod quebrada
  por testar só com tipos Python prontos).
"""
from __future__ import annotations

import csv
import io

from nuclea_modeler.backend.core import delta
from nuclea_modeler.backend.entities import roundtrip

# ─── fk_references_by_attr (lógica pura) ─────────────────────────────────────

META = {
    "p-id": {"schema": "vendas", "table": "pedido", "column": "id", "is_pk": True},
    "i-id": {"schema": "vendas", "table": "item", "column": "id", "is_pk": True},
    "i-fk": {"schema": "vendas", "table": "item", "column": "pedido_id", "is_pk": False},
    "c-id": {"schema": "crm", "table": "cliente", "column": "id", "is_pk": True},
}


def test_fk_convencao_source_pai():
    rels = [{"source_attr_ids": ["p-id"], "target_attr_ids": ["i-fk"]}]
    assert roundtrip.fk_references_by_attr(rels, META) == {"i-fk": "vendas.pedido.id"}


def test_fk_orientacao_invertida_decidida_pela_pk():
    """Dado legado: source=FILHO / target=PAI. A FK continua na coluna NÃO-PK."""
    rels = [{"source_attr_ids": ["i-fk"], "target_attr_ids": ["p-id"]}]
    assert roundtrip.fk_references_by_attr(rels, META) == {"i-fk": "vendas.pedido.id"}


def test_fk_pk_pk_cai_na_convencao():
    rels = [{"source_attr_ids": ["p-id"], "target_attr_ids": ["i-id"]}]
    assert roundtrip.fk_references_by_attr(rels, META) == {"i-id": "vendas.pedido.id"}


def test_fk_multiplas_referencias_e_ponta_desconhecida():
    rels = [
        {"source_attr_ids": ["p-id"], "target_attr_ids": ["i-fk"]},
        {"source_attr_ids": ["c-id"], "target_attr_ids": ["i-fk"]},
        {"source_attr_ids": ["p-id"], "target_attr_ids": ["i-fk"]},  # duplicada
        {"source_attr_ids": ["fora-do-sistema"], "target_attr_ids": ["i-fk"]},
        {"source_attr_ids": [], "target_attr_ids": []},
    ]
    assert roundtrip.fk_references_by_attr(rels, META) == {
        "i-fk": "vendas.pedido.id; crm.cliente.id",
    }


# ─── export_system_csv / export_system_xlsx (formato real da API) ────────────

# Ordem do SELECT do CSV: schema, table, table_logical, table_desc, domain,
# criticality, column, column_logical, data_type, is_pk, is_nullable,
# column_desc, ordinal, attribute_id — tudo STRING, como a API devolve.
_CSV_ROWS = [
    ["vendas", "pedido", None, None, None, None, "id", None, "bigint", "true", "false", None, "1", "p-id"],
    ["vendas", "item", None, None, None, None, "id", None, "bigint", "true", "false", None, "1", "i-id"],
    ["vendas", "item", None, None, None, None, "pedido_id", None, "bigint", "false", "true", "fk", "2", "i-fk"],
]
# Relacionamento com arrays como string JSON e orientação INVERTIDA (legado).
_REL_ROWS = [["rel-1", "ent-item", "ent-pedido", '["i-fk"]', '["p-id"]', None, None, "Item → Pedido"]]


def _fake_fetch(attr_rows):
    def fetch(_sql, query, *_a, **_k):
        if "relationships" in query:
            return _REL_ROWS
        if "attribute_flags" in query:
            return []
        return attr_rows
    return fetch


def test_export_csv_tem_fk_e_respeita_booleanos_string(monkeypatch):
    monkeypatch.setattr(delta, "fetch_all_params", _fake_fetch(_CSV_ROWS))
    out = list(csv.DictReader(io.StringIO(roundtrip.export_system_csv(None, "sys-x"))))
    assert list(out[0].keys()) == roundtrip.CSV_EXPORT_HEADERS
    by_col = {(r["table"], r["column"]): r for r in out}
    fk = by_col[("item", "pedido_id")]
    assert fk["fk_references"] == "vendas.pedido.id"
    assert fk["is_pk"] == "false" and fk["is_nullable"] == "true"
    assert by_col[("pedido", "id")]["is_pk"] == "true"
    assert by_col[("pedido", "id")]["fk_references"] == ""


def test_export_csv_sem_relacionamentos_nao_quebra(monkeypatch):
    def fetch(_sql, query, *_a, **_k):
        if "relationships" in query:
            raise RuntimeError("tabela indisponível")
        return _CSV_ROWS
    monkeypatch.setattr(delta, "fetch_all_params", fetch)
    out = list(csv.DictReader(io.StringIO(roundtrip.export_system_csv(None, "sys-x"))))
    assert all(r["fk_references"] == "" for r in out)


# Ordem do SELECT do XLSX: table, table_desc, column, column_desc, ordinal,
# attribute_id, schema, data_type, is_nullable, is_pk.
_XLSX_ROWS = [
    ["pedido", None, "id", None, "1", "p-id", "vendas", "bigint", "false", "true"],
    ["item", None, "id", None, "1", "i-id", "vendas", "bigint", "false", "true"],
    ["item", None, "pedido_id", "fk", "2", "i-fk", "vendas", "bigint", None, "false"],
]


def test_export_xlsx_colunas_extras_e_reimport_compativel(monkeypatch):
    from openpyxl import load_workbook

    monkeypatch.setattr(delta, "fetch_all_params", _fake_fetch(_XLSX_ROWS))
    data = roundtrip.export_system_xlsx(None, "sys-x")
    ws = load_workbook(io.BytesIO(data)).active
    rows = list(ws.iter_rows(values_only=True))
    assert list(rows[0]) == [
        "table", "table_description", "column", "column_description",
        *roundtrip.XLSX_EXTRA_HEADERS,
    ]
    fk = next(r for r in rows[1:] if r[2] == "pedido_id")
    assert fk[4:] == ("vendas", "bigint", "true", "false", "vendas.pedido.id")
    # O leitor do import ignora as colunas extras (indexa por nome de cabeçalho).
    parsed = roundtrip._read_xlsx_rows(data)
    assert {"table", "column", "table_description", "column_description"} == set(parsed[0])
