"""Justificativa de flag/tag é OPCIONAL (v1.0035, feedback do cliente).

`_validate_flag_applicable` deixou de exigir justificativa mesmo quando a flag
tem `requires_justification=True`. Só a flag INATIVA bloqueia.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from nuclea_modeler.backend.flags.models import FlagOut
from nuclea_modeler.backend.flags.router import _validate_flag_applicable


def _flag(**kw) -> FlagOut:
    base = dict(
        flag_id="f1", flag_key="lgpd_pessoais", category="LGPD",
        display_name="Dados Pessoais", requires_justification=True, is_active=True,
    )
    base.update(kw)
    return FlagOut(**base)


def test_requires_justification_flag_applies_without_justification():
    # Antes levantava HTTPException(400); agora deve passar sem justificativa.
    _validate_flag_applicable(_flag(requires_justification=True), None)
    _validate_flag_applicable(_flag(requires_justification=True), "")


def test_inactive_flag_still_blocks():
    with pytest.raises(HTTPException):
        _validate_flag_applicable(_flag(is_active=False), "qualquer")
