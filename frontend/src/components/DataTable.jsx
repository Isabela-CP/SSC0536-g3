import React, { useState } from 'react'
export default function DataTable({
  columns,
  rows,
  caption,
  empty = 'Nenhum registro encontrado.',
  pageSize = 5,
}) {
  const [page, setPage] = useState(1),
    total = Math.max(1, Math.ceil(rows.length / pageSize)),
    current = Math.min(page, total)
  return (
    <div className="data-table">
      <div className="table-scroll">
        <table>
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key} scope="col">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice((current - 1) * pageSize, current * pageSize).map((row, index) => (
              <tr
                key={
                  row.id ||
                  row.id_estabelecimento ||
                  row.id_usuario ||
                  row.id_pesquisa ||
                  row.id_resposta ||
                  index
                }
              >
                {columns.map((column) => (
                  <td key={column.key}>
                    {column.render ? column.render(row) : (row[column.key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={columns.length}>{empty}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <footer className="table-pagination">
        <span>
          Página {current} de {total}
        </span>
        <div>
          <button
            className="button button-small button-secondary"
            disabled={current === 1}
            onClick={() => setPage(current - 1)}
          >
            ‹ Anterior
          </button>
          <button
            className="button button-small button-primary"
            disabled={current === total}
            onClick={() => setPage(current + 1)}
          >
            Próximo ›
          </button>
        </div>
      </footer>
    </div>
  )
}
