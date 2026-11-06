"""Arquivos de relatório gerados a partir dos registros do servidor."""
import csv
from io import BytesIO, StringIO
from xml.sax.saxutils import escape


def build_report(format, rows):
    if format == "CSV":
        text = StringIO(newline="")
        writer = csv.writer(text)
        for row in rows:
            writer.writerow(["'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value for value in row])
        return text.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    output = BytesIO()
    styles = getSampleStyleSheet()
    content = [[Paragraph(escape(str(value)), styles["BodyText"]) for value in row] for row in rows]
    table = Table(content, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf4f8")), ("GRID", (0, 0), (-1, -1), .5, colors.HexColor("#bdd6e7")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    document = SimpleDocTemplate(output, pagesize=landscape(A4), title="Relatório OTO", leftMargin=32, rightMargin=32)
    document.build([Paragraph("Relatório de ocupação — OTO", styles["Title"]), Spacer(1, 18), table])
    return output.getvalue(), "application/pdf"
