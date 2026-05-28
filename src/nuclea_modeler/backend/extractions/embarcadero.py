"""Parser Embarcadero ER/Studio .erx XML → ExtractionSnapshot.

The .erx format varies across ER/Studio versions and exports. This parser is
defensive — it accepts multiple casing/aliasing variants for tag and attribute
names and skips malformed nodes rather than failing the entire parse.

Public API:
    parse_erx(xml_text, system_id) -> (snapshot, warnings)
"""
from __future__ import annotations

# defusedxml previne ataques XXE / billion laughs / DTD recursion comuns em
# arquivos .erx vindos de fontes não-confiáveis (upload do usuário).
# A API é drop-in compatível com xml.etree.ElementTree.
import xml.etree.ElementTree as ET  # noqa: F401 — usado para type hints `ET.Element`

from defusedxml import ElementTree as _DefusedET
from datetime import datetime
from typing import Iterable

from .models import ExtractedAttribute, ExtractedEntity, ExtractionSnapshot


# ─── Tag / attribute aliases ────────────────────────────────────────────────

_ENTITY_TAGS = ("entity", "table")
_ENTITIES_CONTAINER_TAGS = ("entities", "tables")
_ATTRIBUTE_TAGS = ("attribute", "column", "field")
_ATTRIBUTES_CONTAINER_TAGS = ("attributes", "columns", "fields")
_COMMENT_TAGS = ("comment", "description", "definition", "note", "notes")
_RELATIONSHIP_TAGS = ("relationship", "foreignkey", "foreign_key", "link")
_RELATIONSHIPS_CONTAINER_TAGS = ("relationships", "foreignkeys", "links")

_ENTITY_NAME_ATTRS = ("name", "entityname", "table", "tablename", "physicalname")
_ENTITY_SCHEMA_ATTRS = ("schema", "schemaname", "owner", "ownername")
_ATTR_NAME_ATTRS = ("name", "columnname", "fieldname", "physicalname")
_ATTR_TYPE_ATTRS = ("datatype", "type", "logicaldatatype", "physicaldatatype", "columndatatype")
_ATTR_NULLABLE_ATTRS = ("nullable", "isnullable", "allownulls", "nulloption")
_ATTR_PK_ATTRS = ("primarykey", "ispk", "ispkmember", "key", "iskey", "ispartofpk")
_ATTR_ORDER_ATTRS = ("order", "ordinalposition", "sequence", "ordinal", "position")
_ATTR_DEFAULT_ATTRS = ("default", "defaultvalue")
_ATTR_COMMENT_ATTRS = ("comment", "description", "definition", "note")


# ─── Helpers ────────────────────────────────────────────────────────────────


def _localname(tag: str) -> str:
    """Strip namespace prefix from an XML tag and lowercase it."""
    if not tag:
        return ""
    if "}" in tag:
        tag = tag.split("}", 1)[1]
    return tag.lower()


def _find_children_ci(parent: ET.Element, *tag_names: str) -> Iterable[ET.Element]:
    """Yield direct children whose localname matches any of the given names (case-insensitive)."""
    wanted = {t.lower() for t in tag_names}
    for child in list(parent):
        if _localname(child.tag) in wanted:
            yield child


def _iter_descendants_ci(parent: ET.Element, *tag_names: str) -> Iterable[ET.Element]:
    """Yield all descendants whose localname matches any of the given names."""
    wanted = {t.lower() for t in tag_names}
    for elem in parent.iter():
        if elem is parent:
            continue
        if _localname(elem.tag) in wanted:
            yield elem


def _get_attr_ci(elem: ET.Element, *names: str) -> str | None:
    """Return the first matching attribute value (case-insensitive). Returns None if none match."""
    if elem.attrib:
        lower_map = {k.lower().rsplit("}", 1)[-1]: v for k, v in elem.attrib.items()}
        for n in names:
            v = lower_map.get(n.lower())
            if v is not None and v != "":
                return v
    return None


