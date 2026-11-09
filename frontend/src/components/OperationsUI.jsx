import React from 'react'
import Modal from './Modal.jsx'
import { Feedback, FormErrors } from './Feedback.jsx'
import { useOperation } from '../hooks/operations.js'
export function OperationFeedback({ operation, errors = {} }) {
  return (
    <>
      <Feedback message={operation.error?.message} />
      <Feedback kind="success" message={operation.message} />
      <FormErrors errors={{ ...operation.error?.fields, ...errors }} />
    </>
  )
}
export function ResourceState({ resource }) {
  return resource.loading ? (
    <p role="status" className="muted">
      Carregando…
    </p>
  ) : resource.error ? (
    <>
      <Feedback message={resource.error} />
      <button className="button button-secondary" onClick={resource.reload}>
        Tentar novamente
      </button>
    </>
  ) : null
}
export function ConfirmAction({ title, children, action, onClose, onDone, label = 'Confirmar' }) {
  const operation = useOperation()
  return (
    <Modal title={title} onClose={onClose} busy={operation.busy}>
      <OperationFeedback operation={operation} />
      {children}
      <div className="form-actions">
        <button className="button button-secondary" onClick={onClose} disabled={operation.busy}>
          Cancelar
        </button>
        <button
          className="button button-primary"
          disabled={operation.busy}
          onClick={() =>
            operation.run(action, (result) => {
              onDone?.(result)
              onClose()
            })
          }
        >
          {operation.busy ? 'Salvando…' : label}
        </button>
      </div>
    </Modal>
  )
}
