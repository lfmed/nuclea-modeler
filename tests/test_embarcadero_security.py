"""Tests do parser .DM1 do Embarcadero.

O formato .DM1 é texto ASCII multi-seção (CSV interno) — não há vetor XXE
ou DTD a defender (o parser antigo .erx XML usava defusedxml). Aqui
validamos: payloads malformados degradam graciosamente, payload válido é
parseado corretamente, e nomes vêm do pool de strings indireto.
"""
from __future__ import annotations

import pytest

from nuclea_modeler.backend.extractions.embarcadero import parse_dm1


# ─── Robustez contra entrada malformada ─────────────────────────────────────


def test_rejects_empty():
    """Arquivo vazio deve levantar ValueError explícito."""
    with pytest.raises(ValueError, match="vazio"):
        parse_dm1("", system_id="sys-test")


def test_rejects_random_text():
    """Texto aleatório (sem seção Entity) deve falhar com mensagem clara."""
    with pytest.raises(ValueError, match="Entity"):
        parse_dm1("this is not a DM1 file\njust random bytes\n", system_id="sys-test")


def test_ignores_malformed_rows():
    """Linhas com count de colunas errado são descartadas, não derrubam o parse."""
    payload = (
        "Entity\n"
        "DiagramId,ModelId,EntityId,EntityNameId,TableNameId,OwnerId,DefinitionId\n"
        "1,1,10,100,100,0,0\n"
        "ROW_COM_COLUNAS_DEMAIS_OU_DE_MENOS,xxx\n"
        "1,1,11,101,101,0,0\n"
        "\n"
        "SmallString\n"
        "String_Id,Data,Overflow,ConstantString,Row_Time_Stamp\n"
        "100,clientes,0,0,0\n"
        "101,produtos,0,0,0\n"
    )
    snap, _ = parse_dm1(payload, system_id="sys-test")
    assert {e.technical_name for e in snap.entities} == {"clientes", "produtos"}


# ─── Parse legítimo ─────────────────────────────────────────────────────────


def test_parses_legitimate_dm1_payload():
    """Payload mínimo válido: 1 entity, 2 atributos (1 PK), nomes via SmallString."""
    payload = (
        "Entity\n"
        "DiagramId,ModelId,EntityId,EntityNameId,TableNameId,OwnerId,DefinitionId\n"
        "1,1,5,50,50,0,0\n"
        "\n"
        "Attribute\n"
        "DiagramId,ModelId,EntityId,AttributeId,AttributeNameId,DatatypeId,Length,Scale,Nullable,DefinitionId\n"
        "1,1,5,1,60,8,-2,-1,N,0\n"
        "1,1,5,2,61,10,100,-1,Y,0\n"
        "\n"
        "PrimaryKey\n"
        "DiagramId,ModelId,EntityId,AttributeId,PrimaryKey_ID,Attribute_ID,SequenceNo,Global_User_ID,Row_Time_Stamp\n"
        "1,1,5,1,1,60,1,0,0\n"
        "\n"
        "SmallString\n"
        "String_Id,Data,Overflow,ConstantString,Row_Time_Stamp\n"
        "50,cliente,0,0,0\n"
        "60,id_cliente,0,0,0\n"
        "61,nome,0,0,0\n"
    )
    snap, warns = parse_dm1(payload, system_id="sys-test")
    assert len(snap.entities) == 1
    ent = snap.entities[0]
    assert ent.technical_name == "cliente"
    assert len(ent.attributes) == 2
    pk = [a for a in ent.attributes if a.is_primary_key]
    assert len(pk) == 1 and pk[0].technical_name == "id_cliente"
    assert pk[0].native_data_type == "INTEGER"
    nome = next(a for a in ent.attributes if a.technical_name == "nome")
    assert nome.native_data_type == "VARCHAR(100)"
    assert nome.is_nullable is True
    assert warns == [] or all("desconhec" not in w for w in warns)