def _get_child_text_ci(elem: ET.Element, *tag_names: str) -> str | None:
    """Return text of the first matching direct or nested child element."""
    for child in elem.iter():
        if child is elem:
            continue
        if _localname(child.tag) in {t.lower() for t in tag_names}:
            txt = (child.text or "").strip()
            if txt:
                return txt
    return None


def _parse_bool(value: str | None) -> bool | None:
    """Interpret common boolean encodings used by ER/Studio. None if not recognizable."""
    if value is None:
        return None
    v = value.strip().lower()
    if v in ("true", "1", "y", "yes", "t", "nullable"):
        return True
    if v in ("false", "0", "n", "no", "f", "notnull", "nonullsallowed", "not null"):
        return False
    return None


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


# ─── Parser ─────────────────────────────────────────────────────────────────


def _parse_attribute(
    elem: ET.Element, fallback_order: int, warnings: list[str]
) -> ExtractedAttribute | None:
    """Parse a single column/attribute element into ExtractedAttribute. Returns None if unusable."""
    try:
        name = _get_attr_ci(elem, *_ATTR_NAME_ATTRS) or _get_child_text_ci(elem, "name", "columnname")
        if not name:
            warnings.append("attribute skipped: missing name")
            return None
        native_type = _get_attr_ci(elem, *_ATTR_TYPE_ATTRS) or _get_child_text_ci(
            elem, "datatype", "type", "logicaldatatype"
        )
        nullable = _parse_bool(_get_attr_ci(elem, *_ATTR_NULLABLE_ATTRS))
        # For nullable attribute "Nullable=NULL OPTION" style: also check text
        if nullable is None:
            nullable = _parse_bool(_get_child_text_ci(elem, "nullable", "isnullable"))
        is_pk = _parse_bool(_get_attr_ci(elem, *_ATTR_PK_ATTRS)) or False
        if not is_pk:
            # Some exports use a nested <PrimaryKey>true</PrimaryKey>
            is_pk = bool(_parse_bool(_get_child_text_ci(elem, "primarykey", "ispk", "key")))
        order = _parse_int(_get_attr_ci(elem, *_ATTR_ORDER_ATTRS)) or fallback_order
        default_value = _get_attr_ci(elem, *_ATTR_DEFAULT_ATTRS) or _get_child_text_ci(
            elem, "default", "defaultvalue"
        )
        comment = _get_attr_ci(elem, *_ATTR_COMMENT_ATTRS) or _get_child_text_ci(
            elem, *_COMMENT_TAGS
        )
        return ExtractedAttribute(
            technical_name=str(name).strip(),
            ordinal_position=order,
            native_data_type=str(native_type).strip() if native_type else None,
            is_nullable=nullable,
            default_value=default_value,
            is_primary_key=bool(is_pk),
            native_comment=comment,
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"attribute skipped due to error: {exc}")
        return None


def _parse_entity(elem: ET.Element, warnings: list[str]) -> ExtractedEntity | None:
    """Parse a single Entity/Table element into ExtractedEntity. Returns None if unusable."""
    try:
        name = _get_attr_ci(elem, *_ENTITY_NAME_ATTRS) or _get_child_text_ci(
            elem, "name", "entityname", "tablename", "physicalname"
        )
        if not name:
            warnings.append("entity skipped: missing name")
            return None
        schema = (
            _get_attr_ci(elem, *_ENTITY_SCHEMA_ATTRS)
            or _get_child_text_ci(elem, "schema", "schemaname", "owner")
            or "dbo"
        )
        comment = _get_attr_ci(elem, *_ATTR_COMMENT_ATTRS) or _get_child_text_ci(
            elem, *_COMMENT_TAGS
        )

        # Locate the attribute container (direct child) and fall back to nested search.
        attr_elements: list[ET.Element] = []
        for container in _find_children_ci(elem, *_ATTRIBUTES_CONTAINER_TAGS):
            for attr_el in _find_children_ci(container, *_ATTRIBUTE_TAGS):
                attr_elements.append(attr_el)
        # Also accept direct <Attribute>/<Column> children at the entity level.
        for attr_el in _find_children_ci(elem, *_ATTRIBUTE_TAGS):
            attr_elements.append(attr_el)
        # Last resort: scan descendants if nothing found yet.
        if not attr_elements:
            attr_elements = list(_iter_descendants_ci(elem, *_ATTRIBUTE_TAGS))

        attributes: list[ExtractedAttribute] = []
        for idx, attr_el in enumerate(attr_elements, start=1):
            parsed = _parse_attribute(attr_el, fallback_order=idx, warnings=warnings)
            if parsed is not None:
                attributes.append(parsed)

        return ExtractedEntity(
            schema_name=str(schema).strip(),
            technical_name=str(name).strip(),
            entity_type="TABLE",
            native_comment=comment,
            attributes=attributes,
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"entity skipped due to error: {exc}")
        return None


