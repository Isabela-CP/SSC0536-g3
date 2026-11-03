"""Erros HTTP das consultas no formato ErrorResponse do contrato."""
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute


class InventoryRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def contract_handler(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return JSONResponse(status_code=400, content={"error": {
                    "code": "BAD_REQUEST",
                    "message": "A requisição não pôde ser interpretada.",
                    "details": [{"field": ".".join(map(str, error["loc"][1:])),
                                 "issue": error["msg"]} for error in exc.errors()],
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
