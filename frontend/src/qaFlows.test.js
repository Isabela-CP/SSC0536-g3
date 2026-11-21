import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { testServer } from './testSupport.js'
import { createHttpClient, createInventoryApi } from './services/http.js'

let server, mocks, files, reports, reading, mockReading, seed, HotelHome, EstablishmentForm
before(async () => {
  server = await testServer()
  mocks = await server.ssrLoadModule('/src/services/mock.js')
  files = await server.ssrLoadModule('/src/services/inventoryFiles.js')
  reports = await server.ssrLoadModule('/src/services/reports.js')
  reading = await server.ssrLoadModule('/src/services/reading.js')
  mockReading = await server.ssrLoadModule('/src/services/mockReading.js')
  seed = (await server.ssrLoadModule('/../contratos_api_oto/mocks/seed-data.json')).default
  HotelHome = (await server.ssrLoadModule('/src/pages/HotelHome.jsx')).default
  EstablishmentForm = (await server.ssrLoadModule('/src/pages/EstablishmentForm.jsx')).default
})
after(async () => server?.close())
const apiFor = (role) => createInventoryApi(createHttpClient({
  fetchImpl: mocks.createMockFetch(mocks.mockUser(role), { preview: true }),
}), { preview: true })
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props))

test('cadastro mock apresenta as sete categorias e valida situação Cadastur sem quebrar o contrato legado', async () => {
  const api = apiFor()
  const { data: categories } = await api.categories()
  assert.deepEqual(categories.map((item) => item.nome_categoria), [
    'HOTEL', 'POUSADA', 'RESORT', 'HOTEL FAZENDA', 'HOSTEL', 'FLAT', 'ACAMPAMENTO TURÍSTICO',
  ])
  const admin = mocks.mockUser()
  const item = await api.establishment(seed.estabelecimentos[0].id_estabelecimento)
  const markup = render(EstablishmentForm, { api, user: admin, categories, establishment: item, mode: 'edit' })
  assert.match(markup, /Próximo vencimento \(90 dias/)
  assert.match(markup, /EM ALERTA \(30 dias/)
  assert.doesNotMatch(markup, /value="OBRIGATORIO"/)
  await assert.rejects(api.update(item.id_estabelecimento, { cadastur_status: 'OBRIGATORIO' }), { status: 422 })
  assert.equal((await api.update(item.id_estabelecimento, { cadastur_status: 'REGULAR' })).cadastur_status, 'REGULAR')
})

test('mínimo de leitos combina categoria, status e paginação antes de montar o mapa', async () => {
  const api = apiFor('GESTOR')
  const data = await reading.loadInventory(api, { leitos_min: '50', status: 'ATIVO', page: 1, page_size: 1 })
  assert.ok(data.markers.length > 0)
  assert.equal(data.data.length, 1)
  assert.equal(data.pagination.total, data.markers.length)
  for (const row of data.markers) assert.ok(row.meio_hospedagem.total_leitos >= 50 && row.status === 'ATIVO')
  await assert.rejects(api.establishments({ leitos_min: -1 }), { status: 422 })
  const empty = await reading.loadInventory(api, { leitos_min: '50', id_categoria: 101, page: 1, page_size: 1 })
  assert.equal(empty.pagination.total, 0)
})

test('auditoria filtra pelo registro da empresa, não pelo autor, e exige administrador', async () => {
  const admin = apiFor()
  const id = seed.estabelecimentos[0].id_estabelecimento
  const result = await admin.audit({ id_entidade: id, acao: 'UPDATE' })
  assert.ok(result.data.length)
  assert.ok(result.data.every((row) => row.id_entidade === id && row.acao === 'UPDATE'))
  assert.deepEqual((await admin.audit({ id_entidade: 'inexistente' })).data, [])
  await assert.rejects(apiFor('GESTOR').audit({ id_entidade: id }), { status: 403 })
})

test('alteração de perfil exige vínculo válido e administrador, e gera auditoria', async () => {
  const admin = apiFor()
  await assert.rejects(admin.changeRole(1, { perfil: 'GESTOR' }), { status: 409 })
  await assert.rejects(admin.changeRole(2, { perfil: 'HOTEL' }), { status: 422 })
  await assert.rejects(apiFor('EDITOR').changeRole(2, { perfil: 'ADMINISTRADOR' }), { status: 403 })
  const id = seed.estabelecimentos[0].id_estabelecimento
  const hotel = await admin.changeRole(2, { perfil: 'HOTEL', id_estabelecimento: id })
  assert.equal(hotel.id_estabelecimento, id)
  const editor = await admin.changeRole(2, { perfil: 'EDITOR' })
  assert.equal(editor.id_estabelecimento, undefined)
  assert.equal((await admin.audit({ acao: 'USUARIO_PERFIL_ALTERADO' })).data.length, 2)
})

test('HOTEL corrige a resposta aberta mantendo o ID e exibindo zero na interface', async () => {
  const api = apiFor('HOTEL')
  const { data: [original] } = await api.responseHistory()
  const { data: open } = await api.surveys()
  assert.ok(open.some((row) => row.id_pesquisa === original.id_pesquisa))
  await assert.rejects(api.answerSurvey(original.id_pesquisa, { taxa_ocupacao: 101 }), { status: 422 })
  const corrected = await api.answerSurvey(original.id_pesquisa, { taxa_ocupacao: 0 })
  assert.equal(corrected.id_resposta, original.id_resposta)
  const { data: history } = await api.responseHistory()
  assert.equal(history.length, 1)
  assert.equal(history[0].dados.taxa_ocupacao, 0)
  const initialData = { history, pending: [], open }
  assert.match(render(HotelHome, { api, initialData }), /Corrigir resposta/)
  assert.match(render(HotelHome, { api, initialData }), />0%</)
  assert.doesNotMatch(render(HotelHome, { api, initialData: { ...initialData, open: [] } }), /Corrigir resposta/)
  assert.doesNotMatch(render(HotelHome, { api: {}, initialData }), /Corrigir resposta/)
  await assert.rejects(apiFor('GESTOR').answerSurvey(original.id_pesquisa, { taxa_ocupacao: 50 }), { status: 403 })
})

test('relatório vazio não inicia geração; mock rejeita intervalo invertido e cruza categoria com período', async () => {
  const never = { createReport: () => assert.fail('Relatório vazio não deve chamar a API') }
  await assert.rejects(reports.exportReport(never, {}, 0), /Nenhuma resposta/)
  const api = apiFor('GESTOR')
  const filter = { tipo: 'OCUPACAO', formato: 'CSV', periodo_inicio: '2026-10-01',
    periodo_fim: '2026-10-31', id_categoria: 101 }
  await assert.rejects(api.createReport({ ...filter, periodo_fim: '2026-09-01' }), { status: 422 })
  await assert.rejects(api.createReport({ ...filter, id_categoria: 102 }), { status: 409 })
  const { file } = await reports.prepareReport(api, filter)
  const csv = await file.blob.text()
  assert.match(csv, /Ipê Amarelo/)
  assert.doesNotMatch(csv, /Serra Azul/)
})

test('indicador conta cadastros do mês de referência, inclusive registros inativos', () => {
  const items = [
    { id_categoria: 1, criado_em: '2026-11-01T12:00:00Z', status: 'INATIVO' },
    { id_categoria: 1, criado_em: '2026-10-31T12:00:00Z', status: 'ATIVO' },
    { id_categoria: 2, criado_em: '2026-11-02T12:00:00Z', status: 'ATIVO' },
  ]
  assert.equal(mockReading.mockDashboard(items, seed.categorias_estabelecimento, '2026-11-08')
    .indicadores.empresas_cadastradas_no_mes, 1)
})

test('planilha real importa atomicamente e PDF/XLSX têm conteúdo binário válido', async () => {
  const api = apiFor()
  const entry = [1, 'Hotel Novo', 'Hotel Novo Ltda.', '11222333000181', 'Rua de Teste, 25']
  const sheet = async (rows) => new File([await files.tableFile(rows, 'XLSX', 'Teste')], 'inventario.xlsx')
  const invalid = await sheet([files.importColumns, entry, entry])
  await assert.rejects(api.importInventory(invalid), (error) =>
    error.status === 422 && error.details.some((detail) => detail.field === 'Linha 3 · cnpj'))
  assert.equal((await api.establishments({ busca: 'Hotel Novo' })).pagination.total, 0)
  const valid = await sheet([files.importColumns, entry])
  await assert.rejects(apiFor('GESTOR').importInventory(valid), { status: 403 })
  assert.equal((await api.importInventory(valid)).importados, 1)
  assert.equal((await api.establishments({ busca: 'Hotel Novo' })).pagination.total, 1)
  await assert.rejects(api.importInventory(valid), { status: 422 })
  await assert.rejects(api.importInventory(new File(['inválido'], 'corrompido.xlsx')), /Não foi possível ler/)
  const pdf = await files.tableFile([['Nome'], [entry[1]]], 'PDF', 'Boletim do Inventário')
  assert.equal(pdf.type, 'application/pdf')
  assert.match(await pdf.slice(0, 8).text(), /^%PDF-/)
})
