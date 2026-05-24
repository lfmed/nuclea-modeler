"""Service helpers for the Corporate Data Dictionary."""
from __future__ import annotations

from .models import ConceptualType


# Heuristic type-compatibility map: conceptual type -> list of substrings that
# might appear in a SGBD native data type (lower-cased, partial match).
_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "IDENTIFIER": ("varchar", "char", "string", "uuid", "int", "bigint", "smallint", "uniqueidentifier"),
    "MONETARY": ("decimal", "numeric", "money", "double", "float", "real"),
    "DATE": ("date", "timestamp", "datetime", "time"),
    "BOOLEAN": ("bit", "bool", "tinyint(1)", "tinyint"),
    "TEXT": ("varchar", "char", "text", "string", "clob", "ntext"),
    "NUMERIC": ("int", "bigint", "smallint", "decimal", "numeric", "double", "float", "real", "tinyint"),
    "CATEGORICAL": ("varchar", "char", "string", "enum", "text"),
    "OTHER": (),
}


def check_type_compat(
    conceptual_type: ConceptualType | str | None,
    native_data_type: str | None,
) -> bool:
    """Return True if `native_data_type` looks compatible with `conceptual_type`.

    Heuristic only — looks for any keyword overlap. Returns True when we cannot
    decide (no conceptual type or no native data type) to avoid false alarms.
    OTHER is always considered compatible.
    """
    if not conceptual_type or not native_data_type:
        return True
    ct = str(conceptual_type).upper()
    if ct == "OTHER":
        return True
    keywords = _TYPE_KEYWORDS.get(ct, ())
    if not keywords:
        return True
    nlower = native_data_type.lower()
    return any(kw in nlower for kw in keywords)