def _collect_relationship_warnings(root: ET.Element, warnings: list[str]) -> int:
    """Count relationships found (purely informational — surfaced in warnings)."""
    count = 0
    for rel in _iter_descendants_ci(root, *_RELATIONSHIP_TAGS):
        try:
            name = _get_attr_ci(rel, "name", "relationshipname") or "(unnamed)"
            src = _get_attr_ci(rel, "sourceentity", "parententity", "from", "parenttable")
            tgt = _get_attr_ci(rel, "targetentity", "childentity", "to", "childtable")
            if src and tgt:
                count += 1
                warnings.append(f"relationship detected: {name} ({src} → {tgt})")
        except Exception:  # noqa: BLE001
            continue
    return count


def parse_erx(xml_text: str, system_id: str) -> tuple[ExtractionSnapshot, list[str]]:
    """Parse an Embarcadero ER/Studio .erx XML string into an ExtractionSnapshot.

    Args:
        xml_text: Raw XML content (any encoding already decoded to text).
        system_id: System id used for the resulting snapshot.

    Returns:
        Tuple of (snapshot, parse_warnings). The snapshot may contain zero
        entities if nothing was recognized; check len(snapshot.entities).
    """
    warnings: list[str] = []
    if xml_text is None:
        raise ValueError("XML content is empty")

    # Strip BOM and leading whitespace.
    cleaned = xml_text.lstrip("﻿").lstrip()
    if not cleaned:
        raise ValueError("XML content is empty")

    try:
        # defusedxml.ElementTree.fromstring desabilita XXE/billion-laughs/DTD
        # recursion. Retorna o mesmo tipo ET.Element do stdlib.
        root = _DefusedET.fromstring(cleaned)
    except ET.ParseError as exc:
        raise ValueError(f"XML inválido: {exc}") from exc

    # Locate all Entity/Table elements. Strategy:
    #   1. Look for containers (<Entities>, <Tables>) anywhere under root and pull their entity children.
    #   2. If none found, scan the whole tree for any element whose localname matches an entity tag.
    entity_elements: list[ET.Element] = []
    seen_ids: set[int] = set()

    def _add(el: ET.Element) -> None:
        if id(el) not in seen_ids:
            seen_ids.add(id(el))
            entity_elements.append(el)

    # Container-based discovery (preferred).
    for container in [root, *list(root.iter())]:
        if _localname(container.tag) in {t.lower() for t in _ENTITIES_CONTAINER_TAGS}:
            for child in _find_children_ci(container, *_ENTITY_TAGS):
                _add(child)

    # Fallback: any entity-tagged descendant of root, but not nested inside another entity.
    if not entity_elements:
        for el in _iter_descendants_ci(root, *_ENTITY_TAGS):
            _add(el)

    entities: list[ExtractedEntity] = []
    for el in entity_elements:
        parsed = _parse_entity(el, warnings)
        if parsed is not None:
            entities.append(parsed)

    # Relationships are best-effort; only logged as warnings/info today.
    rel_count = _collect_relationship_warnings(root, warnings)
    if rel_count:
        warnings.insert(0, f"{rel_count} relacionamento(s) detectado(s) — não persistidos nesta versão")

    snapshot = ExtractionSnapshot(
        source_kind="EMBARCADERO",
        system_id=system_id,
        captured_at=datetime.utcnow(),
        schemas=sorted({e.schema_name for e in entities}),
        entities=entities,
    )
    return snapshot, warnings
