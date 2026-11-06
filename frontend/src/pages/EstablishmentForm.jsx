import React, { useRef, useState } from 'react'
import { BASIC_FIELDS, CONTACT_FIELDS, CADASTUR_FIELDS, SECTION_FIELDS, schemas, draftFrom, emptyDraft, buildPayload, validateEstablishment, permissions, applyApiError, hostingCategories } from '../domain/establishment.js'
import { labelFor } from '../domain/labels.js'
import { Field, RootFields, SchemaFields } from '../components/FormFields.jsx'
import { Feedback, FormErrors } from '../components/Feedback.jsx'

export default function EstablishmentForm({ mode = 'create', establishment, user, categories = [], api, onSaved, onCancel, onEditing, initialErrors = {}, initialStatus = 'idle' }) {
  const [draft, setDraft] = useState(() => mode === 'create' ? emptyDraft() : draftFrom(establishment || {}))
  const [dirty, setDirty] = useState([])
  const [errors, setErrors] = useState(initialErrors)
  const [status, setStatus] = useState(initialStatus)
  const [message, setMessage] = useState('')
  const submitting = useRef(false)
  const access = permissions(user, establishment)
  const allowed = mode === 'create' ? access.create : access.edit
  const busy = status === 'submitting'
  const change = (path, value) => {
    onEditing?.()
    setDraft(previous => ({ ...previous, [path]: value }))
    setDirty(previous => previous.includes(path) ? previous : [...previous, path])
    setErrors(previous => { const next = { ...previous }; delete next[path]; return next })
    if (status !== 'idle') { setStatus('idle'); setMessage('') }
  }
  async function submit(event) {
    event.preventDefault()
    if (submitting.current || !allowed) return
    let payload
    try { payload = buildPayload(draft, { mode, dirty, user, establishment }) }
    catch (error) { setMessage(error.message); setStatus('error'); return }
    const nextErrors = validateEstablishment(payload, mode)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) { setStatus('error'); requestAnimationFrame(() => document.querySelector('[data-error-summary]')?.focus()); return }
    submitting.current = true
    setStatus('submitting'); setMessage('')
    try {
      const result = mode === 'create' ? await api.create(payload) : await api.update(establishment.id_estabelecimento, payload)
      setDirty([]); setDraft(draftFrom(result)); setStatus('success'); setMessage(mode === 'create' ? 'Hospedagem cadastrada com sucesso.' : 'Dados salvos com sucesso.')
      onSaved?.(result)
    } catch (error) {
      const feedback = applyApiError(error)
      setErrors(feedback.fields); setMessage(feedback.message); setStatus('error')
    } finally { submitting.current = false }
  }
  const quickPaths = ['infraestrutura.piscina_adulto', 'acessibilidade.possui_facilidade_pcd', 'infraestrutura.estacionamento', 'infraestrutura.recreacao.nao_possui']
  const shared = { draft, errors, onChange: change, disabled: busy || !allowed, protectedDisabled: !access.protected, categories: hostingCategories(categories), mode }
  return <form className="establishment-form" onSubmit={submit} noValidate aria-busy={busy}>
    <Feedback kind={status === 'success' ? 'success' : 'error'} message={message} />
    <FormErrors errors={errors} />
    {!allowed && <Feedback kind="info" message="Seu perfil tem acesso somente à consulta desta ficha." />}
    <section className="form-card" aria-labelledby="basic-title"><h2 id="basic-title">{mode === 'create' ? 'Identificação' : 'Dados Básicos - OTO'}</h2><RootFields {...shared} fields={BASIC_FIELDS} compact /></section>
    {mode === 'edit' && <section className="form-card" aria-labelledby="operational-title"><h2 id="operational-title">Dados Operacionais - Hotel</h2>{!establishment?.meio_hospedagem && <p className="muted">Aguardando preenchimento do hotel</p>}<SchemaFields schema={{ type: 'object', properties: { total_uh: schemas.MeioHospedagem.properties.total_uh, total_leitos: schemas.MeioHospedagem.properties.total_leitos } }} prefix="meio_hospedagem" {...shared} /><div className="quick-checks"><Field path="infraestrutura.piscina_adulto" schema={schemas.InfraestruturaHospedagem.properties.piscina_adulto} value={draft['infraestrutura.piscina_adulto']} labelOverride="Piscina" onChange={change} disabled={busy || !allowed} /><Field path="acessibilidade.possui_facilidade_pcd" schema={schemas.AcessibilidadeDetalhada.properties.possui_facilidade_pcd} value={draft['acessibilidade.possui_facilidade_pcd']} labelOverride="Acessibilidade" onChange={change} disabled={busy || !allowed} /><Field path="infraestrutura.estacionamento" schema={schemas.InfraestruturaHospedagem.properties.estacionamento} value={draft['infraestrutura.estacionamento']} onChange={change} disabled={busy || !allowed} /><Field path="infraestrutura.recreacao.nao_possui" schema={{ type: ['boolean', 'null'] }} value={draft['infraestrutura.recreacao.nao_possui'] == null ? null : !draft['infraestrutura.recreacao.nao_possui']} labelOverride="Área de Lazer" onChange={(path, value) => change(path, value == null ? null : !value)} disabled={busy || !allowed} /></div><details className="subgroup"><summary>Mais dados operacionais</summary><SchemaFields schema={{ ...schemas.MeioHospedagem, properties: Object.fromEntries(Object.entries(schemas.MeioHospedagem.properties).filter(([key]) => !['total_uh', 'total_leitos'].includes(key))) }} prefix="meio_hospedagem" {...shared} /></details></section>}
    <section className="form-card" aria-labelledby="expiration-title"><h2 id="expiration-title">Vencimentos</h2><RootFields {...shared} fields={['vencimento_cadastur']} compact /><details className="subgroup"><summary>Dados do Cadastur</summary><RootFields {...shared} fields={CADASTUR_FIELDS.filter(field => field !== 'vencimento_cadastur')} /></details></section>
    <details className="form-card expandable-card"><summary>Contatos e informações complementares</summary><RootFields {...shared} fields={CONTACT_FIELDS} /></details>
    {(mode === 'create' ? SECTION_FIELDS : SECTION_FIELDS.filter(field => field !== 'meio_hospedagem')).map(field => <details className="form-card expandable-card" key={field}><summary>{labelFor(field)}{mode === 'create' && <span className="optional">Opcional</span>}</summary><SchemaFields schema={schemas.EstabelecimentoCreate.properties[field]} prefix={field} {...shared} exclude={mode === 'edit' ? quickPaths : []} /></details>)}
    {allowed && <div className="form-actions"><button className="button button-secondary" type="button" disabled={busy} onClick={() => { setDraft(mode === 'create' ? emptyDraft() : draftFrom(establishment)); setErrors({}); setDirty([]); setStatus('idle'); setMessage(''); onCancel?.() }}>Cancelar</button><button className="button button-primary" type="submit" disabled={busy}>{busy ? 'Salvando…' : user?.perfil === 'HOTEL' ? 'Salvar Meus Dados' : 'Salvar'}</button></div>}
  </form>
}
