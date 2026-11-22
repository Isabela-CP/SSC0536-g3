export const xlsxType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
export const importColumns = ['id_categoria', 'nome_fantasia', 'razao_social', 'cnpj', 'endereco']

export async function tableFile(rows, format, title) {
  if (format === 'XLSX') {
    const { default: writeExcelFile } = await import('write-excel-file/universal')
    const cells = rows.map((row, index) => row.map((value) => ({
      type: String, value: String(value ?? ''), fontWeight: index === 0 ? 'bold' : undefined,
    })))
    return writeExcelFile(cells, { columns: rows[0].map(() => ({ width: 28 })) }).toBlob()
  }
  if (format === 'PDF') {
    const { jsPDF } = await import('jspdf')
    const pdf = new jsPDF({ orientation: 'landscape' })
    pdf.setFontSize(11)
    let y = 20
    const heading = () => {
      pdf.text(title, 12, y)
      y += 8
    }
    heading()
    for (const row of rows) {
      const lines = pdf.splitTextToSize(row.join(' | '), 270)
      for (const line of lines) {
        if (y > 195) {
          pdf.addPage()
          y = 20
          heading()
        }
        pdf.text(line, 12, y)
        y += 6
      }
    }
    return pdf.output('blob')
  }
  const csv = rows.map((row) => row.map((value) => {
    let text = String(value ?? '')
    if (/^\s*[=+\-@]/.test(text)) text = "'" + text
    return '"' + text.replaceAll('"', '""') + '"'
  }).join(',')).join('\r\n')
  return new Blob([csv], { type: 'text/csv' })
}

export async function readInventorySheet(file) {
  if (!file?.name?.toLowerCase().endsWith('.xlsx') || !file.size)
    throw new Error('Selecione uma planilha .xlsx.')
  if (file.size > 1024 * 1024) throw new Error('A planilha deve ter até 1 MB.')
  const { readSheet } = await import('read-excel-file/universal')
  let sheet
  try {
    sheet = await readSheet(file)
  } catch {
    throw new Error('Não foi possível ler a planilha Excel.')
  }
  const [header, ...entries] = sheet
  if (!header || header.length !== importColumns.length ||
      !importColumns.every((field, index) => header[index] === field))
    throw new Error('Use os cabeçalhos da planilha modelo.')
  const rows = []
  for (const [index, values] of entries.entries()) {
    if (values.every((value) => value == null || value === '')) continue
    if (rows.length >= 200) throw new Error('Importe até 200 linhas por arquivo.')
    const line = index + 2
    if (values.some((value) => value != null && typeof value !== 'number' && typeof value !== 'string'))
      throw new Error(`Linha ${line}: use apenas texto ou números.`)
    rows.push({
      line,
      payload: Object.fromEntries(importColumns.map((field, column) => [
        field,
        field === 'id_categoria' ? Number(values[column]) : String(values[column] ?? '').trim(),
      ])),
    })
  }
  if (!rows.length) throw new Error('A planilha não tem estabelecimentos para importar.')
  return rows
}
