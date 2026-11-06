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
} = {}) {
  return async function request(path, { body, responseType = 'json', ...options } = {}) {
    const headers = new Headers(options.headers)
    headers.set('Accept', responseType === 'blob' ? 'application/octet-stream' : 'application/json')
    const token = getToken()
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
    profile: (options) => request('/perfil', options),
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
