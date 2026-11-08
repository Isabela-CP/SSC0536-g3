import DashboardPage from './DashboardPage.jsx'
import InventoryPage from './InventoryPage.jsx'
import EstablishmentDetail from './EstablishmentDetail.jsx'
import AuditPage from './AuditPage.jsx'
import ResearchHistoryPage from './ResearchHistoryPage.jsx'
import React, { useEffect, useState } from 'react'
import { applicationRuntime } from '../services/runtime.js'
import { homeFor, portalRoute } from '../domain/navigation.js'
import { readPreferences, applyPreferences } from '../services/preferences.js'
import AccessPage from './AccessPage.jsx'
import ProfilePage from './ProfilePage.jsx'
import AccountsPage from './AccountsPage.jsx'
import SurveysPage from './SurveysPage.jsx'
import HotelHome from './HotelHome.jsx'
import Layout from '../components/Layout.jsx'
import { Feedback } from '../components/Feedback.jsx'

export default function Application({ Workspace }) {
  const [state, setState] = useState({ loading: true, user: null, runtime: null, error: '' }),
    [hash, setHash] = useState(() => globalThis.window?.location.hash || '')
  const navigate = (path) => {
    window.location.hash = path
  }
  useEffect(() => {
    const update = () => setHash(window.location.hash)
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  useEffect(() => {
    let active = true
    applicationRuntime()
      .then(async (runtime) => {
        let user = null
        if (runtime.session.token()) {
          try {
            user = await runtime.api.profile()
          } catch (error) {
            if (error.status !== 401) throw error
            runtime.session.clear()
          }
        }
        if (active) setState({ loading: false, user, runtime, error: '' })
      })
      .catch((error) => {
        if (active)
          setState((previous) => ({ ...previous, loading: false, error: error.message }))
      })
    return () => {
      active = false
    }
  }, [])
  useEffect(() => {
    if (!state.runtime) return
    const expired = () => {
      state.runtime.session.clear()
      setState((previous) => ({ ...previous, user: null }))
      navigate('/login')
    }
    const check = () => {
      if (state.user && !state.runtime.session.token()) expired()
    }
    window.addEventListener('oto:unauthorized', expired)
    window.addEventListener('focus', check)
    const timer = setInterval(check, 15000)
    return () => {
      window.removeEventListener('oto:unauthorized', expired)
      window.removeEventListener('focus', check)
      clearInterval(timer)
    }
  }, [state.runtime, state.user])
  useEffect(() => {
    applyPreferences(
      state.user
        ? readPreferences(globalThis.localStorage, state.user)
        : { theme: 'light', font: 'normal' },
    )
  }, [state.user])
  if (state.loading)
    return (
      <Layout>
        <div className="loading-card" role="status">
          Carregando dados da hospedagem…
        </div>
      </Layout>
    )
  if (state.error)
    return (
      <main className="access-screen">
        <section className="access-card">
          <Feedback message={state.error} />
          <button className="button button-secondary" onClick={() => window.location.reload()}>
            Tentar novamente
          </button>
        </section>
      </main>
    )
  const { runtime, user } = state,
    path = hash.replace(/^#/, '').split('?')[0],
    publicRoute = ['/login', '/recuperar-senha', '/ativar-convite'].includes(path)
  if (!user || publicRoute) {
    const params = new URLSearchParams(hash.split('?')[1] || '')
    return (
      <AccessPage
        key={path}
        api={runtime.api}
        kind={
          path === '/recuperar-senha'
            ? 'recover'
            : path === '/ativar-convite'
              ? 'activate'
              : 'login'
        }
        invitation={{ id: params.get('id'), token: params.get('token') }}
        onNavigate={navigate}
        onAuthenticated={(result) => {
          runtime.session.save(result)
          setState((previous) => ({ ...previous, user: result.usuario }))
          const route = portalRoute(hash, result.usuario)
          if (publicRoute || ['forbidden', 'notfound'].includes(route.kind))
            navigate(homeFor(result.usuario))
        }}
      />
    )
  }
  const route = portalRoute(hash, user)
  const logout = async () => {
    try {
      await runtime.api.logout()
    } catch {
      /* A saída local também ocorre quando a rede está indisponível. */
    } finally {
      runtime.session.clear()
      setState((previous) => ({ ...previous, user: null }))
      navigate('/login')
    }
  }
  if (route.kind === 'workspace')
    return <Workspace api={runtime.api} initialUser={user} onLogout={logout} />
  let page
  if (route.kind === 'profile')
    page = (
      <ProfilePage
        user={user}
        api={runtime.api}
        onUpdated={(result) => setState((previous) => ({ ...previous, user: result }))}
      />
    )
  else if (route.kind === 'accounts') page = <AccountsPage api={runtime.api} />
  else if (route.kind === 'surveys') page = <SurveysPage api={runtime.api} user={user} />
  else if (route.kind === 'hotel') page = <HotelHome api={runtime.api} />
  else if (route.kind === 'dashboard') page = <DashboardPage api={runtime.api} />
  else if (route.kind === 'inventory') page = <InventoryPage api={runtime.api} user={user} />
  else if (route.kind === 'detail')
    page = <EstablishmentDetail key={route.id} api={runtime.api} user={user} id={route.id} />
  else if (route.kind === 'audit') page = <AuditPage api={runtime.api} user={user} />
  else if (route.kind === 'history' || route.kind === 'responses')
    page = (
      <ResearchHistoryPage
        key={`${route.kind}:${route.id}`}
        api={runtime.api}
        user={user}
        establishmentId={route.kind === 'history' ? route.id : undefined}
        surveyId={route.kind === 'responses' ? route.id : undefined}
      />
    )
  else
    page = (
      <Feedback
        message={
          route.kind === 'forbidden'
            ? 'Seu perfil não pode acessar esta área.'
            : 'Tela não encontrada.'
        }
      />
    )
  return (
    <Layout
      user={user}
      activePath={route.kind === 'responses' ? '/pesquisas' : route.path}
      onNavigate={navigate}
      onLogout={logout}
    >
      {page}
    </Layout>
  )
}
