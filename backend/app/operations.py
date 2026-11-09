"""Validações das operações já existentes no contrato."""
from datetime import date
import re
from app.inventory_errors import invalid_field


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise invalid_field(field, "Campo obrigatório.")
    return value.strip()


def email(value):
    value = text(value, "email").casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+", value):
        raise invalid_field("email", "Informe um e-mail válido.")
    return value


def fields(payload, allowed, required=()):
    for key in required:
        if key not in payload:
            raise invalid_field(key, "Campo obrigatório.")
    for key in payload:
        if key not in allowed:
            raise invalid_field(key, "Campo não permitido.")


def survey(payload):
    allowed = {"titulo", "tipo", "periodo_inicio", "periodo_fim", "estabelecimentos"}
    fields(payload, allowed, allowed)
    result = dict(payload)
    result["titulo"] = text(result["titulo"], "titulo")
    if result["tipo"] not in ("CONSOLIDADO", "EXPECTATIVA"):
        raise invalid_field("tipo", "Selecione Consolidado ou Expectativa.")
    for field in ("periodo_inicio", "periodo_fim"):
        try:
            date.fromisoformat(result[field])
        except (ValueError, TypeError):
            raise invalid_field(field, "Informe uma data válida.") from None
    if result["periodo_inicio"] > result["periodo_fim"]:
        raise invalid_field("periodo_fim", "A data final deve ser posterior ou igual à inicial.")
    ids = result["estabelecimentos"]
    if not isinstance(ids, list) or not ids or any(not isinstance(entry, str) for entry in ids):
        raise invalid_field("estabelecimentos", "Selecione pelo menos uma hospedagem.")
    result["estabelecimentos"] = list(dict.fromkeys(ids))
    return result
