import React, { useEffect, useRef, useState } from 'react'
import Layout from './components/Layout.jsx'
import EstablishmentForm from './pages/EstablishmentForm.jsx'
import DocumentsPanel from './components/DocumentsPanel.jsx'
import StatusDialog from './components/StatusDialog.jsx'
import { Feedback } from './components/Feedback.jsx'
import { permissions, applyApiError } from './domain/establishment.js'
import { resolveRoute } from './domain/routing.js'
import { applicationRuntime } from './services/runtime.js'
import { MAX_UPLOAD_BYTES } from './domain/documents.js'

export default function App({ api: providedApi, initialUser, initialEstablishment, initialCategories = [], initialMode = 'create' }) {
  const [state, setState] = useState({ status: initialUser ? 'ready' : 'loading', user: initialUser, item: initialEstablishment, categories: initialCategories, mode: initialMode, api: providedApi })
  const [location, setLocation] = useState(() => globalThis.window?.location.hash || '')
  const [dialog, setDialog] = useState(false)
  const [notice, setNotice] = useState('')
  const mounted = useRef(true)
  useEffect(() => { const update = () => { setLocation(window.location.hash); setNotice(''); setDialog(false) }; window.addEventListener('hashchange', update); return () => window.removeEventListener('hashchange', update) }, [])
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    mounted.current = true
    async function load() {
      setState(previous => ({ ...previous, status: 'loading', error: null }))
      try {
        const runtime = providedApi ? { api: providedApi, mock: false } : await applicationRuntime()
        const user = initialUser || await runtime.api.profile({ signal: controller.signal })
        if (active) setState(previous => ({ ...previous, user }))
        const route = resolveRoute(location, user)
        const [categories, item] = await Promise.all([runtime.api.categories({ signal: controller.signal }), route.id ? runtime.api.establishment(route.id, { signal: controller.signal }) : null])
        if (active) setState({ status: 'ready', user, item, categories: categories.data, mode: route.mode, api: runtime.api, mock: runtime.mock })
      } catch (error) { if (active && error.name !== 'AbortError') setState(previous => ({ ...previous, status: 'error', error: applyApiError(error).message })) }
    }
    load()
    return () => { active = false; mounted.current = false; controller.abort() }
  }, [location, providedApi, initialUser])
  function navigate(path) { window.location.hash = path }
  function saved(item, message) {
    if (!mounted.current) return
    setState(previous => ({ ...previous, item, mode: 'edit' }))
    setNotice(message)
    if (state.mode === 'create') window.history.replaceState(null, '', `#/estabelecimentos/${item.id_estabelecimento}/editar`)
  }
  const { item, user, categories, api, mode } = state
  const access = permissions(user, item)
  const configuredMax = Number(import.meta.env.VITE_UPLOAD_MAX_BYTES)
  const maxBytes = Number.isFinite(configuredMax) && configuredMax > 0 ? configuredMax : MAX_UPLOAD_BYTES
  return <Layout user={user} onNavigate={navigate}>
    {state.status === 'loading' ? <div className="loading-card" role="status">Carregando dados da hospedagem…</div> : state.status === 'error' ? <><h1>Cadastro de hospedagem</h1><Feedback message={state.error} /><button className="button button-secondary" type="button" onClick={() => window.location.reload()}>Tentar novamente</button></> : <>
      <div inert={dialog ? true : undefined}>
        <header className="page-heading"><h1>{mode === 'create' ? 'Cadastro base do CNPJ' : user?.perfil === 'HOTEL' ? 'Meus dados' : access.edit ? 'Editar dados' : 'Dados da hospedagem'}</h1>{item && <span className={`status-badge ${item.status === 'INATIVO' ? 'inactive' : ''}`}>{item.status === 'ATIVO' ? 'Ativo' : 'Inativo'}</span>}</header>
        {state.mock && <Feedback kind="info" message="Ambiente de demonstração. As alterações são temporárias." />}
        <Feedback kind="success" message={notice} />
        <EstablishmentForm key={`${mode}:${item?.id_estabelecimento || 'new'}`} mode={mode} establishment={item} user={user} categories={categories} api={api} onSaved={result => saved(result, mode === 'create' ? 'Hospedagem cadastrada com sucesso.' : 'Dados salvos com sucesso.')} onCancel={() => setNotice('Alterações descartadas.')} />
        {item && <><DocumentsPanel key={item.id_estabelecimento} establishment={item} api={api} canManage={access.documents} maxBytes={maxBytes} onChange={documents => setState(previous => ({ ...previous, item: { ...previous.item, documentos: documents } }))} />{access.status && <div className="maintenance-actions"><button className="button button-secondary" type="button" onClick={() => setDialog(true)}>{item.status === 'ATIVO' ? 'Inativar hospedagem' : 'Reativar hospedagem'}</button></div>}</>}
      </div>
      {dialog && item && access.status && <StatusDialog establishment={item} api={api} onClose={() => setDialog(false)} onSaved={result => saved(result, result.status === 'ATIVO' ? 'Hospedagem reativada com sucesso.' : 'Hospedagem inativada com sucesso.')} />}
    </>}
  </Layout>
}
