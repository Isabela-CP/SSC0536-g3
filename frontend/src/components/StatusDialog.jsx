import React, { useRef, useState } from 'react'
import Modal from './Modal.jsx'
import { Feedback } from './Feedback.jsx'
import { validateReason, applyApiError } from '../domain/establishment.js'
export default function StatusDialog({ establishment, api, onClose, onSaved }) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [fieldError, setFieldError] = useState('')
  const [busy, setBusy] = useState(false)
  const pending = useRef(false)
  const active = establishment.status === 'ATIVO'
  async function submit(event) {
    event.preventDefault()
    if (pending.current) return
    if (active) {
      const errors = validateReason(reason)
      if (errors.motivo_inativacao) {
        setFieldError(errors.motivo_inativacao)
        return
      }
    }
    pending.current = true
    setBusy(true)
    setError('')
    try {
      const result = active
        ? await api.inactivate(establishment.id_estabelecimento, reason)
        : await api.reactivate(establishment.id_estabelecimento)
      onSaved(result)
      onClose()
    } catch (error) {
      const feedback = applyApiError(error)
      setError(feedback.message)
      setFieldError(feedback.fields.motivo_inativacao || '')
    } finally {
      pending.current = false
      setBusy(false)
    }
  }
  return (
    <Modal
      title={`${active ? 'Inativar' : 'Reativar'} ${establishment.nome_fantasia}`}
      onClose={onClose}
      busy={busy}
    >
      <form onSubmit={submit} noValidate>
        <Feedback message={error} />
        <p>
          <strong>Status Atual:</strong>{' '}
          <span className={`status-badge ${active ? '' : 'inactive'}`}>
            {active ? 'Ativo' : 'Inativo'}
          </span>
        </p>
        {active ? (
          <>
            <label htmlFor="inactivation-reason">
              Justificativa de Remoção{' '}
              <span className="sr-only">(motivo obrigatório, de 3 a 500 caracteres)</span>
            </label>
            <textarea
              id="inactivation-reason"
              name="motivo_inativacao"
              minLength={3}
              maxLength={500}
              value={reason}
              disabled={busy}
              aria-required="true"
              aria-invalid={!!fieldError}
              aria-describedby={fieldError ? 'reason-error' : 'reason-hint'}
              onChange={(event) => {
                setReason(event.target.value)
                setFieldError('')
              }}
            />
            <p className="file-hint" id="reason-hint">
              A inativação preserva os dados da hospedagem. Informe um motivo de 3 a 500 caracteres.
            </p>
            {fieldError && (
              <p className="field-error" id="reason-error" role="alert">
                {fieldError}
              </p>
            )}
          </>
        ) : (
          <p>Confirma a reativação desta hospedagem? O histórico de alterações será preservado.</p>
        )}
        <div className="form-actions">
          <button
            className="button button-secondary"
            type="button"
            disabled={busy}
            onClick={onClose}
          >
            Cancelar
          </button>
          <button className="button button-primary" type="submit" disabled={busy}>
            {busy ? 'Salvando…' : active ? 'Inativar' : 'Reativar'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
