"""Arquivos de relatório gerados a partir dos registros do servidor."""
import csv
from io import BytesIO, StringIO
from xml.sax.saxutils import escape
from app.cadastur import CadasturStatus


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def build_report(format, rows, title="Relatório de ocupação — OTO"):
    if format == "XLSX":
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet("Inventário")
        for row in rows:
            cells = [WriteOnlyCell(sheet, value=str(value)) for value in row]
            for cell in cells:
                cell.data_type = "s"
            sheet.append(cells)
        output = BytesIO()
        workbook.save(output)
        return output.getvalue(), XLSX_MIME
    if format == "CSV":
        text = StringIO(newline="")
        writer = csv.writer(text)
        for row in rows:
            writer.writerow(["'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value for value in row])
        return text.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    output = BytesIO()
    styles = getSampleStyleSheet()
    content = [[Paragraph(escape(str(value)), styles["BodyText"]) for value in row] for row in rows]
    table = Table(content, colWidths=[(landscape(A4)[0] - 64) / len(rows[0])] * len(rows[0]), repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf4f8")), ("GRID", (0, 0), (-1, -1), .5, colors.HexColor("#bdd6e7")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    document = SimpleDocTemplate(output, pagesize=landscape(A4), title="Relatório OTO", leftMargin=32, rightMargin=32)
    document.build([Paragraph(title, styles["Title"]), Spacer(1, 18), table])
    return output.getvalue(), "application/pdf"


def report_filters(payload):
    from datetime import date
    from app.inventory_errors import invalid_field
    start, end, category = payload.get("periodo_inicio"), payload.get("periodo_fim"), payload.get("id_categoria")
    if start is not None or end is not None:
        for field, value in (("periodo_inicio", start), ("periodo_fim", end)):
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            except (ValueError, TypeError):
                raise invalid_field(field, "Informe uma data no formato AAAA-MM-DD.") from None
        if start > end:
            raise invalid_field("periodo_fim", "A data final deve ser posterior ou igual à inicial.")
    if category is not None and (type(category) is not int or category < 1):
        raise invalid_field("id_categoria", "Informe um identificador válido.")
    return start, end, category


def occupancy_rows(payload, surveys, history, establishments):
    from app.inventory_errors import InventoryError
    start, end, category = report_filters(payload)
    selected = payload.get("id_pesquisa")
    if selected is not None and selected not in {survey["id_pesquisa"] for survey in surveys}:
        raise InventoryError(404, "SURVEY_NOT_FOUND", "Pesquisa não encontrada.")
    items = {row["id_estabelecimento"]: row for row in establishments}
    responses = {(row["id_pesquisa"], row["id_estabelecimento"]): row for row in history}
    rows = [["Pesquisa", "Hospedagem", "Início", "Fim", "Ocupação (%)", "Respondida em"]]
    answered = False
    for survey in surveys:
        if selected is not None and survey["id_pesquisa"] != selected:
            continue
        if start and (survey["periodo_inicio"] > end or survey["periodo_fim"] < start):
            continue
        for identifier in survey["estabelecimentos"]:
            item = items.get(identifier)
            if item is None or (category is not None and item["id_categoria"] != category):
                continue
            response = responses.get((survey["id_pesquisa"], identifier))
            answered |= response is not None
            rows.append([survey["titulo"], item["nome_fantasia"], survey["periodo_inicio"],
                         survey["periodo_fim"], response["dados"]["taxa_ocupacao"] if response else "Sem resposta",
                         response["enviada_em"] if response else ""])
    if not answered:
        raise InventoryError(409, "REPORT_NO_DATA", "Nenhuma resposta encontrada para gerar o relatório.")
    return rows


def report_rows(payload, repository, surveys, history):
    from app import operations
    from app.inventory import InventoryQuery, query_establishments
    from app.inventory_errors import invalid_field
    from app.postgres_inventory import PostgresInventoryRepository
    kind, fmt = payload.get("tipo"), payload.get("formato")
    if kind == "OCUPACAO":
        operations.fields(payload, {"tipo", "formato", "id_pesquisa", "periodo_inicio", "periodo_fim", "id_categoria"})
        if fmt not in ("PDF", "CSV"):
            raise invalid_field("formato", "Informe PDF ou CSV para o relatório de ocupação.")
        return occupancy_rows(payload, surveys(), history(), repository.establishments())
    if kind != "INVENTARIO":
        raise invalid_field("tipo", "Informe OCUPACAO ou INVENTARIO.")
    if fmt not in ("PDF", "XLSX"):
        raise invalid_field("formato", "Informe PDF ou XLSX para o boletim de inventário.")
    operations.fields(payload, {"tipo", "formato", "filtros"})
    filters = payload.get("filtros", {})
    from pydantic import BaseModel, ConfigDict, Field, ValidationError
    from typing import Literal

    class Filters(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        busca: str | None = Field(None, max_length=120)
        id_categoria: int | None = Field(None, ge=1)
        status: Literal["ATIVO", "INATIVO"] | None = None
        cadastur_status: CadasturStatus | None = None
        aceita_pesquisas: bool | None = None
        leitos_min: int | None = Field(None, ge=0, le=2147483647)
        somente_hospedagem: bool = False
        ordenar_por: Literal["nome_fantasia", "criado_em", "atualizado_em"] = "nome_fantasia"
        ordem: Literal["asc", "desc"] = "asc"

    try:
        params = Filters.model_validate(filters).model_dump()
    except ValidationError:
        raise invalid_field("filtros", "Informe filtros válidos do inventário.") from None

    from dataclasses import replace
    query = InventoryQuery(**params, page_size=100)
    rows = [["Nome", "CNPJ", "Categoria", "Bairro", "Status"]]
    categories = {row["id_categoria"]: row["nome_categoria"] for row in repository.categories()}
    while True:
        result = (repository.query(query) if isinstance(repository, PostgresInventoryRepository)
                  else query_establishments(repository, query))
        rows.extend([item["nome_fantasia"], item.get("cnpj") or "", categories.get(item["id_categoria"], ""),
                     item.get("bairro") or "", item["status"]] for item in result["data"])
        if query.page >= result["pagination"]["total_pages"]:
            return rows
        query = replace(query, page=query.page + 1)
