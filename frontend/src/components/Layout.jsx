import React from 'react'
import logo from '../assets/oto-logo.png'

export default function Layout({ user, children, onNavigate }) {
  const hotel = user?.perfil === 'HOTEL'
  const items = hotel ? ['Início', 'Meu cadastro', 'Perfil'] : ['Início', 'Inventário', 'Convites', 'Pesquisas', 'Auditoria', 'Perfil']
  return <div className="app-shell"><a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>Ir para o conteúdo</a><aside className="sidebar" aria-label="Navegação principal">
    <div className="brand"><img src={logo} alt="Observatório de Turismo de Olímpia" width="203" height="216" /><p>Observatório de<br />Turismo</p></div>
    <nav><ul>{items.map(label => { const active = label === (hotel ? 'Meu cadastro' : 'Inventário'); return <li key={label}>{active && (hotel || user?.perfil === 'ADMINISTRADOR') ? <a href={hotel ? '#/meu-cadastro' : '#/estabelecimentos/novo'} aria-current="page" onClick={event => { if (onNavigate) { event.preventDefault(); onNavigate(hotel ? '/meu-cadastro' : '/estabelecimentos/novo') } }}>{label}</a> : <span aria-current={active ? 'page' : undefined}>{label}</span>}</li> })}</ul></nav><span className="sidebar-exit" aria-hidden="true">↪ Sair</span>
  </aside><main id="main-content" className="main-content" tabIndex={-1}>{children}</main></div>
}
