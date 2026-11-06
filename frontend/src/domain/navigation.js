export function homeFor(user) {
  return user.perfil === 'HOTEL'
    ? '/inicio'
    : user.perfil === 'ADMINISTRADOR'
      ? '/estabelecimentos/novo'
      : user.perfil === 'EDITOR'
        ? '/pesquisas'
        : '/perfil'
}
export function portalRoute(hash = '', user) {
  const path = hash.replace(/^#/, '').split('?')[0] || homeFor(user)
  if (path === '/perfil') return { kind: 'profile', path }
  if (path === '/contas')
    return { kind: user.perfil === 'ADMINISTRADOR' ? 'accounts' : 'forbidden', path }
  if (path === '/pesquisas') return { kind: user.perfil === 'HOTEL' ? 'hotel' : 'surveys', path }
  if (path === '/inicio')
    return { kind: user.perfil === 'HOTEL' ? 'hotel' : 'reading', path, title: 'Dashboard OTO' }
  if (path === '/auditoria')
    return {
      kind: user.perfil === 'ADMINISTRADOR' ? 'reading' : 'forbidden',
      path,
      title: 'Log de auditoria',
    }
  if (path === '/inventario')
    return {
      kind: user.perfil === 'HOTEL' ? 'forbidden' : 'reading',
      path,
      title: 'Inventário Hospedagem OTO',
    }
  if (path === '/meu-cadastro')
    return {
      kind: user.perfil === 'HOTEL' && user.id_estabelecimento ? 'workspace' : 'forbidden',
      path,
    }
  if (path === '/estabelecimentos/novo')
    return { kind: user.perfil === 'ADMINISTRADOR' ? 'workspace' : 'forbidden', path }
  const match = path.match(/^\/estabelecimentos\/([^/]+)\/editar$/)
  if (match)
    return {
      kind:
        user.perfil === 'HOTEL' && user.id_estabelecimento !== match[1] ? 'forbidden' : 'workspace',
      path,
    }
  return { kind: 'notfound', path }
}
