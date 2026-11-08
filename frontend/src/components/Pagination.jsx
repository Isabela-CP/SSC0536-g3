import React from 'react'
export default function Pagination({ pagination, onPage, busy = false }) {
  return (
    <footer className="table-pagination">
      <span>
        Página {pagination.page} de {pagination.total_pages} · {pagination.total} registro(s)
      </span>
      <div>
        <button
          className="button button-small button-secondary"
          disabled={busy || pagination.page <= 1}
          onClick={() => onPage(pagination.page - 1)}
        >
          ‹ Anterior
        </button>
        <button
          className="button button-small button-primary"
          disabled={busy || pagination.page >= pagination.total_pages}
          onClick={() => onPage(pagination.page + 1)}
        >
          Próximo ›
        </button>
      </div>
    </footer>
  )
}
