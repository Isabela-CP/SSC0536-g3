import React, { useState } from 'react'
import { Field } from '../components/FormFields.jsx'
import { OperationFeedback } from '../components/OperationsUI.jsx'
import { useOperation } from '../hooks/operations.js'
import { profilePayload, validateProfile, roles } from '../domain/operations.js'
import { readPreferences, savePreferences, applyPreferences } from '../services/preferences.js'
export default function ProfilePage({ user, api, onUpdated }) {
  const [draft, setDraft] = useState({ nome: user.nome, email: user.email }),
    [errors, setErrors] = useState({}),
    [preferences, setPreferences] = useState(() => readPreferences(globalThis.localStorage, user)),
    operation = useOperation()
  const change = (path, value) => {
    setDraft((previous) => ({ ...previous, [path]: value }))
    setErrors({})
    operation.clear()
  }
  function submit(event) {
    event.preventDefault()
    const next = validateProfile(draft)
    setErrors(next)
    if (Object.keys(next).length) return
    const payload = profilePayload(draft, user)
    if (!Object.keys(payload).length) {
      operation.success('Nenhuma alteração para salvar.')
      return
    }
    operation.run(
      () => api.updateProfile(payload),
      (result) => {
        onUpdated(result)
        operation.success('Dados atualizados com sucesso.')
      },
    )
  }
  function preference(next) {
    try {
      savePreferences(globalThis.localStorage, user, next)
      setPreferences(next)
      applyPreferences(next)
      operation.success('Preferências salvas neste navegador.')
    } catch {
      setErrors({ preferencias: 'Não foi possível salvar as preferências.' })
    }
  }
  return (
    <>
      <header className="page-heading">
        <h1>Meus Dados</h1>
      </header>
      <section className="form-card profile-card">
        <div className="profile-avatar" aria-hidden="true">
          {user.nome
            ?.split(' ')
            .map((part) => part[0])
            .slice(0, 2)
            .join('')}
        </div>
        <p className="avatar-caption">Foto de Perfil</p>
        <OperationFeedback operation={operation} errors={errors} />
        <form onSubmit={submit} noValidate>
          <Field
            path="nome"
            schema={{ type: 'string' }}
            labelOverride="Nome Completo"
            value={draft.nome}
            onChange={change}
            error={errors.nome || operation.error?.fields.nome}
            disabled={operation.busy}
          />
          <Field
            path="email"
            schema={{ type: 'string', format: 'email' }}
            labelOverride="E-mail Institucional"
            value={draft.email}
            onChange={change}
            error={errors.email || operation.error?.fields.email}
            disabled={operation.busy}
          />
          <Field
            path="perfil"
            schema={{ type: 'string' }}
            labelOverride="Cargo"
            value={roles[user.perfil] || user.perfil}
            disabled
            onChange={() => {}}
          />
          <div className="form-actions">
            <button className="button button-primary" disabled={operation.busy}>
              {operation.busy ? 'Salvando…' : 'Salvar dados'}
            </button>
          </div>
        </form>
        <h2>Segurança</h2>
        <button
          className="button button-secondary button-small"
          disabled={operation.busy}
          onClick={() =>
            operation.run(
              () => api.recover({ email: user.email }),
              () => operation.success('Solicitação de recuperação recebida.'),
            )
          }
        >
          Solicitar recuperação de senha
        </button>
        <p className="file-hint">A troca direta de senha ainda não está disponível.</p>
        <h2>Preferências</h2>
        <div className="preference-groups">
          <fieldset>
            <legend>Tamanho da Fonte</legend>
            {[
              ['normal', 'A'],
              ['large', 'A+'],
              ['larger', 'A++'],
            ].map(([value, label]) => (
              <button
                className="button button-secondary button-small"
                key={value}
                aria-pressed={preferences.font === value}
                onClick={() => preference({ ...preferences, font: value })}
              >
                {label}
              </button>
            ))}
          </fieldset>
          <fieldset>
            <legend>Tema</legend>
            {[
              ['light', 'Claro'],
              ['dark', 'Escuro'],
            ].map(([value, label]) => (
              <button
                className="button button-secondary button-small"
                key={value}
                aria-pressed={preferences.theme === value}
                onClick={() => preference({ ...preferences, theme: value })}
              >
                {label}
              </button>
            ))}
          </fieldset>
        </div>
      </section>
    </>
  )
}
