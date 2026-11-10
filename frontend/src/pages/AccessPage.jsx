import React, { useState } from 'react'
import logo from '../assets/oto-logo.png'
import { Field } from '../components/FormFields.jsx'
import { useOperation } from '../hooks/operations.js'
import { OperationFeedback } from '../components/OperationsUI.jsx'
import { validateAccess } from '../domain/operations.js'
export default function AccessPage({
  api,
  kind = 'login',
  invitation,
  onAuthenticated,
  onNavigate,
}) {
  const [draft, setDraft] = useState({ email: '', senha: '', confirmacao: '' }),
    [errors, setErrors] = useState({}),
    [finished, setFinished] = useState(false)
  const operation = useOperation(),
    invalidInvite =
      (kind === 'activate' && (!invitation?.id || !invitation?.token)) ||
      (kind === 'reset' && !invitation?.token)
  const change = (path, value) => {
    setDraft((previous) => ({ ...previous, [path]: value }))
    setErrors({})
    operation.clear()
  }
  function submit(event) {
    event.preventDefault()
    const data = ['activate', 'reset'].includes(kind)
      ? { senha: draft.senha, confirmacao: draft.confirmacao }
      : kind === 'recover'
        ? { email: draft.email }
        : { email: draft.email, senha: draft.senha }
    const next = validateAccess(data, kind)
    setErrors(next)
    if (Object.keys(next).length || invalidInvite) return
    operation.run(
      () =>
        kind === 'reset'
          ? api.resetPassword({ token: invitation.token, senha: draft.senha })
          : kind === 'activate'
            ? api.activate(invitation.id, { token: invitation.token, senha: draft.senha })
            : kind === 'recover'
              ? api.recover({ email: draft.email.trim() })
              : api.login({ email: draft.email.trim(), senha: draft.senha }),
      (result) => {
        if (kind === 'login') onAuthenticated(result)
        else {
          setFinished(true)
          setDraft({ email: '', senha: '', confirmacao: '' })
          operation.success(
            kind === 'reset'
              ? 'Senha redefinida. Entre novamente.'
              : kind === 'activate'
                ? 'Acesso ativado. Entre com seu e-mail e senha.'
                : 'Solicitação recebida.',
          )
        }
      },
    )
  }
  return (
    <main className="access-screen">
      <section className="access-card">
        <img src={logo} width="203" height="216" alt="Observatório de Turismo de Olímpia" />
        <h1>
          {kind === 'reset'
            ? 'Redefinir senha'
            : kind === 'activate'
              ? 'Bem-vindo! Defina sua senha'
              : kind === 'recover'
                ? 'Recuperar acesso'
                : 'Observatório de Turismo'}
        </h1>
        {kind === 'activate' && <p>Para ativar o seu acesso, crie uma senha.</p>}
        <OperationFeedback operation={operation} errors={errors} />
        {invalidInvite && (
          <p role="alert" className="field-error">
            {kind === 'reset'
              ? 'Link de recuperação inválido ou incompleto.'
              : 'Link de ativação inválido ou incompleto.'}
          </p>
        )}
        {!finished && !invalidInvite && (
          <form onSubmit={submit} noValidate aria-busy={operation.busy}>
            {!['activate', 'reset'].includes(kind) && (
              <Field
                path="email"
                schema={{ type: 'string', format: 'email' }}
                value={draft.email}
                labelOverride="E-mail"
                compact
                autoComplete="username"
                onChange={change}
                disabled={operation.busy}
                error={errors.email || operation.error?.fields.email}
              />
            )}{' '}
            {kind !== 'recover' && (
              <Field
                path="senha"
                schema={{ type: 'string', format: 'password' }}
                value={draft.senha}
                error={errors.senha || operation.error?.fields.senha}
                labelOverride="Senha"
                autoComplete={kind === 'login' ? 'current-password' : 'new-password'}
                compact
                onChange={change}
                disabled={operation.busy}
              />
            )}{' '}
            {['activate', 'reset'].includes(kind) && (
              <Field
                path="confirmacao"
                schema={{ type: 'string', format: 'password' }}
                value={draft.confirmacao}
                labelOverride="Repetir Senha"
                autoComplete="new-password"
                compact
                onChange={change}
                disabled={operation.busy}
                error={errors.confirmacao}
              />
            )}
            <button className="button button-primary" disabled={operation.busy}>
              {operation.busy
                ? 'Aguarde…'
                : kind === 'reset'
                  ? 'Redefinir senha'
                  : kind === 'activate'
                    ? 'Salvar senha e ativar acesso'
                    : kind === 'recover'
                      ? 'Solicitar recuperação'
                      : 'Entrar no Sistema'}
            </button>
          </form>
        )}
        {kind === 'login' ? (
          <a
            href="#/recuperar-senha"
            onClick={(event) => {
              event.preventDefault()
              onNavigate('/recuperar-senha')
            }}
          >
            Esqueci minha senha
          </a>
        ) : (
          <a
            href="#/login"
            onClick={(event) => {
              event.preventDefault()
              onNavigate('/login')
            }}
          >
            Voltar ao login
          </a>
        )}
      </section>
    </main>
  )
}
