import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ApiError, createHttpClient, createInventoryApi } from './services/http.js'

test('centraliza URL, Bearer e JSON', async () => {
  let seen
  const client = createHttpClient({ baseUrl: 'http://api.test/', getToken: () => 'token', fetchImpl: async (...args) => { seen = args; return Response.json({ ok: true }) } })
  assert.deepEqual(await client('/estabelecimentos', { method: 'POST', body: { nome: 'Hotel' } }), { ok: true })
  assert.equal(seen[0], 'http://api.test/estabelecimentos')
  assert.equal(seen[1].headers.get('Authorization'), 'Bearer token')
  assert.equal(seen[1].headers.get('Content-Type'), 'application/json')
  assert.equal(seen[1].body, '{"nome":"Hotel"}')
})
test('multipart mantém boundary do navegador e não serializa arquivo em JSON', async () => {
  const form = new FormData()
  form.append('arquivo', new File(['pdf'], 'a.pdf'))
  const request = createHttpClient({ fetchImpl: async (_, options) => {
    assert.equal(options.body, form)
    assert.equal(options.headers.has('Content-Type'), false)
    return Response.json({ ok: true })
  } })
  await request('/arquivo', { method: 'PUT', body: form, headers: { 'Content-Type': 'application/json' } })
})
test('preserva status, código e detalhes do contrato', async () => {
  const request = createHttpClient({ fetchImpl: async () => Response.json({ error: { code: 'CONFLICT', message: 'Duplicado', details: [{ field: 'cnpj', issue: 'Duplicado' }] } }, { status: 409 }) })
  await assert.rejects(request('/estabelecimentos'), error => error instanceof ApiError && error.status === 409 && error.code === 'CONFLICT' && error.details[0].field === 'cnpj')
})
test('falha de rede, erro não JSON e cancelamento', async () => {
  await assert.rejects(createHttpClient({ fetchImpl: async () => { throw new TypeError('network') } })('/perfil'), error => error.status === 0)
  await assert.rejects(createHttpClient({ fetchImpl: async () => new Response('Erro', { status: 503 }) })('/perfil'), error => error.status === 503)
  await assert.rejects(createHttpClient({ fetchImpl: async () => { throw new DOMException('cancelado', 'AbortError') } })('/perfil'), error => error.name === 'AbortError')
})
test('downloads retornam Blob e nome público', async () => {
  const request = createHttpClient({ fetchImpl: async () => new Response('pdf', { headers: { 'Content-Disposition': 'attachment; filename=a.pdf' } }) })
  const result = await request('/arquivo', { responseType: 'blob' })
  assert.equal(await result.blob.text(), 'pdf')
  assert.equal(result.disposition, 'attachment; filename=a.pdf')
})
test('operações usam os métodos e caminhos do contrato', async () => {
  const seen = []
  const api = createInventoryApi(async (...args) => { seen.push(args); return {} })
  await api.create({})
  await api.update('id', { bairro: null })
  await api.inactivate('id', 'Motivo')
  await api.reactivate('id')
  await api.uploadDocument('id', new FormData())
  await api.updateDocument('id', 1, { numero: null })
  await api.downloadDocument('id', 1)
  await api.replaceDocument('id', 1, new FormData())
  assert.deepEqual(seen.map(([url, options]) => [url, options?.method || 'GET']), [
    ['/estabelecimentos', 'POST'], ['/estabelecimentos/id', 'PATCH'], ['/estabelecimentos/id/inativacao', 'POST'], ['/estabelecimentos/id/reativacao', 'POST'], ['/estabelecimentos/id/documentos', 'POST'], ['/estabelecimentos/id/documentos/1', 'PATCH'], ['/estabelecimentos/id/documentos/1/arquivo', 'GET'], ['/estabelecimentos/id/documentos/1/arquivo', 'PUT'],
  ])
})
