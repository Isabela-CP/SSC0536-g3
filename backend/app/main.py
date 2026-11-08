from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.inventory import InventoryQuery, InventoryRepository, JsonInventoryRepository, query_establishments
from app.inventory_http import InventoryRoute
from app.inventory_repository import MemoryInventoryRepository
from app.inventory_writes import create_write_router
from app.inventory_errors import InventoryError, invalid_field
from app import operations
from app.read_views import dashboard_summary, audit_records
from app.reporting import build_report


ROOT_DIR = Path(__file__).resolve().parents[2]
SEED_FILE = ROOT_DIR / "contratos_api_oto" / "mocks" / "seed-data.json"
OPENAPI_FILE = ROOT_DIR / "contratos_api_oto" / "openapi.json"

app = FastAPI(
    title="Inventário OTO",
    version="0.1.0",
    description="Base FastAPI que entrega respostas mockadas do contrato OTO.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def custom_openapi() -> dict[str, Any]:
    """Expõe o contrato completo de contratos_api_oto/openapi.json no /docs."""
    with OPENAPI_FILE.open(encoding="utf-8") as file:
        spec = json.load(file)
    spec["servers"] = [{"url": "/", "description": "Servidor local"}]
    return spec


app.openapi = custom_openapi  # type: ignore[method-assign]


DEMO_USERS = {
    "marina.admin@example.test": {
        "id_usuario": 1, "nome": "Marina Administradora", "email": "marina.admin@example.test",
        "perfil": "ADMINISTRADOR", "senha": "admin-demo", "ativo": True,
    },
    "rafael.consulta@example.test": {
        "id_usuario": 2, "nome": "Rafael Consulta", "email": "rafael.consulta@example.test",
        "perfil": "GESTOR", "senha": "gestor-demo", "ativo": True,
    },
    "camila.editora@example.test": {
        "id_usuario": 3, "nome": "Camila Editora", "email": "camila.editora@example.test",
        "perfil": "EDITOR", "senha": "editor-demo", "ativo": True,
    },
}
TOKENS = {"admin-token": "marina.admin@example.test", "gestor-token": "rafael.consulta@example.test", "editor-token": "camila.editora@example.test"}
INVITES: list[dict[str, Any]] = []
SURVEYS: list[dict[str, Any]] = []
OCCUPANCY_RESPONSES: list[dict[str, Any]] = []
AUDIT_LOG: list[dict[str, Any]] = []
REPORTS: list[dict[str, Any]] = []
REPORT_FILES: dict[str, tuple[bytes, str]] = {}


def error_response(status_code: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error})


@app.exception_handler(InventoryError)
async def operation_error(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.error})


