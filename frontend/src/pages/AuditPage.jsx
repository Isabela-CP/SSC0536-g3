import React, { useState } from 'react'
import { useResource } from '../hooks/operations.js'
import { ResourceState } from '../components/OperationsUI.jsx'
import { Feedback } from '../components/Feedback.jsx'
import DataTable from '../components/DataTable.jsx'
import { auditQuery, changes } from '../domain/reading.js'
const valueLabel = (value) => (value === undefined ? 'Campo ausente' : JSON.stringify(value))
export default function AuditPage({ api, user, initialData = null }) {
  const [draft, setDraft] = useState({
      acao: '',
      id_usuario: '',
      data_inicio: '',
      data_fim: '',
    }),
    [query, setQuery] = useState({}),
    [error, setError] = useState('')
  const resource = useResource(
    (options) =>
      user.perfil === 'ADMINISTRADOR'
        ? api.audit(query, options)
        : Promise.resolve({ data: [] }),
    [api, query, user.perfil],
    initialData,
  )
  if (user.perfil !== 'ADMINISTRADOR')
    return <Feedback message="Seu perfil não pode acessar a auditoria." />
  return (
    <>
      <header className="page-heading">
        <h1>Log de auditoria</h1>
      </header>
      <form
        className="audit-filters"
        noValidate
        onSubmit={(event) => {
          event.preventDefault()
          try {
            setQuery(auditQuery(draft))
            setError('')
          } catch (error) {
            setError(error.message)
          }
        }}
      >
        {[
          ['data_inicio', 'Data inicial', 'datetime-local'],
          ['data_fim', 'Data final', 'datetime-local'],
          ['id_usuario', 'Filtrar por Usuário (ID)', 'number'],
          ['acao', 'Ação', 'text'],
        ].map(([key, label, type]) => (
          <label key={key}>
            {label}
            <input
              type={type}
              min={type === 'number' ? '1' : undefined}
              value={draft[key]}
              onChange={(event) =>
                setDraft((previous) => ({ ...previous, [key]: event.target.value }))
              }
            />
          </label>
        ))}
        <button className="button button-primary" disabled={resource.loading}>
          Aplicar filtros
        </button>
      </form>
      <Feedback message={error} />
      <ResourceState resource={resource} />
      {resource.data && (
        <DataTable
          caption="Eventos de auditoria"
          rows={resource.data.data.flatMap((row) => {
            const diff = changes(row.antes, row.depois)
            return (
              diff.length
                ? diff
                : [{ label: 'Sem alteração de dados', before: row.antes, after: row.depois }]
            ).map((change, index) => ({ ...row, id: `${row.id}:${index}`, change }))
          })}
          columns={[
            {
              key: 'criado_em',
              label: 'Data/Hora',
              render: (row) => new Date(row.criado_em).toLocaleString('pt-BR'),
            },
            { key: 'usuario', label: 'Autor' },
            {
              key: 'id_entidade',
              label: 'Hotel / registro afetado',
              render: (row) =>
                row.entidade?.toUpperCase() === 'ESTABELECIMENTO' ? (
                  <a href={`#/estabelecimentos/${row.id_entidade}`}>
                    {row.depois?.nome_fantasia || row.antes?.nome_fantasia || row.id_entidade}
                  </a>
                ) : (
                  `${row.entidade}: ${row.id_entidade}`
                ),
            },
            {
              key: 'acao',
              label: 'O que mudou',
              render: (row) => (
                <>
                  {row.acao}
                  <br />
                  {row.change.label}
                </>
              ),
            },
            {
              key: 'antes',
              label: 'Valor Anterior',
              render: (row) => <code>{valueLabel(row.change.before)}</code>,
            },
            {
              key: 'depois',
              label: 'Valor Atual',
              render: (row) => <code>{valueLabel(row.change.after)}</code>,
            },
          ]}
        />
      )}
    </>
  )
}
