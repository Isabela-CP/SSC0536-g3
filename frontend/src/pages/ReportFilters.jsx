import React, { useState } from 'react'
import { OperationFeedback } from '../components/OperationsUI.jsx'
import { useOperation } from '../hooks/operations.js'
import { exportReport } from '../services/reports.js'

export default function ReportFilters({ api, categories }) {
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [category, setCategory] = useState('')
  const [format, setFormat] = useState('PDF')
  const operation = useOperation()
  return (
    <form className="form-card" onSubmit={(event) => {
      event.preventDefault()
      operation.run(async () => {
        if (!start || !end || start > end) throw new Error('Informe um período válido.')
        await exportReport(api, {
          tipo: 'OCUPACAO', formato: format, periodo_inicio: start, periodo_fim: end,
          ...(category && { id_categoria: Number(category) }),
        })
      }, () => operation.success('Download iniciado.'))
    }}>
      <h2>Relatório por período e categoria</h2>
      <OperationFeedback operation={operation} />
      <fieldset className="field-grid" disabled={operation.busy}>
        <label>Data inicial<input type="date" required value={start} onChange={(event) => setStart(event.target.value)} /></label>
        <label>Data final<input type="date" required min={start || undefined} value={end} onChange={(event) => setEnd(event.target.value)} /></label>
        <label>Categoria
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="">Todas</option>
            {categories.map((item) => <option key={item.id_categoria} value={item.id_categoria}>{item.nome_categoria}</option>)}
          </select>
        </label>
        <label>Formato
          <select value={format} onChange={(event) => setFormat(event.target.value)}>
            <option>PDF</option><option>CSV</option>
          </select>
        </label>
      </fieldset>
      <button className="button button-primary" disabled={operation.busy}>
        {operation.busy ? 'Gerando…' : 'Gerar relatório'}
      </button>
    </form>
  )
}
