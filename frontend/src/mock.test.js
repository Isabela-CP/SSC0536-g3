import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { testServer } from './testSupport.js'
import { createHttpClient, createInventoryApi } from './services/http.js'
let server, createMockFetch, mockUser, docs
before(async () => {
  server = await testServer()
  ;({ createMockFetch, mockUser } = await server.ssrLoadModule('/src/services/mock.js'))
  docs = await server.ssrLoadModule('/src/domain/documents.js')
})
after(async () => { await server?.close() })
const payload = () => ({ id_categoria: 1, nome_fantasia: 'Hotel Novo', razao_social: 'Hotel Novo Ltda.', cnpj: '11222333000181', endereco: 'Rua dos Testes, 123' })
const apiFor = role => createInventoryApi(createHttpClient({ fetchImpl: createMockFetch(mockUser(role)) }))

test('mock reutiliza seed e mantém cadastro, edição e transições na sessão', async () => {
  const api = apiFor()
  const created = await api.create(payload())
  assert.equal(created.status, 'ATIVO')
  assert.deepEqual(created.documentos, [])
  const updated = await api.update(created.id_estabelecimento, { bairro: null, meio_hospedagem: { total_uh: 12 } })
  assert.equal(updated.meio_hospedagem.total_uh, 12)
  assert.equal(updated.nome_fantasia, payload().nome_fantasia)
  assert.equal((await api.inactivate(created.id_estabelecimento, 'Encerramento temporário')).status, 'INATIVO')
  await assert.rejects(api.inactivate(created.id_estabelecimento, 'Outro motivo'), error => error.status === 409)
  assert.equal((await api.reactivate(created.id_estabelecimento)).status, 'ATIVO')
  await assert.rejects(api.reactivate(created.id_estabelecimento), error => error.status === 409)
  await assert.rejects(api.create(payload()), error => error.status === 409)
  await assert.rejects(apiFor().establishment(created.id_estabelecimento), error => error.status === 404)
})
test('mock mantém fluxo multipart, metadados, download e substituição', async () => {
  const api = apiFor()
  const item = await api.create(payload())
  const file = new File(['%PDF-1.4'], 'alvará.pdf', { type: 'application/pdf' })
  const document = await api.uploadDocument(item.id_estabelecimento, docs.documentFormData({ tipo_documento: 'ALVARA', data_vencimento: '2099-01-01' }, file))
  assert.equal(document.arquivo.tamanho_bytes, file.size)
  assert.equal(await (await api.downloadDocument(item.id_estabelecimento, document.id_documento)).blob.text(), '%PDF-1.4')
  const changed = await api.updateDocument(item.id_estabelecimento, document.id_documento, { numero: null, data_vencimento: '2000-01-01' })
  assert.equal(changed.numero, null)
  assert.equal(changed.status, 'VENCIDO')
  await api.replaceDocument(item.id_estabelecimento, document.id_documento, docs.replacementFormData(new File(['novo'], 'novo.pdf', { type: 'application/pdf' })))
  assert.equal(await (await api.downloadDocument(item.id_estabelecimento, document.id_documento)).blob.text(), 'novo')
})
test('mock isola HOTEL e bloqueia GESTOR em escrita', async () => {
  const hotel = apiFor('HOTEL')
  const user = await hotel.profile()
  assert.equal((await hotel.establishment(user.id_estabelecimento)).id_estabelecimento, user.id_estabelecimento)
  await assert.rejects(hotel.establishment('22222222-2222-4222-8222-222222222222'), error => error.status === 403)
  await assert.rejects(hotel.update(user.id_estabelecimento, { cnpj: null }), error => error.status === 403)
  await assert.rejects(hotel.create(payload()), error => error.status === 403)
  await assert.rejects(hotel.inactivate(user.id_estabelecimento, 'Motivo'), error => error.status === 403)
  await assert.rejects(apiFor('GESTOR').update(user.id_estabelecimento, { bairro: 'Novo' }), error => error.status === 403)
})
