"""Security tests para o parser Embarcadero — XXE / billion laughs.

Garante que o parser usa defusedxml e rejeita payloads maliciosos comuns.
"""
from __future__ import annotations

import pytest

# Skip todo o módulo se defusedxml não estiver instalado (ambiente local sem deps)
defusedxml = pytest.importorskip("defusedxml")

from nuclea_modeler.backend.extractions.embarcadero import parse_erx


# ─── XXE (XML External Entity) ──────────────────────────────────────────────


def test_rejects_xxe_external_entity():
    """Payload XXE clássico: tenta ler /etc/passwd via entity externa.
    defusedxml deve recusar — não devemos ler arquivo do disco."""
    xxe = """<?xml version="1.0"?>
    <!DOCTYPE foo [
      <!ENTITY xxe SYSTEM "file:///etc/passwd">
    ]>
    <Model><Entities><Entity name="&xxe;"/></Entities></Model>
    """
    with pytest.raises((ValueError, defusedxml.EntitiesForbidden, defusedxml.DTDForbidden)):
        parse_erx(xxe, system_id="sys-test")


def test_rejects_billion_laughs():
    """Payload DoS: expansão exponencial de entities ('billion laughs').
    Cada `&lol9;` expande para milhões de bytes. defusedxml deve recusar."""
    bomb = """<?xml version="1.0"?>
    <!DOCTYPE lolz [
      <!ENTITY lol "lol">
      <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
      <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
    ]>
    <Model><Entities><Entity name="&lol3;"/></Entities></Model>
    """
    with pytest.raises((ValueError, defusedxml.EntitiesForbidden, defusedxml.DTDForbidden)):
        parse_erx(bomb, system_id="sys-test")


def test_rejects_dtd():
    """DTD inline é vetor para múltiplos ataques. defusedxml proíbe por default."""
    dtd = """<?xml version="1.0"?>
    <!DOCTYPE Model [
      <!ELEMENT Model (Entities)>
      <!ELEMENT Entities (Entity*)>
      <!ELEMENT Entity EMPTY>
    ]>
    <Model><Entities><Entity name="x"/></Entities></Model>
    """
    with pytest.raises((ValueError, defusedxml.DTDForbidden)):
        parse_erx(dtd, system_id="sys-test")


# ─── Sanity: parser legítimo ainda funciona ─────────────────────────────────


def test_parses_legitimate_erx_payload():
    """Payload mínimo válido — deve parsear sem erro."""
    ok = """<?xml version="1.0"?>
    <Model>
      <Entities>
        <Entity name="cliente" schema="public">
          <Attributes>
            <Attribute name="id" datatype="bigint" primarykey="true"/>
            <Attribute name="nome" datatype="varchar(100)" nullable="false"/>
          </Attributes>
        </Entity>
      </Entities>
    </Model>
    """
    snapshot, warnings = parse_erx(ok, system_id="sys-test")
    assert len(snapshot.entities) == 1
    assert snapshot.entities[0].technical_name == "cliente"
    # 2 attributes parsed
    assert len(snapshot.entities[0].attributes) == 2
