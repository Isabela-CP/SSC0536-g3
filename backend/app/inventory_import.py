"""Importa o modelo XLSX do inventário e valida o lote antes de persistir."""
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import ValidationError

from app.inventory_errors import InventoryError, invalid_field
from app.inventory_models import EstablishmentCreate
from app.inventory_service import cnpj_digits, valid_cnpj

UPLOAD_LIMIT = 1024 * 1024
HEADERS = ("id_categoria", "nome_fantasia", "razao_social", "cnpj", "endereco")


def import_workbook(service, actor, stream, filename):
    if not filename or not filename.lower().endswith(".xlsx"):
        raise InventoryError(415, "UNSUPPORTED_MEDIA_TYPE", "Selecione uma planilha .xlsx.")
    content = stream.read(UPLOAD_LIMIT + 1)
    if len(content) > UPLOAD_LIMIT:
        raise InventoryError(413, "PAYLOAD_TOO_LARGE", "A planilha deve ter até 1 MB.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 200 or sum(entry.file_size for entry in entries) > 8 * UPLOAD_LIMIT:
                raise InventoryError(413, "PAYLOAD_TOO_LARGE", "A planilha descompactada excede o limite.")
        workbook = load_workbook(BytesIO(content), read_only=True, keep_links=False)
        try:
            rows = parse_sheet(workbook.worksheets[0], service)
        finally:
            workbook.close()
    except (BadZipFile, InvalidFileException, ParseError, DefusedXmlException, KeyError, IndexError, ValueError):
        raise invalid_field("arquivo", "Não foi possível ler a planilha Excel.") from None

    with service.repository.transaction():
        ordered = sorted(rows, key=lambda row: row[1]["cnpj"])
        for _, payload in ordered:
            if hasattr(service.repository, "lock_cnpj"):
                service.repository.lock_cnpj(payload["cnpj"])
        existing = {cnpj_digits(row["cnpj"]) for row in service.repository.establishments() if row.get("cnpj")}
        conflicts = [{"field": f"Linha {line} · cnpj", "issue": "CNPJ já cadastrado."}
                     for line, payload in rows if payload["cnpj"] in existing]
        if conflicts:
            raise InventoryError(422, "VALIDATION_ERROR", "Verifique as linhas da planilha.", conflicts)
        for line, payload in ordered:
            try:
                service.create(actor, payload)
            except InventoryError as error:
                if error.status_code != 409:
                    raise
                raise invalid_field(f"Linha {line} · cnpj", "CNPJ já cadastrado.") from None
    return {"importados": len(rows)}


def parse_sheet(sheet, service):
    sheet.reset_dimensions()
    entries = sheet.iter_rows(max_col=len(HEADERS) + 1)
    header = tuple(cell.value for cell in next(entries, ()))
    if header != (*HEADERS, None):
        raise invalid_field("arquivo", "Use os cabeçalhos da planilha modelo.")
    seen, rows, details = set(), [], []
    count = 0
    categories = {row["id_categoria"] for row in service.repository.categories()}
    for line, cells in enumerate(entries, 2):
        if line > 1001:
            raise invalid_field("arquivo", "A planilha excede o limite de linhas.")
        values = tuple(cell.value for cell in cells)
        if all(value is None for value in values):
            continue
        count += 1
        if count > 200:
            raise invalid_field("arquivo", "Importe até 200 linhas por arquivo.")
        if values[-1] is not None or any(getattr(cell, "data_type", None) == "f" for cell in cells):
            details.append({"field": f"Linha {line}", "issue": "Use o modelo e valores sem fórmulas."})
            continue
        data = {field: value.strip() if isinstance(value, str) else value
                for field, value in zip(HEADERS, values)}
        try:
            data["id_categoria"] = int(str(data["id_categoria"]))
            data["cnpj"] = str(data["cnpj"] or "")
            payload = EstablishmentCreate.model_validate(data).model_dump(mode="json", exclude_unset=True)
        except (ValidationError, ValueError) as error:
            fields = ["id_categoria"] if not isinstance(error, ValidationError) else [
                ".".join(map(str, entry["loc"])) for entry in error.errors()]
            details.extend({"field": f"Linha {line} · {field}", "issue": "Valor inválido."} for field in fields)
            continue
        digits = cnpj_digits(payload["cnpj"])
        if not valid_cnpj(payload["cnpj"]) or digits in seen:
            details.append({"field": f"Linha {line} · cnpj", "issue": "CNPJ inválido ou repetido na planilha."})
            continue
        if payload["id_categoria"] not in categories:
            details.append({"field": f"Linha {line} · id_categoria", "issue": "Categoria inválida."})
            continue
        seen.add(digits)
        rows.append((line, {**payload, "cnpj": digits}))
    if details:
        raise InventoryError(422, "VALIDATION_ERROR", "Verifique as linhas da planilha.", details)
    if not rows:
        raise invalid_field("arquivo", "A planilha não tem estabelecimentos para importar.")
    return rows
