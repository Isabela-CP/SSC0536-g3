import React, { useState } from 'react'
import { useOperation } from '../hooks/operations.js'
import { saveDownload } from '../domain/documents.js'
import { importColumns, tableFile } from '../services/inventoryFiles.js'
import { Feedback } from '../components/Feedback.jsx'

export default function InventoryFiles({ api, rows, categories, canImport, loading, onImported }) {
  const operation = useOperation()
  const [file, setFile] = useState(null)
  const [inputVersion, setInputVersion] = useState(0)
  const names = new Map(categories.map((entry) => [entry.id_categoria, entry.nome_categoria]))
  const exportRows = async (format) => {
    const table = [['Nome', 'CNPJ', 'Categoria', 'Bairro', 'Status'], ...rows.map((row) => [
      row.nome_fantasia, row.cnpj || '', names.get(row.id_categoria) || '', row.bairro || '', row.status,
    ])]
    saveDownload({ blob: await tableFile(table, format, 'Boletim do Inventário') },
      `inventario.${format.toLowerCase()}`)
  }
  return (
    <section className="form-card">
      <h2>Arquivos do inventário</h2>
      <Feedback message={operation.error?.message} />
      <Feedback kind="success" message={operation.message} />
      {!!Object.keys(operation.error?.fields || {}).length && (
        <ul aria-label="Erros por linha da planilha">
          {Object.entries(operation.error.fields).map(([field, issue]) => (
            <li key={field}>{field} — {issue}</li>
          ))}
        </ul>
      )}
      <div className="document-actions">
        {['PDF', 'XLSX'].map((format) => (
          <button type="button" key={format} className="button button-secondary"
            disabled={loading || operation.busy || !rows.length}
            onClick={() => operation.run(() => exportRows(format), () => operation.success('Download iniciado.'))}>
            Exportar lista em {format === 'XLSX' ? 'Excel' : format}
          </button>
        ))}
      </div>
      {canImport && (
        <form onSubmit={(event) => {
          event.preventDefault()
          if (!file) return
          operation.run(() => api.importInventory(file), ({ importados }) => {
            operation.success(`${importados} estabelecimento(s) importado(s).`)
            setFile(null)
            setInputVersion((previous) => previous + 1)
            onImported()
          })
        }}>
          <p>Use o modelo Excel e preencha o ID da categoria indicado abaixo.</p>
          <p>{categories.map((item) => `${item.id_categoria} — ${item.nome_categoria}`).join(' · ')}</p>
          <div className="document-actions">
            <button type="button" className="button button-secondary" disabled={operation.busy}
              onClick={() => operation.run(async () => {
                saveDownload({ blob: await tableFile([importColumns], 'XLSX') }, 'modelo-inventario.xlsx')
              })}>
              Baixar modelo Excel
            </button>
            <label>
              Planilha Excel (.xlsx)
              <input key={inputVersion} type="file" accept=".xlsx" disabled={operation.busy}
                onChange={(event) => { setFile(event.target.files?.[0] || null); operation.clear() }} />
            </label>
            <button className="button button-primary" disabled={loading || operation.busy || !file}>
              {operation.busy ? 'Aguarde…' : 'Importar planilha'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
