"""Erros de domínio, sem dependência do transporte HTTP."""


class InventoryError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: list[dict] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error = {"code": code, "message": message}
        if details:
            self.error["details"] = details


def invalid_field(field: str, message: str) -> InventoryError:
    return InventoryError(422, "VALIDATION_ERROR", "Verifique os campos informados.",
                          [{"field": field, "issue": message}])
