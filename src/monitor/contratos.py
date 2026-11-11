"""Validación de los contratos v1 de evento, captura, ventana y alerta (issue #3), y de la alerta
de fuente del extra #33."""

from __future__ import annotations

import json
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator

from .config import RAIZ

DIR_CONTRATOS = RAIZ / "config" / "p6" / "contratos"
TIPOS = ("evento", "captura", "ventana", "alerta", "alerta_fuente", "alerta_tecnica")


class ErrorContrato(ValueError):
    """Un registro no cumple su esquema; el mensaje dice el campo."""


@cache
def _validador(tipo: str) -> Draft202012Validator:
    if tipo not in TIPOS:
        raise ValueError(f"tipo de contrato desconocido: {tipo}")
    esquema = json.loads((DIR_CONTRATOS / f"{tipo}.v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(esquema)
    return Draft202012Validator(esquema)


def errores(tipo: str, registro: Any) -> list[str]:
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '(raíz)'}: {e.message}"
        for e in _validador(tipo).iter_errors(registro)
    ]


def validar(tipo: str, registro: Any) -> None:
    lista = errores(tipo, registro)
    if lista:
        raise ErrorContrato(f"{tipo} inválido: " + "; ".join(lista[:5]))
