"""Erros HTTP do inventário no formato ErrorResponse do contrato."""
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.inventory_errors import InventoryError


class InventoryRoute(APIRoute):
    validation_status = 400

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def contract_handler(request):
            try:
                return await handler(request)
            except InventoryError as exc:
                return JSONResponse(status_code=exc.status_code, content={"error": exc.error})
            except RequestValidationError as exc:
                errors = exc.errors()
                malformed = any(error["type"] == "json_invalid" or error["loc"][0] == "path" for error in errors)
                status = 400 if malformed else self.validation_status
                return JSONResponse(status_code=status, content={"error": {
                    "code": "BAD_REQUEST" if status == 400 else "VALIDATION_ERROR",
                    "message": "A requisição não pôde ser interpretada." if status == 400 else "Verifique os campos informados.",
                    "details": [{"field": error.get("ctx", {}).get("field") or ".".join(map(str, error["loc"][1:])) or "body",
                                 "issue": error.get("ctx", {}).get("issue") or error["msg"]} for error in errors],
                }})
            except HTTPException as exc:
                codes = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND"}
                messages = {
                    401: "É necessário autenticar-se.",
                    403: "Seu perfil não pode executar esta operação.",
                    404: "Estabelecimento ou documento não encontrado.",
                }
                if exc.status_code not in codes:
                    raise
                return JSONResponse(status_code=exc.status_code, headers=exc.headers,
                                    content={"error": {"code": codes[exc.status_code],
                                                       "message": messages[exc.status_code]}})

        return contract_handler


class InventoryWriteRoute(InventoryRoute):
    validation_status = 422
