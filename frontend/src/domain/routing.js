export function resolveRoute(hash = '', user) {
  const route =
    hash.replace(/^#/, '').split('?')[0] ||
    (user?.perfil === 'HOTEL' ? '/meu-cadastro' : '/estabelecimentos/novo')
  if (route === '/meu-cadastro') {
    if (user?.perfil !== 'HOTEL' || !user.id_estabelecimento)
      throw Object.assign(new Error('Esta conta não possui uma hospedagem vinculada.'), {
        status: 403,
      })
    return { mode: 'edit', id: user.id_estabelecimento }
  }
  if (route === '/estabelecimentos/novo') {
    if (user?.perfil !== 'ADMINISTRADOR')
      throw Object.assign(new Error('Seu perfil não pode cadastrar hospedagens.'), {
        status: 403,
      })
    return { mode: 'create' }
  }
  const match = route.match(/^\/estabelecimentos\/([^/]+)\/editar$/)
  if (!match) throw Object.assign(new Error('Tela não encontrada.'), { status: 404 })
  const id = decodeURIComponent(match[1])
  if (user?.perfil === 'HOTEL' && (!user.id_estabelecimento || user.id_estabelecimento !== id))
    throw Object.assign(new Error('Você só pode acessar sua própria hospedagem.'), {
      status: 403,
    })
  return { mode: 'edit', id }
}
