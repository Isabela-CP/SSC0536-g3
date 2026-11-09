import React, { useState } from 'react'
import Modal from '../components/Modal.jsx'
import { Field } from '../components/FormFields.jsx'
import { OperationFeedback, ResourceState } from '../components/OperationsUI.jsx'
import { useOperation, useResource } from '../hooks/operations.js'
import { validateOccupancy } from '../domain/operations.js'
function AnswerDialog({ survey, api, onClose, onSaved }) {
  const [rate, setRate] = useState(''),
    [errors, setErrors] = useState({}),
    [confirm, setConfirm] = useState(false),
    operation = useOperation()
  function submit(event) {
    event.preventDefault()
    const next = validateOccupancy(rate)
    setErrors(next)
    if (Object.keys(next).length) return
    if (!confirm) {
      setConfirm(true)
      return
    }
    operation.run(
      () => api.answerSurvey(survey.id_pesquisa, { taxa_ocupacao: Number(rate) }),
      () => {
        onSaved()
        onClose()
      },
    )
  }
  return (
    <Modal title={survey.titulo} onClose={onClose} busy={operation.busy}>
      <form onSubmit={submit} noValidate>
        <OperationFeedback operation={operation} errors={errors} />
        {confirm ? (
          <p>
            Confirma o envio da taxa de ocupação de <strong>{rate}%</strong>? A resposta não poderá
            ser reenviada.
          </p>
        ) : (
          <Field
            path="taxa_ocupacao"
            schema={{ type: 'number', minimum: 0, maximum: 100 }}
            labelOverride="Taxa de ocupação (%)"
            value={rate}
            error={errors.taxa_ocupacao}
            disabled={operation.busy}
            onChange={(_, value) => {
              setRate(value)
              setErrors({})
            }}
          />
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
          <button className="button button-primary" disabled={operation.busy}>
            {operation.busy ? 'Enviando…' : confirm ? 'Confirmar e enviar' : 'Continuar'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
export default function HotelHome({ api, initialData = null }) {
  const resource = useResource(
      async (options) => {
        const [pending, history] = await Promise.all([
          api.pendingSurveys(options),
          api.responseHistory(options),
        ])
        return { pending: pending.data, history: history.data }
      },
      [api],
      initialData,
    ),
    [selected, setSelected] = useState(''),
    [answering, setAnswering] = useState(null)
  return (
    <>
      <ResourceState resource={resource} />
      {resource.data && (
        <>
          <section className="form-card hotel-pending">
            <h1>Pesquisa de Ocupação Pendente</h1>
            {resource.data.pending.length ? (
              <div className="pending-controls">
                <label className="sr-only" htmlFor="pending-period">
                  Pesquisa / período
                </label>
                <select
                  id="pending-period"
                  value={selected}
                  onChange={(event) => setSelected(event.target.value)}
                >
                  <option value="">Selecione uma pesquisa</option>
                  {resource.data.pending.map((survey) => (
                    <option key={survey.id_pesquisa} value={survey.id_pesquisa}>
                      {survey.titulo} · {survey.periodo_inicio} a {survey.periodo_fim}
                    </option>
                  ))}
                </select>
                <button
                  className="button button-primary"
                  disabled={!selected}
                  onClick={() =>
                    setAnswering(resource.data.pending.find((row) => row.id_pesquisa === selected))
                  }
                >
                  Enviar Resposta
                </button>
              </div>
            ) : (
              <p className="muted">Você não tem pesquisas pendentes.</p>
            )}
          </section>
          <section className="form-card">
            <h2>Minhas respostas</h2>
            {resource.data.history.length ? (
              <ul className="response-list">
                {resource.data.history.map((row) => (
                  <li key={row.id_resposta}>
                    <span>{new Date(row.enviada_em).toLocaleDateString('pt-BR')}</span>
                    <strong>{row.dados.taxa_ocupacao}%</strong>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">Nenhuma resposta enviada.</p>
            )}
          </section>
          {answering && (
            <AnswerDialog
              survey={answering}
              api={api}
              onClose={() => setAnswering(null)}
              onSaved={() => {
                setSelected('')
                resource.reload()
              }}
            />
          )}
        </>
      )}
    </>
  )
}
