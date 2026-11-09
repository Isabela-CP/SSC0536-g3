export function homeFor(user) {
  return '/inicio'
}
export function portalRoute(hash = '', user) {
  const path = hash.replace(/^#/, '').split('?')[0] || homeFor(user)
  if (path === '/perfil') return { kind: 'profile', path }
  if (path === '/contas')
    return { kind: user.perfil === 'ADMINISTRADOR' ? 'accounts' : 'forbidden', path }
  if (path === '/pesquisas')
    return { kind: user.perfil === 'HOTEL' ? 'hotel' : 'surveys', path }
  if (path === '/inicio')
    return {
      kind: user.perfil === 'HOTEL' ? 'hotel' : 'dashboard',
      path,
      title: 'Dashboard OTO',
    }
  if (path === '/auditoria')
    return {
      kind: user.perfil === 'ADMINISTRADOR' ? 'audit' : 'forbidden',
      path,
      title: 'Log de auditoria',
    }
  if (path === '/inventario')
    return {
      kind: user.perfil === 'HOTEL' ? 'forbidden' : 'inventory',
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
  const detail = path.match(/^\/estabelecimentos\/([^/]+)(?:\/(pesquisas))?$/)
  if (detail)
    return {
      kind:
        user.perfil === 'HOTEL' && user.id_estabelecimento !== detail[1]
          ? 'forbidden'
          : detail[2]
            ? 'history'
            : 'detail',
      path,
      id: detail[1],
    }
  const responses = path.match(/^\/pesquisas\/([^/]+)\/respostas$/)
  if (responses)
    return { kind: user.perfil === 'HOTEL' ? 'forbidden' : 'responses', path, id: responses[1] }
  const match = path.match(/^\/estabelecimentos\/([^/]+)\/editar$/)
  if (match)
    return {
      kind:
        user.perfil === 'HOTEL' && user.id_estabelecimento !== match[1]
          ? 'forbidden'
          : 'workspace',
      path,
    }
  return { kind: 'notfound', path }
}
