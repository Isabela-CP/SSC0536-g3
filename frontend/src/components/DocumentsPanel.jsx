import React, { useEffect, useRef, useState } from 'react'
import { schemas, applyApiError } from '../domain/establishment.js'
import { labelFor } from '../domain/labels.js'
import {
  documentPayload,
  validateDocument,
  validateFile,
  documentFormData,
  replacementFormData,
  saveDownload,
  MAX_UPLOAD_BYTES,
} from '../domain/documents.js'
import { Field } from './FormFields.jsx'
import { Feedback, FormErrors } from './Feedback.jsx'

const empty = () => ({ tipo_documento: '', numero: '', data_emissao: '', data_vencimento: '' })
export default function DocumentsPanel({
  establishment,
  api,
  canManage,
  maxBytes = MAX_UPLOAD_BYTES,
  onChange,
  initialBusy = false,
  initialError = '',
}) {
  const [documents, setDocuments] = useState(establishment.documentos || [])
  const [selected, setSelected] = useState(null)
  const [editor, setEditor] = useState(false)
  const [draft, setDraft] = useState(empty)
  const [file, setFile] = useState(null)
  const [fileKey, setFileKey] = useState(0)
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(initialError)
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(initialBusy)
  const pending = useRef(false)
  const editorRef = useRef(null)
  useEffect(() => {
    if (editor) editorRef.current?.querySelector('select,input')?.focus()
  }, [editor, selected])
  useEffect(() => {
    setDocuments(establishment.documentos || [])
  }, [establishment.documentos])
  const id = establishment.id_estabelecimento
  const updateList = (result) => {
    const next = documents.some((doc) => doc.id_documento === result.id_documento)
      ? documents.map((doc) => (doc.id_documento === result.id_documento ? result : doc))
      : [...documents, result]
    setDocuments(next)
    onChange?.(next)
  }
  function start(document = null) {
    setSelected(document)
    setEditor(true)
    setDraft(
      document
        ? {
            tipo_documento: document.tipo_documento,
            numero: document.numero ?? '',
            data_emissao: document.data_emissao ?? '',
            data_vencimento: document.data_vencimento ?? '',
          }
        : empty(),
    )
    setFile(null)
    setFileKey((key) => key + 1)
    setErrors({})
    setMessage('')
    setSuccess('')
  }
  async function operation(action, done) {
    if (pending.current) return
    pending.current = true
    setBusy(true)
    setMessage('')
    setSuccess('')
    try {
      done(await action())
    } catch (error) {
      const feedback = applyApiError(error)
      setMessage(feedback.message)
      setErrors(feedback.fields)
    } finally {
      pending.current = false
      setBusy(false)
    }
  }
  function submit(event) {
    event.preventDefault()
    if (!canManage || pending.current) return
    const payload = documentPayload(draft, selected)
    const next = validateDocument(payload, !!selected)
    if (!selected) {
      const fileError = validateFile(file, maxBytes)
      if (fileError) next.arquivo = fileError
    }
    setErrors(next)
    if (Object.keys(next).length) return
    operation(
      () =>
        selected
          ? api.updateDocument(id, selected.id_documento, payload)
          : api.uploadDocument(id, documentFormData(payload, file)),
      (result) => {
        updateList(result)
        setEditor(false)
        setFile(null)
        setSuccess(
          selected ? 'Documento atualizado com sucesso.' : 'Documento enviado com sucesso.',
        )
      },
    )
  }
  function replace(document, event) {
    const input = event.currentTarget
    const replacement = input.files?.[0]
    if (!replacement) return
    const error = validateFile(replacement, maxBytes)
    if (error) {
      setMessage(error)
      input.value = ''
      return
    }
    operation(
      () => api.replaceDocument(id, document.id_documento, replacementFormData(replacement)),
      (result) => {
        updateList(result)
        setSuccess('Arquivo substituído com sucesso.')
      },
    )
    input.value = ''
  }
  return (
    <section className="form-card document-card" aria-labelledby="documents-title" aria-busy={busy}>
      <header>
        <h2 id="documents-title">Documentos</h2>
        {canManage && (
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={busy}
            onClick={() => start()}
          >
            Adicionar documento
          </button>
        )}
      </header>
      <Feedback message={message} />
      <Feedback kind="success" message={success} />
      {!documents.length && (
        <p className="muted">
          Nenhum documento cadastrado. Os documentos podem ser enviados posteriormente.
        </p>
      )}
      <ul className="document-list">
        {documents.map((document) => (
          <li className="document-row" key={document.id_documento}>
            <div>
              <strong>
                {labelFor(document.tipo_documento)}
                {document.numero ? ` — ${document.numero}` : ''}
              </strong>
              <p>{document.arquivo?.nome_arquivo || 'Arquivo não informado'}</p>
              <p>
                Vencimento:{' '}
                {document.data_vencimento?.split('-').reverse().join('/') || 'Não informado'} ·{' '}
                {labelFor(document.status)}
              </p>
            </div>
            <div className="document-actions">
              <button
                className="button button-secondary button-small"
                type="button"
                disabled={busy}
                onClick={() =>
                  operation(
                    () => api.downloadDocument(id, document.id_documento),
                    (result) => {
                      saveDownload(result, document.arquivo?.nome_arquivo)
                      setSuccess('Download iniciado.')
                    },
                  )
                }
                aria-label={`Baixar ${labelFor(document.tipo_documento)}`}
              >
                Baixar
              </button>
              {canManage && (
                <>
                  <button
                    className="button button-secondary button-small"
                    type="button"
                    disabled={busy}
                    onClick={() => start(document)}
                    aria-label={`Editar metadados de ${labelFor(document.tipo_documento)}`}
                  >
                    Editar
                  </button>
                  <label
                    className={`button button-secondary button-small ${busy ? 'is-disabled' : ''}`}
                  >
                    Substituir arquivo
                    <input
                      className="sr-only"
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                      disabled={busy}
                      aria-label={`Substituir arquivo de ${labelFor(document.tipo_documento)}`}
                      onChange={(event) => replace(document, event)}
                    />
                  </label>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
      {editor && canManage && (
        <form className="document-form" ref={editorRef} onSubmit={submit} noValidate>
          <h3>{selected ? 'Editar documento' : 'Novo documento'}</h3>
          <FormErrors errors={errors} />
          <div className="field-grid">
            {Object.entries(schemas.DocumentoControleCreate.properties).map(([path, schema]) => (
              <Field
                key={path}
                path={path}
                schema={schema}
                value={draft[path]}
                onChange={(key, value) => {
                  setDraft((previous) => ({ ...previous, [key]: value }))
                  setErrors((previous) => {
                    const next = { ...previous }
                    delete next[key]
                    return next
                  })
                }}
                disabled={busy}
                required={schemas.DocumentoControleCreate.required.includes(path)}
                error={errors[path]}
              />
            ))}
          </div>
          {!selected && (
            <div className="file-field">
              <label htmlFor="document-file">Arquivo *</label>
              <input
                id="document-file"
                key={fileKey}
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                disabled={busy}
                aria-required="true"
                aria-invalid={!!errors.arquivo}
                aria-describedby="document-file-hint"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
              />
              <p className="file-hint" id="document-file-hint">
                PDF, JPEG ou PNG. Máximo de {Number((maxBytes / 1024 / 1024).toFixed(2))} MiB.
              </p>
              {errors.arquivo && <p className="field-error">{errors.arquivo}</p>}
            </div>
          )}
          <div className="form-actions">
            <button
              className="button button-secondary"
              type="button"
              disabled={busy}
              onClick={() => setEditor(false)}
            >
              Cancelar
            </button>
            <button className="button button-primary" type="submit" disabled={busy}>
              {busy ? 'Enviando…' : selected ? 'Salvar documento' : 'Enviar documento'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