def current_user(authorization: str | None = Header(default=None)) -> dict:
    scheme, _, token = (authorization or "").partition(" ")
    email = TOKENS.get(token) if scheme.casefold() == "bearer" else None
    user = DEMO_USERS.get(email) if email else None
    if not user or not user.get("ativo"):
        raise HTTPException(status_code=401, detail="UNAUTHORIZED",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def audit(actor: dict, action: str, entity: str, entity_id: str, before: Any = None, after: Any = None) -> None:
    AUDIT_LOG.append({
        "id": str(uuid4()), "criado_em": datetime.now(timezone.utc).isoformat(),
        "id_usuario": actor["id_usuario"], "usuario": actor["email"], "acao": action,
        "entidade": entity, "id_entidade": entity_id, "antes": deepcopy(before), "depois": deepcopy(after),
    })


def ensure_role(user: dict, *roles: str) -> None:
    if user["perfil"] not in roles:
        raise HTTPException(status_code=403, detail="FORBIDDEN")


def seed_data() -> dict:
    """Lê a fonte única de dados de desenvolvimento a cada requisição."""
    with SEED_FILE.open(encoding="utf-8") as file:
        return json.load(file)


# Contas HOTEL de demonstração usam o vínculo da fonte de dados do servidor.
for account in seed_data()["contas_empresario"]:
    DEMO_USERS[account["email"]] = {
        "id_usuario": account["id_conta"], "nome": "Responsável pela hospedagem",
        "email": account["email"], "perfil": "HOTEL", "senha": "hotel-demo",
        "ativo": account["ativo"], "id_estabelecimento": account["id_estabelecimento"],
    }
    TOKENS[f"hotel-{account['id_conta']}-token"] = account["email"]


@app.get("/health", tags=["Sistema"])
def health() -> dict[str, str]:
    return {"status": "ok"}


inventory_router = APIRouter(route_class=InventoryRoute)


@lru_cache
def inventory_repository() -> MemoryInventoryRepository:
    return MemoryInventoryRepository(JsonInventoryRepository(SEED_FILE))


def inventory_user(user: dict = Depends(current_user)) -> dict:
    ensure_role(user, "ADMINISTRADOR", "GESTOR", "EDITOR", "HOTEL")
    if user["perfil"] == "HOTEL" and not user.get("id_estabelecimento"):
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return user


def authorized_establishment(
    id_estabelecimento: UUID,
    user: dict = Depends(inventory_user),
    repository: InventoryRepository = Depends(inventory_repository),
) -> dict:
    establishment_id = str(id_estabelecimento)
    if user["perfil"] == "HOTEL" and user["id_estabelecimento"] != establishment_id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    establishment = repository.establishment(establishment_id)
    if establishment is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return establishment


@inventory_router.get("/categorias-estabelecimento", tags=["Categorias"])
def list_categories(
    user: dict = Depends(inventory_user),
    repository: InventoryRepository = Depends(inventory_repository),
) -> dict:
    return {"data": repository.categories()}


@inventory_router.get("/estabelecimentos", tags=["Estabelecimentos"])
def list_establishments(
    busca: Annotated[str | None, Query(max_length=120)] = None,
    status: Literal["ATIVO", "INATIVO"] | None = None,
    id_categoria: Annotated[int | None, Query(ge=1)] = None,
    cadastur_status: Literal["OBRIGATORIO", "OPCIONAL", "NAO_CONSTA"] | None = None,
    aceita_pesquisas: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ordenar_por: Literal["nome_fantasia", "criado_em", "atualizado_em"] = "nome_fantasia",
    ordem: Literal["asc", "desc"] = "asc",
    user: dict = Depends(inventory_user),
    repository: InventoryRepository = Depends(inventory_repository),
) -> dict:
    query = InventoryQuery(
        busca=busca, status=status, id_categoria=id_categoria,
        cadastur_status=cadastur_status, aceita_pesquisas=aceita_pesquisas,
        page=page, page_size=page_size, ordenar_por=ordenar_por, ordem=ordem,
    )
    scope = user["id_estabelecimento"] if user["perfil"] == "HOTEL" else None
    return query_establishments(repository, query, scope)


@inventory_router.get("/estabelecimentos/{id_estabelecimento}", tags=["Estabelecimentos"])
def get_establishment(establishment: dict = Depends(authorized_establishment)) -> dict:
    return establishment


@inventory_router.get("/estabelecimentos/{id_estabelecimento}/documentos", tags=["Documentos"])
def list_documents(establishment: dict = Depends(authorized_establishment)) -> dict:
    return {"data": establishment.get("documentos", [])}


app.include_router(inventory_router)
app.include_router(create_write_router(inventory_repository, inventory_user, audit))


@app.post("/auth/login", tags=["Autenticação"])
def login(payload: dict = Body(...)) -> Any:
    email = payload.get("email")
    user = DEMO_USERS.get(email.strip().casefold()) if isinstance(email, str) else None
    if not user or not isinstance(payload.get("senha"), str) or not payload["senha"] or user["senha"] != payload["senha"] or not user["ativo"]:
        return error_response(401, "INVALID_CREDENTIALS", "E-mail ou senha inválidos.")
    token = next((token for token, email in TOKENS.items() if email == user["email"]), None)
    if token is None:
        token = str(uuid4())
        TOKENS[token] = user["email"]
    return {"access_token": token, "token_type": "Bearer", "expires_in": 3600, "usuario": public_user(user)}


@app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["Autenticação"])
def logout(authorization: str = Header(...), _: dict = Depends(current_user)) -> None:
    TOKENS.pop(authorization.partition(" ")[2], None)
    return None


