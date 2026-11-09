export class ApiError extends Error {
  constructor(status, error = {}) {
    super(error.message || 'Não foi possível acessar o serviço. Tente novamente.')
    this.status = status
    this.code = error.code
    this.details = error.details || []
  }
}

export function createHttpClient({
  baseUrl = '',
  getToken = () => null,
  fetchImpl = globalThis.fetch,
  onUnauthorized,
  requireSession = false,
} = {}) {
  return async function request(path, { body, responseType = 'json', ...options } = {}) {
    const headers = new Headers(options.headers)
    headers.set(
      'Accept',
      responseType === 'blob' ? 'application/octet-stream' : 'application/json',
    )
    const token = getToken()
    const publicOperation =
      ['/auth/login', '/auth/recuperacao-senha', '/auth/redefinicao-senha'].includes(path) ||
      /^\/convites\/[^/]+\/aceitacao$/.test(path)
    if (requireSession && !publicOperation && !token) {
      onUnauthorized?.()
      throw new ApiError(401, { code: 'UNAUTHORIZED', message: 'Entre para continuar.' })
    }
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const multipart = body instanceof FormData
    if (body !== undefined && !multipart) headers.set('Content-Type', 'application/json')
    if (multipart) headers.delete('Content-Type')
    let response
    try {
      response = await fetchImpl(`${baseUrl.replace(/\/$/, '')}${path}`, {
        ...options,
        headers,
        body: body === undefined || multipart ? body : JSON.stringify(body),
      })
    } catch (error) {
      if (error.name === 'AbortError') throw error
      throw new ApiError(0)
    }
    if (!response.ok) {
      if (response.status === 401 && !publicOperation) onUnauthorized?.()
      const payload = await response.json().catch(() => ({}))
      throw new ApiError(response.status, payload.error)
    }
    if (response.status === 204) return null
    if (responseType === 'blob')
      return {
        blob: await response.blob(),
        disposition: response.headers.get('Content-Disposition'),
      }
    return response.json()
  }
}

export function createInventoryApi(request) {
  const itemPath = (id) => `/estabelecimentos/${encodeURIComponent(id)}`
  const documentPath = (id, doc) => `${itemPath(id)}/documentos/${encodeURIComponent(doc)}`
  return {
    dashboard: (options) => request('/dashboard', options),
    audit: (params = {}, options = {}) =>
      request(`/auditoria?${new URLSearchParams(params)}`, options),
    profile: (options) => request('/perfil', options),
    login: (payload) => request('/auth/login', { method: 'POST', body: payload }),
    logout: () => request('/auth/logout', { method: 'POST' }),
    recover: (payload) => request('/auth/recuperacao-senha', { method: 'POST', body: payload }),
    activate: (id, payload) =>
      request(`/convites/${encodeURIComponent(id)}/aceitacao`, {
        method: 'POST',
        body: payload,
      }),
    resetPassword: (payload) =>
      request('/auth/redefinicao-senha', { method: 'POST', body: payload }),
    changePassword: (payload) => request('/perfil/senha', { method: 'PUT', body: payload }),
    inactivateUser: (id) =>
      request(`/usuarios/${encodeURIComponent(id)}/inativacao`, { method: 'POST' }),
    reactivateUser: (id) =>
      request(`/usuarios/${encodeURIComponent(id)}/reativacao`, { method: 'POST' }),
    updateProfile: (payload) => request('/perfil', { method: 'PATCH', body: payload }),
    users: (options) => request('/usuarios', options),
    createUser: (payload) => request('/usuarios', { method: 'POST', body: payload }),
    createInvite: (payload) => request('/convites', { method: 'POST', body: payload }),
    establishments: (params = {}, options = {}) =>
      request(`/estabelecimentos?${new URLSearchParams(params)}`, options),
    surveys: (options) => request('/pesquisas-ocupacao', options),
    createSurvey: (payload) =>
      request('/pesquisas-ocupacao', { method: 'POST', body: payload }),
    updateSurvey: (id, payload) =>
      request(`/pesquisas-ocupacao/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        body: payload,
      }),
    closeSurvey: (id) =>
      request(`/pesquisas-ocupacao/${encodeURIComponent(id)}/encerramento`, { method: 'POST' }),
    pendingSurveys: (options) => request('/pesquisas-ocupacao/pendentes', options),
    answerSurvey: (id, payload) =>
      request(`/pesquisas-ocupacao/${encodeURIComponent(id)}/respostas`, {
        method: 'POST',
        body: payload,
      }),
    responseHistory: (options) => request('/respostas-ocupacao/historico', options),
    createReport: (payload) => request('/relatorios', { method: 'POST', body: payload }),
    report: (id) => request(`/relatorios/${encodeURIComponent(id)}`),
    downloadReport: (id) =>
      request(`/relatorios/${encodeURIComponent(id)}/arquivo`, { responseType: 'blob' }),
    categories: (options) => request('/categorias-estabelecimento', options),
    establishment: (id, options) => request(itemPath(id), options),
    documents: (id, options) => request(`${itemPath(id)}/documentos`, options),
    create: (payload) => request('/estabelecimentos', { method: 'POST', body: payload }),
    update: (id, payload) => request(itemPath(id), { method: 'PATCH', body: payload }),
    inactivate: (id, reason) =>
      request(`${itemPath(id)}/inativacao`, {
        method: 'POST',
        body: { motivo_inativacao: reason },
      }),
    reactivate: (id) => request(`${itemPath(id)}/reativacao`, { method: 'POST' }),
    uploadDocument: (id, form) =>
      request(`${itemPath(id)}/documentos`, { method: 'POST', body: form }),
    updateDocument: (id, doc, payload) =>
      request(documentPath(id, doc), { method: 'PATCH', body: payload }),
    downloadDocument: (id, doc) =>
      request(`${documentPath(id, doc)}/arquivo`, { responseType: 'blob' }),
    replaceDocument: (id, doc, form) =>
      request(`${documentPath(id, doc)}/arquivo`, { method: 'PUT', body: form }),
  }
}
