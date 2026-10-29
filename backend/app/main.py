from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


ROOT_DIR = Path(__file__).resolve().parents[2]
SEED_FILE = ROOT_DIR / "contratos_api_oto" / "mocks" / "seed-data.json"

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


def error_response(status_code: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error})


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")
    email = TOKENS.get(authorization.removeprefix("Bearer "))
    if not email:
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")
    return DEMO_USERS[email]


def audit(actor: dict, action: str, entity: str, entity_id: str, before: Any = None, after: Any = None) -> None:
    AUDIT_LOG.append({
        "id": str(uuid4()), "criado_em": datetime.now(timezone.utc).isoformat(),
        "id_usuario": actor["id_usuario"], "usuario": actor["email"], "acao": action,
        "entidade": entity, "id_entidade": entity_id, "antes": before, "depois": after,
    })


def ensure_role(user: dict, *roles: str) -> None:
    if user["perfil"] not in roles:
        raise HTTPException(status_code=403, detail="FORBIDDEN")


def seed_data() -> dict:
    """Lê a fonte única de dados de desenvolvimento a cada requisição."""
    with SEED_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def find_establishment(establishment_id: str) -> dict:
    for establishment in seed_data()["estabelecimentos"]:
        if establishment["id_estabelecimento"] == establishment_id:
            return establishment
    raise HTTPException(status_code=404, detail="Estabelecimento não encontrado.")


