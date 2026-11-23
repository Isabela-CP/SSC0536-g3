from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

CadasturStatus = Literal["REGULAR", "PROXIMO_VENCIMENTO", "EM_ALERTA", "VENCIDO", "SEM_VALIDADE"]

HOSPITALITY_CATEGORIES = {
    "MEIOS DE HOSPEDAGEM", "HOTEL", "POUSADA", "RESORT",
    "HOTEL FAZENDA", "HOSTEL", "FLAT", "ACAMPAMENTO TURÍSTICO",
}


def cadastur_for(item, today=None) -> CadasturStatus:
    expiration = item.get("vencimento_cadastur")
    if not item.get("possui_cadastur") or not expiration:
        return "SEM_VALIDADE"
    today = today or datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    days = (date.fromisoformat(expiration) - today).days
    if days < 0:
        return "VENCIDO"
    if days <= 30:
        return "EM_ALERTA"
    if days <= 90:
        return "PROXIMO_VENCIMENTO"
    return "REGULAR"