def test_relationships_emitted_as_warnings():
    """ForeignKey vira warning informativo (não é persistido estruturalmente)."""
    payload = (
        "Entity\n"
        "DiagramId,ModelId,EntityId,EntityNameId,TableNameId,OwnerId,DefinitionId\n"
        "1,1,10,100,100,0,0\n"
        "1,1,11,101,101,0,0\n"
        "\n"
        "SmallString\n"
        "String_Id,Data,Overflow,ConstantString,Row_Time_Stamp\n"
        "100,pedido,0,0,0\n"
        "101,item_pedido,0,0,0\n"
        "\n"
        "ForeignKey\n"
        "DiagramId,ModelId,RelationshipId,ForeignKey_ID,ParentEntityId,ChildEntityId,Global_User_ID,Row_Time_Stamp\n"
        "1,1,1,1,10,11,0,0\n"
    )
    _, warns = parse_dm1(payload, system_id="sys-test")
    assert any("pedido → item_pedido" in w for w in warns)
    assert any("1 relacionamento" in w for w in warns)


def test_extracts_indexes_with_columns():
    """Seção Indexes + IndexColumn é extraída, com dedup lógico/físico e
    skip de KeyType=P (já coberto pela seção PrimaryKey)."""
    payload = (
        "Entity\n"
        "DiagramId,ModelId,EntityId,EntityNameId,TableNameId,OwnerId,DefinitionId\n"
        "1,2,10,100,100,0,0\n"
        "\n"
        "Attribute\n"
        "DiagramId,ModelId,EntityId,AttributeId,AttributeNameId,DatatypeId,Length,Scale,Nullable,DefinitionId\n"
        "1,2,10,1,200,8,-2,-1,N,0\n"
        "1,2,10,2,201,10,80,-1,Y,0\n"
        "\n"
        "Indexes\n"
        "DiagramId,ModelId,EntityId,IndexId,Indexes_ID,Entity_ID,IsUniqueId,IndexTypeId,KeyType,HashSize,HashSizeTypeId,IgnoreDupKeyId,DupRowId,NoSortId,SortOrderingId,IndexNameId,Flags,NSTFlag,CompareFlags,Global_User_ID,Row_Time_Stamp,ColumnStoreId\n"
        "1,2,10,1,1,10,13,0,U,0,0,0,0,0,0,300,0,0,0,0,0,0\n"
        "1,2,10,2,2,10,13,0,P,0,0,0,0,0,0,301,0,0,0,0,0,0\n"
        "\n"
        "IndexColumn\n"
        "DiagramId,ModelId,EntityId,IndexId,AttributeId,IndexColumn_ID,Attribute_ID,Indexes_ID,SequenceNo,SortOrdering,ColumnName_PDId,Global_User_ID,Row_Time_Stamp\n"
        "1,2,10,1,2,1,201,1,1,D,0,0,0\n"
        "\n"
        "SmallString\n"
        "String_Id,Data,Overflow,ConstantString,Row_Time_Stamp\n"
        "100,clientes,0,0,0\n"
        "200,id_cliente,0,0,0\n"
        "201,email,0,0,0\n"
        "300,ix_email_unico,0,0,0\n"
        "301,pk_clientes,0,0,0\n"
    )
    snap, _ = parse_dm1(payload, system_id="sys-test")
    assert len(snap.entities) == 1
    ent = snap.entities[0]
    # KeyType=P pulado, KeyType=U mantido como UNIQUE
    assert len(ent.indexes) == 1
    ix = ent.indexes[0]
    assert ix.index_name == "ix_email_unico"
    assert ix.is_unique is True
    assert len(ix.columns) == 1
    assert ix.columns[0].name == "email"
    assert ix.columns[0].direction == "DESC"  # SortOrdering=D


def test_unknown_datatype_emits_warning():
    """DatatypeId fora do mapping conhecido cai pra fallback VARCHAR/UNKNOWN com warning."""
    payload = (
        "Entity\n"
        "DiagramId,ModelId,EntityId,EntityNameId,TableNameId,OwnerId,DefinitionId\n"
        "1,1,1,10,10,0,0\n"
        "\n"
        "Attribute\n"
        "DiagramId,ModelId,EntityId,AttributeId,AttributeNameId,DatatypeId,Length,Scale,Nullable,DefinitionId\n"
        "1,1,1,1,11,9999,80,-1,Y,0\n"
        "\n"
        "SmallString\n"
        "String_Id,Data,Overflow,ConstantString,Row_Time_Stamp\n"
        "10,t,0,0,0\n"
        "11,c,0,0,0\n"
    )
    snap, warns = parse_dm1(payload, system_id="sys-test")
    # Fallback usa Length pra adivinhar VARCHAR
    assert snap.entities[0].attributes[0].native_data_type == "VARCHAR(80)"
    assert any("DatatypeIds desconhecidos" in w for w in warns)
