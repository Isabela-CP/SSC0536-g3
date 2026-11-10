/** Configuração exclusiva do servidor Vite; nunca importada pelo cliente. */
export function backendProxy(env = {}) {
  const token = env.OTO_DEV_BEARER_TOKEN?.trim()
  return {
    target: env.OTO_API_TARGET || 'http://127.0.0.1:8000',
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api(?=\/|$)/, ''),
    ...(token
      ? {
          configure(proxy) {
            proxy.on('proxyReq', (request, incoming) => {
              // Uma sessão real do usuário sempre tem prioridade sobre a conta local.
              if (!incoming.headers.authorization) {
                request.setHeader('Authorization', `Bearer ${token}`)
              }
            })
          },
        }
      : {}),
  }
}
