import React, { useState } from 'react'
import Modal from './Modal.jsx'
import { Field } from './FormFields.jsx'
import { OperationFeedback } from './OperationsUI.jsx'
import { useOperation } from '../hooks/operations.js'
import { validateAccess } from '../domain/operations.js'
export default function PasswordDialog({ api, onClose, onChanged }) {
  const [draft, setDraft] = useState({ senha_atual: '', senha: '', confirmacao: '' })
  const [errors, setErrors] = useState({})
  const operation = useOperation()
  return (
    <Modal title="Alterar Senha de Acesso" onClose={onClose} busy={operation.busy}>
      <form
        noValidate
        aria-busy={operation.busy}
        onSubmit={(event) => {
          event.preventDefault()
          const next = validateAccess(draft, 'change')
          setErrors(next)
          if (Object.keys(next).length) return
          operation.run(
            () => api.changePassword({ senha_atual: draft.senha_atual, senha: draft.senha }),
            onChanged,
          )
        }}
      >
        <OperationFeedback operation={operation} errors={errors} />
        {[
          ['senha_atual', 'Senha atual'],
          ['senha', 'Nova senha'],
          ['confirmacao', 'Repetir Senha'],
        ].map(([path, label]) => (
          <Field
            key={path}
            path={path}
            schema={{ type: 'string', format: 'password', maxLength: 128 }}
            autoComplete={path === 'senha_atual' ? 'current-password' : 'new-password'}
            labelOverride={label}
            value={draft[path]}
            error={errors[path] || operation.error?.fields[path]}
            disabled={operation.busy}
            onChange={(key, value) => {
              setDraft((previous) => ({ ...previous, [key]: value }))
              setErrors({})
              operation.clear()
            }}
          />
        ))}
        <p className="file-hint">
          Use entre 8 e 128 caracteres. Após salvar, entre novamente. Suas outras sessões também
          serão encerradas.
        </p>
        <div className="form-actions">
          <button
            className="button button-secondary"
            type="button"
            onClick={onClose}
            disabled={operation.busy}
          >
            Cancelar
          </button>
          <button className="button button-primary" disabled={operation.busy}>
            {operation.busy ? 'Salvando…' : 'Alterar senha'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
