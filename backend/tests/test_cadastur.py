from datetime import date, timedelta

import pytest

from app.cadastur import cadastur_for


@pytest.mark.parametrize(("days", "expected"), [
    (-1, "VENCIDO"), (0, "EM_ALERTA"), (30, "EM_ALERTA"),
    (31, "PROXIMO_VENCIMENTO"), (90, "PROXIMO_VENCIMENTO"), (91, "REGULAR"),
    (None, "SEM_VALIDADE"),
])
def test_cadastur_classifies_expiration_boundaries(days, expected):
    today = date(2026, 11, 21)
    expires = (today + timedelta(days=days)).isoformat() if days is not None else None
    assert cadastur_for({"possui_cadastur": True, "vencimento_cadastur": expires}, today) == expected
