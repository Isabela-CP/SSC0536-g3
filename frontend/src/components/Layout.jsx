import React from 'react'
import logo from '../assets/oto-logo.png'
export default function Layout({ user, children, onNavigate, onLogout, activePath }) {
  const hotel = user?.perfil === 'HOTEL',
    path = activePath || (hotel ? '/meu-cadastro' : '/estabelecimentos/novo')
  const items = hotel
    ? [
        ['Início', '/inicio'],
        ['Meu cadastro', '/meu-cadastro'],
        ['Perfil', '/perfil'],
      ]
    : [
        ['Início', '/inicio'],
        ['Inventário', '/inventario'],
        ...(user?.perfil === 'ADMINISTRADOR' ? [['Convites', '/contas']] : []),
        ['Pesquisas', '/pesquisas'],
        ...(user?.perfil === 'ADMINISTRADOR' ? [['Auditoria', '/auditoria']] : []),
        ['Perfil', '/perfil'],
      ]
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault()
          document.getElementById('main-content')?.focus()
        }}
      >
        Ir para o conteúdo
      </a>
      <aside className="sidebar" aria-label="Navegação principal">
        <div className="brand">
          <img src={logo} alt="Observatório de Turismo de Olímpia" width="203" height="216" />
          <p>
            Observatório de
            <br />
            Turismo
          </p>
        </div>
        <nav>
          <ul>
            {items.map(([label, to]) => {
              const active =
                path === to ||
                (to === '/inventario' && path.startsWith('/estabelecimentos')) ||
                (to === '/pesquisas' && path.startsWith('/pesquisas/'))
              return (
                <li key={to}>
                  <a
                    href={`#${to}`}
                    aria-current={active ? 'page' : undefined}
                    onClick={(event) => {
                      if (onNavigate) {
                        event.preventDefault()
                        onNavigate(to)
                      }
                    }}
                  >
                    {label}
                  </a>
                </li>
              )
            })}
          </ul>
        </nav>
        <button className="sidebar-exit" disabled={!onLogout} onClick={onLogout}>
          ↪ Sair
        </button>
      </aside>
      <main id="main-content" className="main-content" tabIndex={-1}>
        {children}
      </main>
    </div>
  )
}
