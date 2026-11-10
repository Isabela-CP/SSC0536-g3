import { createHttpClient, createInventoryApi } from './http.js'
import { createSession } from './session.js'
let runtime
export function applicationRuntime() {
  runtime ??= (async () => {
    // Mocks são opt-in; erros de autenticação da API nunca ativam fallback.
    const mock = import.meta.env.VITE_API_MODE === 'mock'
    const session = createSession(globalThis.sessionStorage)
    const options = {
      baseUrl: import.meta.env.VITE_API_BASE_URL || '/api',
      getToken: () => session.token(),
      requireSession: !mock,
      onUnauthorized: () => {
        session.clear()
        globalThis.dispatchEvent?.(new Event('oto:unauthorized'))
      },
    }
    if (mock) {
      const { createMockFetch, mockUser } = await import('./mock.js')
      options.fetchImpl = createMockFetch(
        mockUser(import.meta.env.VITE_MOCK_ROLE || 'ADMINISTRADOR'),
      )
    }
    return { api: createInventoryApi(createHttpClient(options)), mock, session }
  })()
  return runtime
}