@app.get("/health", tags=["Sistema"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/categorias-estabelecimento", tags=["Categorias"])
def list_categories() -> dict:
    return {"data": seed_data()["categorias_estabelecimento"]}


@app.get("/estabelecimentos", tags=["Estabelecimentos"])
def list_establishments(
    busca: str | None = None,
    status: str | None = None,
    id_categoria: int | None = None,
    aceita_pesquisas: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    establishments = seed_data()["estabelecimentos"]
    if busca:
        term = busca.casefold()
        establishments = [
            item for item in establishments
            if term in " ".join(
                [item["nome_fantasia"], item["razao_social"], item["cnpj"]]
            ).casefold()
        ]
    if status:
        establishments = [item for item in establishments if item["status"] == status]
    if id_categoria:
        establishments = [item for item in establishments if item["id_categoria"] == id_categoria]
    if aceita_pesquisas is not None:
        establishments = [
            item for item in establishments if item["aceita_pesquisas"] == aceita_pesquisas
        ]

    total = len(establishments)
    start = (page - 1) * page_size
    summaries = [
        {
            key: item[key]
            for key in (
                "id_estabelecimento", "id_categoria", "nome_fantasia", "razao_social",
                "cnpj", "bairro", "status", "cadastur_status", "possui_cadastur",
                "aceita_pesquisas", "latitude", "longitude",
            )
        }
        for item in establishments[start : start + page_size]
    ]
    return {
        "data": summaries,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        },
    }


@app.get("/estabelecimentos/{id_estabelecimento}", tags=["Estabelecimentos"])
def get_establishment(id_estabelecimento: str) -> dict:
    return find_establishment(id_estabelecimento)


@app.get("/estabelecimentos/{id_estabelecimento}/documentos", tags=["Documentos"])
def list_documents(id_estabelecimento: str) -> dict:
    return {"data": find_establishment(id_estabelecimento)["documentos"]}


@app.post("/auth/login", tags=["Autenticação"])
def login(payload: dict = Body(...)) -> Any:
    user = DEMO_USERS.get(payload.get("email", "").casefold())
    if not user or user["senha"] != payload.get("senha") or not user["ativo"]:
        return error_response(401, "INVALID_CREDENTIALS", "E-mail ou senha inválidos.")
    token = next(token for token, email in TOKENS.items() if email == user["email"])
    return {"access_token": token, "token_type": "Bearer", "expires_in": 3600, "usuario": public_user(user)}


@app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["Autenticação"])
def logout(_: dict = Depends(current_user)) -> None:
    return None


@app.post("/auth/recuperacao-senha", status_code=status.HTTP_202_ACCEPTED, tags=["Autenticação"])
def recover_password(payload: dict = Body(...)) -> dict:
    return {"message": "Se o e-mail estiver cadastrado, as instruções de recuperação serão enviadas."}


def public_user(user: dict) -> dict:
    return {key: user[key] for key in ("id_usuario", "nome", "email", "perfil", "ativo")}


@app.get("/perfil", tags=["Perfil"])
def get_profile(user: dict = Depends(current_user)) -> dict:
    return public_user(user)


@app.patch("/perfil", tags=["Perfil"])
def update_profile(payload: dict = Body(...), user: dict = Depends(current_user)) -> Any:
    allowed = {"nome", "email"}
    invalid = set(payload) - allowed
    if invalid:
        return error_response(422, "VALIDATION_ERROR", "Verifique os campos informados.", [{"field": next(iter(invalid)), "issue": "Campo não pode ser alterado no perfil."}])
    if "email" in payload and payload["email"].casefold() != user["email"] and payload["email"].casefold() in DEMO_USERS:
        return error_response(409, "EMAIL_ALREADY_EXISTS", "Já existe uma conta com esse e-mail.")
    before = public_user(user)
    for key, value in payload.items():
        user[key] = value.casefold() if key == "email" else value
    audit(user, "PERFIL_ATUALIZADO", "USUARIO", str(user["id_usuario"]), before, public_user(user))
    return public_user(user)


@app.get("/usuarios", tags=["Usuários"])
def list_users(user: dict = Depends(current_user)) -> dict:
    ensure_role(user, "ADMINISTRADOR")
    return {"data": [public_user(item) for item in DEMO_USERS.values()]}


@app.post("/usuarios", status_code=status.HTTP_201_CREATED, tags=["Usuários"])
def create_user(payload: dict = Body(...), user: dict = Depends(current_user)) -> Any:
    ensure_role(user, "ADMINISTRADOR")
    required = {"nome", "email", "perfil"}
    missing = required - set(payload)
    if missing:
        return error_response(422, "VALIDATION_ERROR", "Verifique os campos informados.", [{"field": sorted(missing)[0], "issue": "Campo obrigatório."}])
    email = payload["email"].casefold()
    if email in DEMO_USERS:
        return error_response(409, "EMAIL_ALREADY_EXISTS", "Já existe uma conta com esse e-mail.")
    if payload["perfil"] not in {"ADMINISTRADOR", "GESTOR", "EDITOR", "HOTEL"}:
        return error_response(422, "VALIDATION_ERROR", "Verifique os campos informados.", [{"field": "perfil", "issue": "Perfil inválido."}])
    created = {"id_usuario": len(DEMO_USERS) + 1, "nome": payload["nome"], "email": email, "perfil": payload["perfil"], "senha": "", "ativo": False}
    DEMO_USERS[email] = created
    audit(user, "USUARIO_CRIADO", "USUARIO", str(created["id_usuario"]), after=public_user(created))
    return public_user(created)


@app.post("/convites", status_code=status.HTTP_201_CREATED, tags=["Convites"])
def create_invite(payload: dict = Body(...), user: dict = Depends(current_user)) -> Any:
    ensure_role(user, "ADMINISTRADOR")
    email = payload.get("email", "").casefold()
    if email not in DEMO_USERS:
        return error_response(404, "USER_NOT_FOUND", "Usuário não encontrado para convite.")
    invite = {"id_convite": str(uuid4()), "email": email, "status": "PENDENTE", "expira_em": "2026-11-03T23:59:59Z", "token": str(uuid4())}
    INVITES.append(invite)
    audit(user, "CONVITE_ENVIADO", "CONVITE", invite["id_convite"], after={"email": email})
    return {key: value for key, value in invite.items() if key != "token"}


@app.post("/convites/{id_convite}/aceitacao", tags=["Convites"])
def accept_invite(id_convite: str, payload: dict = Body(...)) -> Any:
    invite = next((item for item in INVITES if item["id_convite"] == id_convite), None)
    if not invite or invite["token"] != payload.get("token"):
        return error_response(404, "INVITE_NOT_FOUND", "Convite não encontrado ou expirado.")
    if invite["status"] != "PENDENTE":
        return error_response(409, "INVITE_ALREADY_USED", "Convite já utilizado.")
    invited = DEMO_USERS[invite["email"]]
    invited["senha"] = payload.get("senha", "")
    invited["ativo"] = True
    invite["status"] = "ACEITO"
    return {"message": "Acesso ativado com sucesso.", "usuario": public_user(invited)}


@app.get("/pesquisas-ocupacao", tags=["Pesquisas de ocupação"])
def list_surveys(user: dict = Depends(current_user)) -> dict:
    return {"data": SURVEYS}


@app.post("/pesquisas-ocupacao", status_code=status.HTTP_201_CREATED, tags=["Pesquisas de ocupação"])
def create_survey(payload: dict = Body(...), user: dict = Depends(current_user)) -> Any:
    ensure_role(user, "ADMINISTRADOR", "EDITOR")
    required = {"titulo", "tipo", "periodo_inicio", "periodo_fim", "estabelecimentos"}
    missing = required - set(payload)
    if missing:
        return error_response(422, "VALIDATION_ERROR", "Verifique os campos informados.", [{"field": sorted(missing)[0], "issue": "Campo obrigatório."}])
    survey = {"id_pesquisa": str(uuid4()), "titulo": payload["titulo"], "tipo": payload["tipo"], "periodo_inicio": payload["periodo_inicio"], "periodo_fim": payload["periodo_fim"], "estabelecimentos": payload["estabelecimentos"], "status": "ABERTA", "criada_por": user["id_usuario"]}
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
    invalid = set(payload) - allowed
    if invalid:
        return error_response(422, "VALIDATION_ERROR", "Verifique os campos informados.", [{"field": sorted(invalid)[0], "issue": "Campo não permitido."}])
    before = survey.copy()
    survey.update(payload)
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
    establishment_id = user.get("id_estabelecimento")
    open_surveys = [item for item in SURVEYS if item["status"] == "ABERTA" and (not establishment_id or establishment_id in item["estabelecimentos"])]
    answered = {item["id_pesquisa"] for item in OCCUPANCY_RESPONSES if item["id_usuario"] == user["id_usuario"]}
    return {"data": [item for item in open_surveys if item["id_pesquisa"] not in answered]}


@app.post("/pesquisas-ocupacao/{id_pesquisa}/respostas", status_code=status.HTTP_201_CREATED, tags=["Respostas de ocupação"])
def submit_occupancy_response(id_pesquisa: str, payload: dict = Body(...), user: dict = Depends(current_user)) -> Any:
    survey = next((item for item in SURVEYS if item["id_pesquisa"] == id_pesquisa), None)
    if not survey:
        return error_response(404, "SURVEY_NOT_FOUND", "Pesquisa não encontrada.")
    if survey["status"] != "ABERTA":
        return error_response(409, "SURVEY_CLOSED", "A pesquisa não está aberta para respostas.")
    if any(item["id_pesquisa"] == id_pesquisa and item["id_usuario"] == user["id_usuario"] for item in OCCUPANCY_RESPONSES):
        return error_response(409, "RESPONSE_ALREADY_SENT", "A resposta desta pesquisa já foi enviada.")
    response = {"id_resposta": str(uuid4()), "id_pesquisa": id_pesquisa, "id_usuario": user["id_usuario"], "dados": payload, "enviada_em": datetime.now(timezone.utc).isoformat()}
    OCCUPANCY_RESPONSES.append(response)
    audit(user, "RESPOSTA_OCUPACAO_ENVIADA", "RESPOSTA_OCUPACAO", response["id_resposta"], after=response)
    return response


@app.get("/respostas-ocupacao/historico", tags=["Respostas de ocupação"])
def occupancy_history(user: dict = Depends(current_user)) -> dict:
    if user["perfil"] == "ADMINISTRADOR":
        return {"data": OCCUPANCY_RESPONSES}
    return {"data": [item for item in OCCUPANCY_RESPONSES if item["id_usuario"] == user["id_usuario"]]}


@app.get("/auditoria", tags=["Auditoria"])
def list_audit_log(acao: str | None = None, id_usuario: int | None = None, data_inicio: str | None = None, data_fim: str | None = None, user: dict = Depends(current_user)) -> dict:
    ensure_role(user, "ADMINISTRADOR")
    records = AUDIT_LOG
    if acao:
        records = [item for item in records if item["acao"] == acao]
    if id_usuario:
        records = [item for item in records if item["id_usuario"] == id_usuario]
    if data_inicio:
        records = [item for item in records if item["criado_em"] >= data_inicio]
    if data_fim:
        records = [item for item in records if item["criado_em"] <= data_fim]
    return {"data": records}


@app.get("/dashboard", tags=["Dashboard"])
def dashboard(user: dict = Depends(current_user)) -> dict:
    establishments = seed_data()["estabelecimentos"]
    return {"indicadores": {"estabelecimentos_ativos": sum(item["status"] == "ATIVO" for item in establishments), "pesquisas_abertas": sum(item["status"] == "ABERTA" for item in SURVEYS), "respostas_recebidas": len(OCCUPANCY_RESPONSES)}, "alertas": [{"tipo": "DOCUMENTO_A_VENCER", "id_estabelecimento": "11111111-1111-4111-8111-111111111111", "mensagem": "AVCB vence em breve."}]}


@app.post("/relatorios", status_code=status.HTTP_202_ACCEPTED, tags=["Relatórios"])
def generate_report(payload: dict = Body(...), user: dict = Depends(current_user)) -> Any:
    ensure_role(user, "ADMINISTRADOR", "GESTOR")
    report_type = payload.get("tipo")
    report_format = payload.get("formato")
    if not report_type or report_format not in {"PDF", "CSV"}:
        return error_response(422, "VALIDATION_ERROR", "Tipo e formato PDF ou CSV são obrigatórios.")
    report_id = str(uuid4())
    report = {"id_relatorio": report_id, "tipo": report_type, "formato": report_format, "status": "CONCLUIDO", "criado_em": datetime.now(timezone.utc).isoformat(), "download_url": f"/relatorios/{report_id}/arquivo"}
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
    return {"id_relatorio": id_relatorio, "formato": report["formato"], "content": "Arquivo de demonstração; use storage na implementação de produção."}


