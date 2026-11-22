import React, { useState } from 'react'
import { useResource } from '../hooks/operations.js'
import { ResourceState } from '../components/OperationsUI.jsx'
import { Feedback } from '../components/Feedback.jsx'
import DataTable from '../components/DataTable.jsx'
import { loadRecipients } from '../domain/operations.js'
import { auditQuery, changes } from '../domain/reading.js'
const valueLabel = (value) => (value === undefined ? 'Campo ausente' : JSON.stringify(value))
export default function AuditPage({ api, user, initialData = null }) {
  const [draft, setDraft] = useState({
      acao: '',
      id_entidade: '',
      id_usuario: '',
      data_inicio: '',
      data_fim: '',
    }),
    [query, setQuery] = useState({}),
    [error, setError] = useState('')
  const companies = useResource(
    (options) => api.preview && user.perfil === 'ADMINISTRADOR' ? loadRecipients(api, options) : [],
    [api, user.perfil],
    [],
  )
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
              value={draft[key]}
              onChange={(event) =>
                setDraft((previous) => ({ ...previous, [key]: event.target.value }))
              }
            />
          </label>
        ))}
        {api.preview && (
          <label>
            Empresa
            <select value={draft.id_entidade} disabled={companies.loading}
              onChange={(event) => setDraft((previous) => ({ ...previous, id_entidade: event.target.value }))}>
              <option value="">Todas</option>
              {companies.data.map((item) => <option key={item.id_estabelecimento} value={item.id_estabelecimento}>{item.nome_fantasia}</option>)}
            </select>
          </label>
        )}
        <button className="button button-primary" disabled={resource.loading}>
          Aplicar filtros
        </button>
      </form>
      {api.preview && <ResourceState resource={companies} />}
      <Feedback message={error} />
      <ResourceState resource={resource} />
      <p className="muted">Cada linha representa um campo alterado.</p>
      {!resource.error && resource.data && (
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
