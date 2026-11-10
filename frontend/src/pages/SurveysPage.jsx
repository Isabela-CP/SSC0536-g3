import React, { useState } from 'react'
import Modal from '../components/Modal.jsx'
import { Field } from '../components/FormFields.jsx'
import DataTable from '../components/DataTable.jsx'
import { OperationFeedback, ResourceState, ConfirmAction } from '../components/OperationsUI.jsx'
import { useOperation, useResource } from '../hooks/operations.js'
import { loadRecipients, validateSurvey, surveyPayload } from '../domain/operations.js'
import { surveyHistory, researchStats } from '../domain/reading.js'
import { exportReport } from '../services/reports.js'
const dates = (value) => value?.split('-').reverse().join('/') || '—'
function SurveyDialog({ api, survey, recipients, onClose, onSaved }) {
  const [draft, setDraft] = useState(
      survey
        ? {
            titulo: survey.titulo,
            tipo: survey.tipo,
            periodo_inicio: survey.periodo_inicio,
            periodo_fim: survey.periodo_fim,
            estabelecimentos: [...survey.estabelecimentos],
          }
        : {
            titulo: '',
            tipo: 'CONSOLIDADO',
            periodo_inicio: '',
            periodo_fim: '',
            estabelecimentos: [],
          },
    ),
    [errors, setErrors] = useState({}),
    [confirm, setConfirm] = useState(false),
    operation = useOperation()
  const eligible = recipients.filter((item) => item.status === 'ATIVO' && item.aceita_pesquisas)
  function submit(event) {
    event.preventDefault()
    const next = validateSurvey(draft)
    setErrors(next)
    if (Object.keys(next).length) return
    if (!confirm) {
      setConfirm(true)
      return
    }
    const payload = surveyPayload(draft, survey)
    if (!Object.keys(payload).length) {
      setErrors({ body: 'Altere pelo menos um campo.' })
      setConfirm(false)
      return
    }
    operation.run(
      () =>
        survey ? api.updateSurvey(survey.id_pesquisa, payload) : api.createSurvey(payload),
      () => {
        onSaved()
        onClose()
      },
    )
  }
  return (
    <Modal
      title={
        confirm ? 'Confirmar pesquisa' : survey ? 'Editar pesquisa' : 'Configurar Nova Pesquisa'
      }
      onClose={onClose}
      busy={operation.busy}
    >
      <form onSubmit={submit} noValidate>
        <OperationFeedback operation={operation} errors={errors} />
        {confirm ? (
          <div className="confirmation-copy">
            <p>
              <strong>{draft.titulo}</strong>
            </p>
            <p>
              {draft.tipo === 'CONSOLIDADO' ? 'Consolidado' : 'Expectativa'} ·{' '}
              {dates(draft.periodo_inicio)} a {dates(draft.periodo_fim)}
            </p>
            <p>
              A pesquisa ficará disponível para {draft.estabelecimentos.length} hospedagem(ns).
            </p>
          </div>
        ) : (
          <>
            <div className="field-grid">
              {[
                ['titulo', 'Título', { type: 'string' }],
                [
                  'tipo',
                  'Tipo',
                  { type: 'string' },
                  [
                    { value: 'CONSOLIDADO', label: 'Consolidado' },
                    { value: 'EXPECTATIVA', label: 'Expectativa' },
                  ],
                ],
                ['periodo_inicio', 'Data de início', { type: 'string', format: 'date' }],
                ['periodo_fim', 'Data final', { type: 'string', format: 'date' }],
              ].map(([path, label, schema, options]) => (
                <Field
                  key={path}
                  path={path}
                  schema={schema}
                  labelOverride={label}
                  options={options}
                  value={draft[path]}
                  disabled={operation.busy}
                  error={errors[path]}
                  onChange={(key, value) => {
                    setDraft((previous) => ({ ...previous, [key]: value }))
                    setErrors({})
                  }}
                />
              ))}
            </div>
            <fieldset id="field-estabelecimentos" className="recipient-picker" tabIndex={-1}>
              <legend>Hospedagens destinatárias</legend>
              <label>
                <input
                  type="checkbox"
                  checked={
                    !!eligible.length &&
                    eligible.every((item) =>
                      draft.estabelecimentos.includes(item.id_estabelecimento),
                    )
                  }
                  onChange={(event) =>
                    setDraft((previous) => ({
                      ...previous,
                      estabelecimentos: event.target.checked
                        ? eligible.map((item) => item.id_estabelecimento)
                        : [],
                    }))
                  }
                />{' '}
                Selecionar todas as hospedagens ativas que aceitam pesquisas
              </label>
              {eligible.map((item) => (
                <label key={item.id_estabelecimento}>
                  <input
                    type="checkbox"
                    checked={draft.estabelecimentos.includes(item.id_estabelecimento)}
                    onChange={(event) =>
                      setDraft((previous) => ({
                        ...previous,
                        estabelecimentos: event.target.checked
                          ? [...previous.estabelecimentos, item.id_estabelecimento]
                          : previous.estabelecimentos.filter(
                              (id) => id !== item.id_estabelecimento,
                            ),
                      }))
                    }
                  />{' '}
                  {item.nome_fantasia}
                </label>
              ))}
              {!eligible.length && <p>Nenhuma hospedagem apta a receber pesquisas.</p>}
            </fieldset>
          </>
        )}
        <div className="form-actions">
          <button
            className="button button-secondary"
            type="button"
            disabled={operation.busy}
            onClick={() => (confirm ? setConfirm(false) : onClose())}
          >
            {confirm ? 'Voltar' : 'Cancelar'}
          </button>
          <button
            className="button button-primary"
            disabled={operation.busy || !eligible.length}
          >
            {operation.busy
              ? 'Salvando…'
              : confirm
                ? 'Confirmar e disponibilizar'
                : 'Continuar'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
export default function SurveysPage({ api, user, initialData = null }) {
  const resource = useResource(
      async (options) => {
        const [surveys, recipients, history] = await Promise.all([
          api.surveys(options),
          loadRecipients(api, options),
          api.responseHistory(options),
        ])
        return { surveys: surveys.data, recipients, history: history.data }
      },
      [api],
      initialData,
    ),
    [editing, setEditing] = useState(undefined),
    [closing, setClosing] = useState(null),
    operation = useOperation()
  const [period, setPeriod] = useState(''),
    [kind, setKind] = useState('')
  const canManage = ['ADMINISTRADOR', 'EDITOR'].includes(user.perfil),
    canReport = ['ADMINISTRADOR', 'GESTOR'].includes(user.perfil)
  const data = resource.data,
    rows = surveyHistory(data?.surveys || [], data?.history || []).filter(
      (row) =>
        (!period ||
          (row.periodo_inicio.slice(0, 7) <= period &&
            row.periodo_fim.slice(0, 7) >= period)) &&
        (!kind || row.tipo === kind),
    )
  const statistics = researchStats(rows)
  const columns = [
    { key: 'titulo', label: 'Nome da Pesquisa' },
    {
      key: 'tipo',
      label: 'Tipo',
      render: (row) => (row.tipo === 'CONSOLIDADO' ? 'Consolidado' : 'Expectativa'),
    },
    {
      key: 'periodo',
      label: 'Período',
      render: (row) => `${dates(row.periodo_inicio)} a ${dates(row.periodo_fim)}`,
    },
    {
      key: 'taxa',
      label: 'Taxa de Resposta (%)',
      render: (row) => (row.responseRate == null ? '—' : `${row.responseRate.toFixed(0)}%`),
    },
    { key: 'status', label: 'Status' },
    {
      key: 'actions',
      label: 'Ações',
      render: (row) => (
        <div className="document-actions">
          <a
            className="button button-small button-secondary"
            href={`#/pesquisas/${row.id_pesquisa}/respostas`}
          >
            Ver respostas
          </a>
          {canManage && row.status === 'ABERTA' && (
            <>
              <button
                className="button button-small button-secondary"
                onClick={() => setEditing(row)}
              >
                Editar
              </button>
              <button
                className="button button-small button-secondary"
                onClick={() => setClosing(row)}
              >
                Encerrar
              </button>
            </>
          )}
          {canReport &&
            ['CSV', 'PDF'].map((formato) => (
              <button
                className="button button-small button-secondary"
                disabled={operation.busy}
                key={formato}
                onClick={() =>
                  operation.run(
                    () =>
                      exportReport(api, {
                        tipo: 'OCUPACAO',
                        formato,
                        id_pesquisa: row.id_pesquisa,
                      }),
                    () => operation.success('Download iniciado.'),
                  )
                }
              >
                Baixar {formato}
              </button>
            ))}
        </div>
      ),
    },
  ]
  return (
    <>
      <header className="page-heading">
        <h1>Gestão de Pesquisas de Ocupação</h1>
        {canManage && (
          <button
            className="button button-primary"
            disabled={!data}
            onClick={() => setEditing(null)}
          >
            Preparar Nova Pesquisa
          </button>
        )}
      </header>
      <ResourceState resource={resource} />
      <OperationFeedback operation={operation} />
      {data && (
        <>
          <div className="stat-grid">
            <article className="stat-card">
              <h2>Pesquisas Ativas</h2>
              <strong>{statistics.active}</strong>
            </article>
            <article className="stat-card">
              <h2>Respostas Coletadas no Mês</h2>
              <strong>{statistics.month}</strong>
            </article>
            <article className="stat-card">
              <h2>Taxa de Resposta</h2>
              <strong>
                {statistics.rate == null ? '—' : `${statistics.rate.toFixed(0)}%`}
              </strong>
            </article>
          </div>
          {canReport && (
            <button
              className="button button-primary consolidated-report"
              disabled={operation.busy || !data.surveys.length}
              onClick={() =>
                operation.run(
                  () => exportReport(api, { tipo: 'OCUPACAO', formato: 'PDF' }),
                  () => operation.success('Download iniciado.'),
                )
              }
            >
              Exportar Relatório Consolidado (PDF)
            </button>
          )}
          <div className="survey-filters">
            <label>
              Filtrar por Período (Mês/Ano)
              <input
                type="month"
                value={period}
                onChange={(event) => setPeriod(event.target.value)}
              />
            </label>
            <label>
              Filtrar por Tipo
              <select value={kind} onChange={(event) => setKind(event.target.value)}>
                <option value="">Todos</option>
                <option value="EXPECTATIVA">Expectativa</option>
                <option value="CONSOLIDADO">Realizado</option>
              </select>
            </label>
          </div>
          <DataTable
            columns={columns}
            rows={rows}
            caption="Pesquisas de ocupação"
            empty="Nenhuma pesquisa cadastrada."
          />
          {editing !== undefined && (
            <SurveyDialog
              api={api}
              survey={editing}
              recipients={data.recipients}
              onClose={() => setEditing(undefined)}
              onSaved={resource.reload}
            />
          )}{' '}
          {closing && (
            <ConfirmAction
              title="Encerrar pesquisa"
              onClose={() => setClosing(null)}
              action={() => api.closeSurvey(closing.id_pesquisa)}
              onDone={resource.reload}
              label="Encerrar"
            >
              <p>
                Confirma o encerramento de {closing.titulo}? Novas respostas não serão aceitas.
              </p>
            </ConfirmAction>
          )}
        </>
      )}
    </>
  )
}