@app.post("/auth/recuperacao-senha", status_code=status.HTTP_202_ACCEPTED, tags=["Autenticação"])
def recover_password(payload: dict = Body(...)) -> dict:
    operations.email(payload.get("email"))
    return {"message": "Se o e-mail estiver cadastrado, as instruções de recuperação serão enviadas."}


def public_user(user: dict) -> dict:
    result = {key: user[key] for key in ("id_usuario", "nome", "email", "perfil", "ativo")}
    if user["perfil"] == "HOTEL":
        result["id_estabelecimento"] = user.get("id_estabelecimento")
    return result


@app.get("/perfil", tags=["Perfil"])
def get_profile(user: dict = Depends(current_user)) -> dict:
    return public_user(user)


@app.patch("/perfil", tags=["Perfil"])
def update_profile(payload: dict = Body(...), user: dict = Depends(current_user)) -> Any:
    operations.fields(payload, {"nome", "email"})
    if not payload:
        raise invalid_field("body", "Altere pelo menos um campo.")
    changes = dict(payload)
    if "nome" in changes:
        changes["nome"] = operations.text(changes["nome"], "nome")
    if "email" in changes:
        changes["email"] = operations.email(changes["email"])
        if changes["email"] != user["email"] and changes["email"] in DEMO_USERS:
            return error_response(409, "EMAIL_ALREADY_EXISTS", "Já existe uma conta com esse e-mail.")
    before, old_email = public_user(user), user["email"]
    user.update(changes)
    if user["email"] != old_email:
        DEMO_USERS.pop(old_email)
        DEMO_USERS[user["email"]] = user
        for token, email in TOKENS.items():
            if email == old_email:
                TOKENS[token] = user["email"]
    audit(user, "PERFIL_ATUALIZADO", "USUARIO", str(user["id_usuario"]), before, public_user(user))
    return public_user(user)


@app.get("/usuarios", tags=["Usuários"])
def list_users(user: dict = Depends(current_user)) -> dict:
    ensure_role(user, "ADMINISTRADOR")
    return {"data": [public_user(item) for item in DEMO_USERS.values()]}


@app.post("/usuarios", status_code=status.HTTP_201_CREATED, tags=["Usuários"])
def create_user(payload: dict = Body(...), user: dict = Depends(current_user)) -> Any:
    ensure_role(user, "ADMINISTRADOR")
    operations.fields(payload, {"nome", "email", "perfil", "id_estabelecimento"}, {"nome", "email", "perfil"})
    email = operations.email(payload["email"])
    name = operations.text(payload["nome"], "nome")
    if email in DEMO_USERS:
        return error_response(409, "EMAIL_ALREADY_EXISTS", "Já existe uma conta com esse e-mail.")
    if payload["perfil"] not in ("ADMINISTRADOR", "GESTOR", "EDITOR", "HOTEL"):
        raise invalid_field("perfil", "Perfil inválido.")
    association = payload.get("id_estabelecimento")
    if payload["perfil"] == "HOTEL":
        if not isinstance(association, str) or inventory_repository().establishment(association) is None:
            raise invalid_field("id_estabelecimento", "Selecione uma hospedagem existente.")
    elif association is not None:
        raise invalid_field("id_estabelecimento", "Somente HOTEL recebe vínculo de hospedagem.")
    created = {"id_usuario": max(item["id_usuario"] for item in DEMO_USERS.values()) + 1,
               "nome": name, "email": email, "perfil": payload["perfil"], "senha": "", "ativo": False}
    if association:
        created["id_estabelecimento"] = association
    DEMO_USERS[email] = created
    audit(user, "USUARIO_CRIADO", "USUARIO", str(created["id_usuario"]), after=public_user(created))
    return public_user(created)


