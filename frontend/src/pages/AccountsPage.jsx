import React, { useState } from 'react'
import { Field } from '../components/FormFields.jsx'
import Modal from '../components/Modal.jsx'
import DataTable from '../components/DataTable.jsx'
import { OperationFeedback, ResourceState, ConfirmAction } from '../components/OperationsUI.jsx'
import { useOperation, useResource } from '../hooks/operations.js'
import {
  roles,
  validateAccount,
  accountPayload,
  createAccountAndInvite,
  loadRecipients,
} from '../domain/operations.js'
export function AccountDialog({
  api,
  recipients,
  onClose,
  onChanged = () => {},
  initialDraft = {},
}) {
  const [draft, setDraft] = useState({
      nome: '',
      email: '',
      perfil: 'GESTOR',
      id_estabelecimento: '',
      ...initialDraft,
    }),
    [errors, setErrors] = useState({}),
    [created, setCreated] = useState(null),
    operation = useOperation()
  function submit(event) {
    event.preventDefault()
    const next = validateAccount(draft)
    setErrors(next)
    if (Object.keys(next).length) return
    operation.run(
      () => createAccountAndInvite(api, accountPayload(draft), created),
      () => {
        onChanged()
        onClose()
      },
      (error) => {
        if (error.account) {
          setCreated(error.account)
          onChanged()
        }
      },
    )
  }
  return (
    <Modal title="Criar Convite" onClose={onClose} busy={operation.busy}>
      <form onSubmit={submit} noValidate>
        <OperationFeedback operation={operation} errors={errors} />
        {created && (
          <p className="muted">
            A conta foi criada. Tente novamente para criar apenas o convite, sem duplicar a
            conta.
          </p>
        )}
        <div className="field-grid">
          {[
            [
              'perfil',
              'Tipo',
              { type: 'string' },
              Object.entries(roles).map(([value, label]) => ({ value, label })),
            ],
            ['nome', 'Nome', { type: 'string' }],
            ['email', 'E-mail', { type: 'string', format: 'email' }],
            ...(draft.perfil === 'HOTEL'
              ? [
                  [
                    'id_estabelecimento',
                    'Hospedagem vinculada',
                    { type: 'string' },
                    recipients.map((item) => ({
                      value: item.id_estabelecimento,
                      label: item.nome_fantasia,
                    })),
                  ],
                ]
              : []),
          ].map(([path, label, schema, options]) => (
            <Field
              key={path}
              path={path}
              schema={schema}
              labelOverride={label}
              options={options}
              value={draft[path]}
              disabled={operation.busy || !!created}
              error={errors[path] || operation.error?.fields[path]}
              onChange={(key, value) => {
                setDraft((previous) => ({ ...previous, [key]: value }))
                setErrors({})
                operation.clear()
              }}
            />
          ))}
        </div>
        <p className="file-hint">
          O convite será colocado na fila de envio. Em desenvolvimento, consulte a caixa de
          e-mail local (Mailpit).
        </p>
        <div className="form-actions">
          <button
            className="button button-secondary"
            type="button"
            disabled={operation.busy}
            onClick={onClose}
          >
            Cancelar
          </button>
          <button className="button button-primary" disabled={operation.busy}>
            {operation.busy
              ? 'Aguarde…'
              : created
                ? 'Tentar convite novamente'
                : 'Criar conta e convite'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
export default function AccountsPage({ api, user: actor, initialData = null }) {
  const resource = useResource(
      async (options) => {
        const [users, recipients] = await Promise.all([
          api.users(options),
          loadRecipients(api, options),
        ])
        return { users: users.data, recipients }
      },
      [api],
      initialData,
    ),
    [dialog, setDialog] = useState(false),
    [changing, setChanging] = useState(null),
    operation = useOperation()
  const columns = [
    { key: 'nome', label: 'Nome' },
    { key: 'email', label: 'E-mail' },
    { key: 'perfil', label: 'Cargo', render: (user) => roles[user.perfil] },
    {
      key: 'ativo',
      label: 'Status',
      render: (user) =>
        user.status === 'INATIVO' ? 'Inativa' : user.ativo ? 'Ativa' : 'Pendente',
    },
    {
      key: 'actions',
      label: 'Ações',
      render: (user) => (
        <div className="document-actions">
          {!user.ativo && user.status !== 'INATIVO' && (
            <button
              className="button button-small button-secondary"
              disabled={operation.busy}
              onClick={() =>
                operation.run(
                  () => api.createInvite({ email: user.email }),
                  () => operation.success('Novo convite criado.'),
                )
              }
            >
              Reenviar convite
            </button>
          )}
          {(user.ativo || user.status === 'INATIVO') && (
            <button
              className="button button-small button-secondary"
              disabled={operation.busy || user.id_usuario === actor?.id_usuario}
              onClick={() => setChanging(user)}
            >
              {user.ativo ? 'Inativar' : 'Reativar'}
            </button>
          )}
        </div>
      ),
    },
  ]
  return (
    <>
      <header className="page-heading">
        <h1>Painel de Convites OTO</h1>
      </header>
      <ResourceState resource={resource} />
      <OperationFeedback operation={operation} />
      {resource.data && (
        <>
          <button className="button button-primary" onClick={() => setDialog(true)}>
            Criar Nova Conta
          </button>
          {[
            ['Equipe Interna', false],
            ['Hospedagens', true],
          ].map(([title, hotel]) => (
            <section className="account-section" key={title}>
              <h2>{title}</h2>
              <DataTable
                columns={columns}
                rows={resource.data.users.filter((user) => (user.perfil === 'HOTEL') === hotel)}
                caption={title}
              />
            </section>
          ))}
          <p className="muted">As contas são inativadas para preservar o histórico.</p>
          {changing && (
            <ConfirmAction
              title={changing.ativo ? 'Inativar conta' : 'Reativar conta'}
              onClose={() => setChanging(null)}
              action={() =>
                changing.ativo
                  ? api.inactivateUser(changing.id_usuario)
                  : api.reactivateUser(changing.id_usuario)
              }
              onDone={resource.reload}
              label={changing.ativo ? 'Inativar' : 'Reativar'}
            >
              <p>
                {changing.nome} — {changing.email}
              </p>
              <p>
                {changing.ativo
                  ? 'A conta perderá acesso e suas sessões serão encerradas. O histórico será preservado.'
                  : 'A conta poderá entrar novamente com a senha já definida.'}
              </p>
            </ConfirmAction>
          )}
          {dialog && (
            <AccountDialog
              api={api}
              recipients={resource.data.recipients}
              onClose={() => setDialog(false)}
              onChanged={resource.reload}
            />
          )}
        </>
      )}
    </>
  )
}
