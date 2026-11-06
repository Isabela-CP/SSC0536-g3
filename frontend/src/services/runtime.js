import { createHttpClient, createInventoryApi } from './http.js'
let runtime
export function applicationRuntime() {
  runtime ??= (async () => {
    // Mocks são opt-in; erros de autenticação da API nunca ativam fallback.
    const mock = import.meta.env.VITE_API_MODE === 'mock'
    const options = { baseUrl: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000', getToken: () => globalThis.sessionStorage?.getItem('oto.accessToken') }
    if (mock) {
      const { createMockFetch, mockUser } = await import('./mock.js')
      options.fetchImpl = createMockFetch(mockUser(import.meta.env.VITE_MOCK_ROLE || 'ADMINISTRADOR'))
    }
    return { api: createInventoryApi(createHttpClient(options)), mock }
  })()
  return runtime
}