@app.post("/convites", status_code=status.HTTP_201_CREATED, tags=["Convites"])
def create_invite(payload: dict = Body(...), user: dict = Depends(current_user)) -> Any:
    ensure_role(user, "ADMINISTRADOR")
    email = operations.email(payload.get("email"))
    if email not in DEMO_USERS:
        return error_response(404, "USER_NOT_FOUND", "Usuário não encontrado para convite.")
    invite = {"id_convite": str(uuid4()), "email": email, "status": "PENDENTE", "expira_em": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(), "token": str(uuid4())}
    for previous in INVITES:
        if previous["email"] == email and previous["status"] == "PENDENTE":
            previous["status"] = "SUBSTITUIDO"
    INVITES.append(invite)
    audit(user, "CONVITE_ENVIADO", "CONVITE", invite["id_convite"], after={"email": email})
    return {key: value for key, value in invite.items() if key != "token"}


@app.post("/convites/{id_convite}/aceitacao", tags=["Convites"])
def accept_invite(id_convite: str, payload: dict = Body(...)) -> Any:
    invite = next((item for item in INVITES if item["id_convite"] == id_convite), None)
    if not invite or invite["token"] != payload.get("token") or datetime.fromisoformat(invite["expira_em"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        return error_response(404, "INVITE_NOT_FOUND", "Convite não encontrado ou expirado.")
    if invite["status"] != "PENDENTE":
        return error_response(409, "INVITE_ALREADY_USED", "Convite já utilizado.")
    invited = DEMO_USERS[invite["email"]]
    password = payload.get("senha")
    if not isinstance(password, str) or not password:
        raise invalid_field("senha", "Informe uma senha.")
    invited["senha"] = password
    invited["ativo"] = True
    invite["status"] = "ACEITO"
    audit(invited, "CONVITE_ACEITO", "USUARIO", str(invited["id_usuario"]))
    return {"message": "Acesso ativado com sucesso.", "usuario": public_user(invited)}


def validate_survey_recipients(ids):
    for establishment_id in ids:
        item = inventory_repository().establishment(establishment_id)
        if not item or item["status"] != "ATIVO" or not item["aceita_pesquisas"]:
            raise invalid_field("estabelecimentos", "Selecione hospedagens ativas que aceitam pesquisas.")


@app.get("/pesquisas-ocupacao", tags=["Pesquisas de ocupação"])
def list_surveys(user: dict = Depends(current_user)) -> dict:
    ensure_role(user, "ADMINISTRADOR", "GESTOR", "EDITOR", "HOTEL")
    if user["perfil"] == "HOTEL":
        association = user.get("id_estabelecimento")
        if not association:
            raise HTTPException(status_code=403, detail="FORBIDDEN")
        return {"data": [item for item in SURVEYS if association in item["estabelecimentos"]]}
    return {"data": SURVEYS}


@app.post("/pesquisas-ocupacao", status_code=status.HTTP_201_CREATED, tags=["Pesquisas de ocupação"])
def create_survey(payload: dict = Body(...), user: dict = Depends(current_user)) -> Any:
    ensure_role(user, "ADMINISTRADOR", "EDITOR")
    data = operations.survey(payload)
    validate_survey_recipients(data["estabelecimentos"])
    survey = {"id_pesquisa": str(uuid4()), **data, "status": "ABERTA", "criada_por": user["id_usuario"]}
    SURVEYS.append(survey)
    audit(user, "PESQUISA_CRIADA", "PESQUISA_OCUPACAO", survey["id_pesquisa"], after=survey)
    return survey


@app.patch("/pesquisas-ocupacao/{id_pesquisa}", tags=["Pesquisas de ocupação"])
def update_survey(id_pesquisa: str, payload: dict = Body(...), user: dict = Depends(current_user)) -> Any:
    ensure_role(user, "ADMINISTRADOR", "EDITOR")
    survey = next((item for item in SURVEYS if item["id_pesquisa"] == id_pesquisa), None)
    if not survey:
        return error_response(404, "SURVEY_NOT_FOUND", "Pesquisa não encontrada.")
    if survey["status"] != "ABERTA":
        return error_response(409, "SURVEY_CLOSED", "A pesquisa encerrada não pode ser alterada.")
    allowed = {"titulo", "tipo", "periodo_inicio", "periodo_fim", "estabelecimentos"}
    operations.fields(payload, allowed)
    if not payload:
        raise invalid_field("body", "Altere pelo menos um campo.")
    data = operations.survey({**{key: survey[key] for key in allowed}, **payload})
    validate_survey_recipients(data["estabelecimentos"])
    before = deepcopy(survey)
    survey.update(data)
    audit(user, "PESQUISA_ATUALIZADA", "PESQUISA_OCUPACAO", id_pesquisa, before, survey)
    return survey


@app.post("/pesquisas-ocupacao/{id_pesquisa}/encerramento", tags=["Pesquisas de ocupação"])
def close_survey(id_pesquisa: str, user: dict = Depends(current_user)) -> Any:
    ensure_role(user, "ADMINISTRADOR", "EDITOR")
    survey = next((item for item in SURVEYS if item["id_pesquisa"] == id_pesquisa), None)
    if not survey:
        return error_response(404, "SURVEY_NOT_FOUND", "Pesquisa não encontrada.")
    if survey["status"] == "ENCERRADA":
        return error_response(409, "SURVEY_ALREADY_CLOSED", "A pesquisa já está encerrada.")
    before = survey.copy()
    survey["status"] = "ENCERRADA"
    audit(user, "PESQUISA_ENCERRADA", "PESQUISA_OCUPACAO", id_pesquisa, before, survey)
    return survey


@app.get("/pesquisas-ocupacao/pendentes", tags=["Respostas de ocupação"])
def pending_surveys(user: dict = Depends(current_user)) -> dict:
    ensure_role(user, "HOTEL")
    association = user.get("id_estabelecimento")
    if not association:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    answered = {item["id_pesquisa"] for item in OCCUPANCY_RESPONSES if item.get("id_estabelecimento") == association}
    return {"data": [item for item in SURVEYS if item["status"] == "ABERTA" and association in item["estabelecimentos"] and item["id_pesquisa"] not in answered]}


@app.post("/pesquisas-ocupacao/{id_pesquisa}/respostas", status_code=status.HTTP_201_CREATED, tags=["Respostas de ocupação"])
def submit_occupancy_response(id_pesquisa: str, payload: dict = Body(...), user: dict = Depends(current_user)) -> Any:
    ensure_role(user, "HOTEL")
    association = user.get("id_estabelecimento")
    survey = next((item for item in SURVEYS if item["id_pesquisa"] == id_pesquisa), None)
    if not survey:
        return error_response(404, "SURVEY_NOT_FOUND", "Pesquisa não encontrada.")
    if not association or association not in survey["estabelecimentos"]:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    if survey["status"] != "ABERTA":
        return error_response(409, "SURVEY_CLOSED", "A pesquisa não está aberta para respostas.")
    operations.fields(payload, {"taxa_ocupacao"}, {"taxa_ocupacao"})
    rate = payload["taxa_ocupacao"]
    if isinstance(rate, bool) or not isinstance(rate, (float, int)) or not 0 <= rate <= 100:
        raise invalid_field("taxa_ocupacao", "Informe uma taxa entre 0 e 100%.")
    if any(item["id_pesquisa"] == id_pesquisa and item.get("id_estabelecimento") == association for item in OCCUPANCY_RESPONSES):
        return error_response(409, "RESPONSE_ALREADY_SENT", "A resposta desta pesquisa já foi enviada.")
    response = {"id_resposta": str(uuid4()), "id_pesquisa": id_pesquisa, "id_usuario": user["id_usuario"], "id_estabelecimento": association, "dados": payload, "enviada_em": datetime.now(timezone.utc).isoformat()}
    OCCUPANCY_RESPONSES.append(response)
    audit(user, "RESPOSTA_OCUPACAO_ENVIADA", "RESPOSTA_OCUPACAO", response["id_resposta"], after=response)
    return response


@app.get("/respostas-ocupacao/historico", tags=["Respostas de ocupação"])
def occupancy_history(user: dict = Depends(current_user)) -> dict:
    ensure_role(user, "ADMINISTRADOR", "GESTOR", "EDITOR", "HOTEL")
    if user["perfil"] != "HOTEL":
        return {"data": OCCUPANCY_RESPONSES}
    association = user.get("id_estabelecimento")
    if not association:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return {"data": [item for item in OCCUPANCY_RESPONSES if item.get("id_estabelecimento") == association]}


@app.get("/auditoria", tags=["Auditoria"])
def list_audit_log(acao: str | None = None, id_usuario: int | None = None, data_inicio: str | None = None, data_fim: str | None = None, user: dict = Depends(current_user)) -> dict:
    ensure_role(user, "ADMINISTRADOR")
    return {"data": audit_records(AUDIT_LOG, acao, id_usuario, data_inicio, data_fim)}


@app.get("/dashboard", tags=["Dashboard"])
def dashboard(user: dict = Depends(current_user), repository: InventoryRepository = Depends(inventory_repository)) -> dict:
    ensure_role(user, "ADMINISTRADOR", "GESTOR", "EDITOR")
    return dashboard_summary(repository, SURVEYS, OCCUPANCY_RESPONSES)


@app.post("/relatorios", status_code=status.HTTP_202_ACCEPTED, tags=["Relatórios"])
def generate_report(payload: dict = Body(...), user: dict = Depends(current_user)) -> Any:
    ensure_role(user, "ADMINISTRADOR", "GESTOR")
    report_type, report_format = payload.get("tipo"), payload.get("formato")
    if report_type != "OCUPACAO" or report_format not in ("PDF", "CSV"):
        return error_response(422, "VALIDATION_ERROR", "Informe tipo OCUPACAO e formato PDF ou CSV.")
    survey_id = payload.get("id_pesquisa")
    if survey_id and not any(item["id_pesquisa"] == survey_id for item in SURVEYS):
        return error_response(404, "SURVEY_NOT_FOUND", "Pesquisa não encontrada.")
    surveys = {item["id_pesquisa"]: item for item in SURVEYS}
    rows = [["Pesquisa", "Hospedagem", "Período inicial", "Período final", "Ocupação (%)", "Enviada em"]]
    for item in OCCUPANCY_RESPONSES:
        if survey_id and item["id_pesquisa"] != survey_id:
            continue
        survey = surveys.get(item["id_pesquisa"], {})
        establishment = inventory_repository().establishment(item.get("id_estabelecimento", "")) or {}
        rows.append([survey.get("titulo", ""), establishment.get("nome_fantasia", ""), survey.get("periodo_inicio", ""), survey.get("periodo_fim", ""), item["dados"].get("taxa_ocupacao", ""), item["enviada_em"]])
    content, mime = build_report(report_format, rows)
    report_id = str(uuid4())
    report = {"id_relatorio": report_id, "tipo": report_type, "formato": report_format, "status": "CONCLUIDO", "criado_em": datetime.now(timezone.utc).isoformat(), "download_url": f"/relatorios/{report_id}/arquivo"}
    REPORT_FILES[report_id] = (content, mime)
    REPORTS.append(report)
    audit(user, "RELATORIO_GERADO", "RELATORIO", report_id, after=report)
    return report


@app.get("/relatorios/{id_relatorio}", tags=["Relatórios"])
def get_report(id_relatorio: str, user: dict = Depends(current_user)) -> Any:
    ensure_role(user, "ADMINISTRADOR", "GESTOR")
    report = next((item for item in REPORTS if item["id_relatorio"] == id_relatorio), None)
    if not report:
        return error_response(404, "REPORT_NOT_FOUND", "Relatório não encontrado.")
    return report


@app.get("/relatorios/{id_relatorio}/arquivo", tags=["Relatórios"])
def download_report(id_relatorio: str, user: dict = Depends(current_user)) -> Any:
    report = get_report(id_relatorio, user)
    if isinstance(report, JSONResponse):
        return report
    if id_relatorio not in REPORT_FILES:
        return error_response(404, "NOT_FOUND", "Arquivo não encontrado.")
    content, mime = REPORT_FILES[id_relatorio]
    return Response(content=content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="relatorio.{report["formato"].lower()}"'})
