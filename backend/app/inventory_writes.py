"""Rotas de escrita: validação HTTP e delegação para serviços de inventário."""
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from starlette.background import BackgroundTask

from app.document_storage import DocumentStorage, document_storage
from app.inventory_http import InventoryWriteRoute
from app.inventory_errors import InventoryError, invalid_field
from app.inventory_models import (
    Document, DocumentCreate, DocumentUpdate, Establishment, EstablishmentCreate,
    EstablishmentUpdate, Inactivation,
)
from app.inventory_repository import WritableInventoryRepository
from app.inventory_service import InventoryService, authorize, check_fields


def create_write_router(repository_dependency, user_dependency, audit_callback) -> APIRouter:
    router = APIRouter(route_class=InventoryWriteRoute)

    def service(repository: WritableInventoryRepository = Depends(repository_dependency),
                storage: DocumentStorage = Depends(document_storage)) -> InventoryService:
        return InventoryService(repository, audit_callback, storage)

    def admin(user: dict = Depends(user_dependency)) -> dict:
        authorize(user, admin_only=True)
        return user

    def writer(id_estabelecimento: UUID, user: dict = Depends(user_dependency)) -> dict:
        authorize(user, str(id_estabelecimento))
        return user

    async def editor(request: Request, user: dict = Depends(writer)) -> dict:
        # Rejeita campos protegidos antes de validar seus valores.
        try:
            payload = await request.json()
        except ValueError:
            raise InventoryError(400, "BAD_REQUEST", "A requisição não pôde ser interpretada.") from None
        if isinstance(payload, dict):
            check_fields(user, payload)
        return user

    async def upload_actor(request: Request, user: dict = Depends(writer)) -> dict:
        form = await request.form()
        allowed = {"arquivo"} if request.method == "PUT" else {
            "arquivo", "tipo_documento", "numero", "data_emissao", "data_vencimento",
        }
        unknown = set(form) - allowed
        if unknown:
            raise invalid_field(sorted(unknown)[0], "Campo não permitido.")
        for key in form:
            if len(form.getlist(key)) > 1:
                raise invalid_field(key, "Campo repetido.")
        return user

    @router.post("/estabelecimentos", status_code=201, response_model=Establishment,
                 response_model_exclude_unset=True, tags=["Estabelecimentos"])
    def create_establishment(payload: EstablishmentCreate, actor: dict = Depends(admin),
                             service: InventoryService = Depends(service)):
        return service.create(actor, payload.model_dump(mode="json", exclude_unset=True))

    @router.patch("/estabelecimentos/{id_estabelecimento}", response_model=Establishment,
                  response_model_exclude_unset=True, tags=["Estabelecimentos"])
    def update_establishment(id_estabelecimento: UUID, payload: EstablishmentUpdate,
                             actor: dict = Depends(editor), service: InventoryService = Depends(service)):
        return service.update(actor, str(id_estabelecimento), payload.model_dump(mode="json", exclude_unset=True))

    @router.post("/estabelecimentos/{id_estabelecimento}/inativacao", response_model=Establishment,
                 response_model_exclude_unset=True, tags=["Estabelecimentos"])
    def inactivate(id_estabelecimento: UUID, payload: Inactivation, actor: dict = Depends(admin),
                   service: InventoryService = Depends(service)):
        return service.change_status(actor, str(id_estabelecimento), False, payload.motivo_inativacao)

    @router.post("/estabelecimentos/{id_estabelecimento}/reativacao", response_model=Establishment,
                 response_model_exclude_unset=True, tags=["Estabelecimentos"])
    def reactivate(id_estabelecimento: UUID, actor: dict = Depends(admin), service: InventoryService = Depends(service)):
        return service.change_status(actor, str(id_estabelecimento), True)

    @router.post("/estabelecimentos/{id_estabelecimento}/documentos", status_code=201,
                 response_model=Document, response_model_exclude_unset=True, tags=["Documentos"])
    def upload_document(
        id_estabelecimento: UUID,
        tipo_documento: Annotated[str, Form()],
        data_vencimento: Annotated[str, Form()],
        arquivo: Annotated[UploadFile, File()],
        numero: Annotated[str | None, Form()] = None,
        data_emissao: Annotated[str | None, Form()] = None,
        actor: dict = Depends(upload_actor),
        service: InventoryService = Depends(service),
    ):
        try:
            payload = DocumentCreate.model_validate({
                "tipo_documento": tipo_documento, "data_vencimento": data_vencimento,
                "numero": numero, "data_emissao": data_emissao,
            })
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc
        return service.upload(actor, str(id_estabelecimento), payload.model_dump(mode="json", exclude_unset=True),
                              arquivo.file, arquivo.filename, arquivo.content_type)

    @router.patch("/estabelecimentos/{id_estabelecimento}/documentos/{id_documento}", response_model=Document,
                  response_model_exclude_unset=True, tags=["Documentos"])
    def update_document(id_estabelecimento: UUID, id_documento: int, payload: DocumentUpdate,
                        actor: dict = Depends(writer), service: InventoryService = Depends(service)):
        return service.update_document(actor, str(id_estabelecimento), id_documento,
                                       payload.model_dump(mode="json", exclude_unset=True))

    @router.put("/estabelecimentos/{id_estabelecimento}/documentos/{id_documento}/arquivo", response_model=Document,
                response_model_exclude_unset=True, tags=["Documentos"])
    def replace_file(id_estabelecimento: UUID, id_documento: int, arquivo: Annotated[UploadFile, File()],
                     actor: dict = Depends(upload_actor), service: InventoryService = Depends(service)):
        return service.replace_file(actor, str(id_estabelecimento), id_documento,
                                    arquivo.file, arquivo.filename, arquivo.content_type)

    @router.get("/estabelecimentos/{id_estabelecimento}/documentos/{id_documento}/arquivo", tags=["Documentos"])
    def download_file(id_estabelecimento: UUID, id_documento: int, actor: dict = Depends(user_dependency),
                      service: InventoryService = Depends(service)):
        stream, metadata = service.download(actor, str(id_estabelecimento), id_documento)

        def chunks():
            with stream:
                while chunk := stream.read(64 * 1024):
                    yield chunk

        return StreamingResponse(chunks(), media_type="application/octet-stream",
                                 headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(metadata["nome_arquivo"], safe=""),
                                          "Content-Length": str(metadata["tamanho_bytes"]),
                                          "X-Content-Type-Options": "nosniff"},
                                 background=BackgroundTask(stream.close))

    return router
