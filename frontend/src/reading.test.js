import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { testServer } from './testSupport.js'
let server,
  domain,
  service,
  mocks,
  navigation,
  seed,
  pages = {}
before(async () => {
  server = await testServer()
  domain = await server.ssrLoadModule('/src/domain/reading.js')
  service = await server.ssrLoadModule('/src/services/reading.js')
  mocks = await server.ssrLoadModule('/src/services/mockReading.js')
  navigation = await server.ssrLoadModule('/src/domain/navigation.js')
  seed = (await server.ssrLoadModule('/../contratos_api_oto/mocks/seed-data.json')).default
  for (const name of [
    'DashboardPage',
    'InventoryPage',
    'EstablishmentDetail',
    'AuditPage',
    'ResearchHistoryPage',
  ])
    pages[name] = (await server.ssrLoadModule(`/src/pages/${name}.jsx`)).default
  pages.InventoryMap = (await server.ssrLoadModule('/src/components/InventoryMap.jsx')).default
})
after(async () => {
  await server?.close()
})
const admin = { perfil: 'ADMINISTRADOR' },
  gestor = { perfil: 'GESTOR' }
const render = (name, props) => renderToStaticMarkup(React.createElement(pages[name], props))
const listing = () =>
  mocks.mockInventory(seed.estabelecimentos, admin, new URLSearchParams({ id_categoria: '1' }))
for (const [key, value] of [
  ['busca', 'x'.repeat(121)],
  ['id_categoria', 0],
  ['status', 'EXCLUIDO'],
  ['cadastur_status', 'SIM'],
  ['aceita_pesquisas', 'talvez'],
  ['page', 0],
  ['page_size', 101],
  ['ordenar_por', 'cnpj'],
  ['ordem', 'up'],
])
  test(`consulta valida parâmetro ${key}`, () => {
    assert.ok(domain.inventoryErrors({ ...domain.inventoryDefaults, [key]: value })[key])
  })
test('payload de consulta preserva false e combina todos os parâmetros', () => {
  const draft = {
    ...domain.inventoryDefaults,
    busca: 'Hotel',
    id_categoria: '1',
    status: 'ATIVO',
    cadastur_status: 'OBRIGATORIO',
    aceita_pesquisas: 'false',
    page: 2,
    page_size: 1,
    ordenar_por: 'atualizado_em',
    ordem: 'desc',
  }
  assert.deepEqual(domain.inventoryErrors(draft), {})
  assert.deepEqual(domain.inventoryQuery(draft), { ...draft, id_categoria: 1 })
  assert.equal(Object.hasOwn(domain.inventoryQuery(domain.inventoryDefaults), 'busca'), false)
})
test('mock combina filtros e pagina resultados deterministicamente', () => {
  const query = new URLSearchParams({
    id_categoria: '1',
    status: 'ATIVO',
    aceita_pesquisas: 'true',
    page_size: '1',
    ordem: 'desc',
  })
  const first = mocks.mockInventory(seed.estabelecimentos, admin, query)
  assert.equal(first.data.length, 1)
  assert.ok(first.data[0].status === 'ATIVO' && first.data[0].aceita_pesquisas)
  query.set('page', '2')
  const second = mocks.mockInventory(seed.estabelecimentos, admin, query)
  assert.notEqual(first.data[0].id_estabelecimento, second.data[0].id_estabelecimento)
  query.set('busca', 'sem-correspondencia')
  assert.equal(mocks.mockInventory(seed.estabelecimentos, admin, query).data.length, 0)
})
test('mock busca nome, razão social e CNPJ normalizado e isola HOTEL', () => {
  const item = seed.estabelecimentos[0]
  for (const term of [item.nome_fantasia, item.razao_social, item.cnpj.replace(/\D/g, '')]) {
    const result = mocks.mockInventory(
      seed.estabelecimentos,
      admin,
      new URLSearchParams({ busca: term }),
    )
    assert.equal(result.data[0].id_estabelecimento, item.id_estabelecimento)
  }
  const result = mocks.mockInventory(
    seed.estabelecimentos,
    { perfil: 'HOTEL', id_estabelecimento: item.id_estabelecimento },
    new URLSearchParams(),
  )
  assert.equal(result.pagination.total, 1)
})
test('mapa carrega todas as páginas com os mesmos filtros, não só a primeira', async () => {
  const calls = []
  const api = {
    establishments: async (params) => {
      calls.push(params)
      return {
        data: [{ id_estabelecimento: String(params.page) }],
        pagination: { total_pages: 3 },
      }
    },
  }
  const rows = await domain.allEstablishments(api, { busca: 'Hotel', status: 'ATIVO' })
  assert.equal(rows.length, 3)
  assert.deepEqual(
    calls.map((row) => row.page),
    [1, 2, 3],
  )
  assert.ok(
    calls.every(
      (row) => row.busca === 'Hotel' && row.status === 'ATIVO' && row.page_size === 100,
    ),
  )
  await assert.rejects(
    () =>
      domain.allEstablishments({ establishments: async () => ({ data: [], pagination: {} }) }),
    /Paginação inválida/,
  )
})
test('dashboard rejeita formato incompleto, sem converter alerta AVCB em Cadastur', async () => {
  const api = {
    dashboard: async () => ({
      indicadores: { estabelecimentos_ativos: 1 },
      alertas: [{ mensagem: 'AVCB' }],
    }),
    categories: async () => ({ data: [] }),
  }
  await assert.rejects(() => service.loadDashboard(api), /Indicadores completos/)
})
test('cancelamento e falha HTTP interrompem consultas sem fallback', async () => {
  const error = Object.assign(new Error('Token inválido'), { status: 401 })
  await assert.rejects(
    () =>
      service.loadInventory(
        {
          categories: async () => {
            throw error
          },
        },
        domain.inventoryDefaults,
      ),
    (received) => received === error,
  )
  const controller = new AbortController()
  controller.abort()
  await assert.rejects(
    () =>
      domain.allEstablishments(
        {
          establishments: async (params, options) => {
            assert.ok(options.signal.aborted)
            throw new DOMException('Cancelado', 'AbortError')
          },
        },
        {},
        { signal: controller.signal },
      ),
    { name: 'AbortError' },
  )
})
test('geolocalização aceita zero e rejeita ausentes, strings e coordenadas inválidas', () => {
  assert.ok(domain.hasCoordinates({ latitude: 0, longitude: 0 }))
  for (const point of [
    { latitude: null, longitude: 1 },
    { latitude: '1', longitude: 1 },
    { latitude: 91, longitude: 0 },
    { latitude: 0, longitude: 181 },
  ])
    assert.equal(domain.hasCoordinates(point), false)
  const result = render('InventoryMap', { items: [] })
  assert.match(result, /Nenhuma hospedagem com coordenadas válidas/)
  assert.doesNotMatch(result, /Mapa interativo/)
})
test('dashboard usa todas as fichas e mostra dados faltantes sem inventar valores', () => {
  const source = seed.estabelecimentos.filter((row) => row.id_categoria === 1)
  const body = mocks.mockDashboard(source, seed.categorias_estabelecimento, '2026-11-08')
  assert.equal(body.indicadores.total_empresas, source.length)
  const result = render('DashboardPage', { api: {}, initialData: { ...body, markers: source } })
  assert.match(result, /Dashboard OTO/)
  assert.match(result, /Total Empresas/)
  assert.match(result, /ALERTA DE VENCIMENTOS CADASTUR/)
  assert.doesNotMatch(result, /AVCB vence em breve|>X</)
})
test('inventário respeita ações por perfil e usa paginação do servidor', () => {
  const body = {
    ...listing(),
    categories: seed.categorias_estabelecimento,
    markers: seed.estabelecimentos,
  }
  const result = render('InventoryPage', { api: {}, user: admin, initialData: body })
  assert.match(result, /Cadastrar Estabelecimento/)
  assert.match(result, /Ver detalhes/)
  assert.match(result, /Ver Pesquisas/)
  const readonly = render('InventoryPage', { api: {}, user: gestor, initialData: body })
  assert.doesNotMatch(readonly, /Cadastrar Estabelecimento|>Editar<|>Inativar</)
  const empty = render('InventoryPage', {
    api: {},
    user: gestor,
    initialData: { ...body, data: [] },
  })
  assert.match(empty, /Nenhuma hospedagem encontrada/)
})
test('detalhe apresenta dados aninhados, documentos e valores zero/false, sem escrita GESTOR', () => {
  const item = structuredClone(seed.estabelecimentos[0])
  item.meio_hospedagem.total_leitos = 0
  item.infraestrutura.estacionamento = false
  const result = render('EstablishmentDetail', {
    api: {},
    user: gestor,
    id: item.id_estabelecimento,
    initialData: item,
  })
  assert.match(result, /Infraestrutura/)
  assert.match(result, /Acessibilidade/)
  assert.match(result, /Documentos/)
  assert.match(result, />0</)
  assert.match(result, />Não</)
  assert.doesNotMatch(result, /Editar dados|Adicionar documento|<input/)
})
test('rotas reservam auditoria ao ADMIN e isolam detalhe/histórico HOTEL', () => {
  assert.equal(navigation.portalRoute('#/auditoria', admin).kind, 'audit')
  assert.equal(navigation.portalRoute('#/auditoria', gestor).kind, 'forbidden')
  assert.equal(
    navigation.portalRoute('#/estabelecimentos/other/pesquisas', {
      perfil: 'HOTEL',
      id_estabelecimento: 'own',
    }).kind,
    'forbidden',
  )
  assert.equal(
    navigation.portalRoute('#/estabelecimentos/own', {
      perfil: 'HOTEL',
      id_estabelecimento: 'own',
    }).kind,
    'detail',
  )
  assert.equal(navigation.homeFor(gestor), '/inicio')
})
test('auditoria preserva diferença entre null, false, zero e campo ausente', () => {
  const changes = domain.changes(
    { nested: { flag: false, count: 0, extra: 'valor' } },
    { nested: { flag: null, count: 1 } },
  )
  assert.ok(
    changes.some(
      (row) => row.path === 'nested.flag' && row.before === false && row.after === null,
    ),
  )
  assert.ok(changes.some((row) => row.path === 'nested.count' && row.before === 0))
  assert.ok(changes.some((row) => row.path === 'nested.extra' && row.after === undefined))
  const result = render('AuditPage', {
    api: {},
    user: admin,
    initialData: {
      data: [
        {
          id: '1',
          acao: 'UPDATE',
          usuario: 'Admin',
          criado_em: '2026-11-08T12:00:00Z',
          entidade: 'ESTABELECIMENTO',
          id_entidade: '1',
          antes: { flag: false, count: 0 },
          depois: { flag: null, count: 1 },
        },
      ],
    },
  })
  assert.match(result, />false</)
  assert.match(result, />null</)
  assert.match(result, />0</)
  assert.match(render('AuditPage', { api: {}, user: gestor }), /Seu perfil não pode acessar/)
})
test('filtros de auditoria validam usuário e intervalo e normalizam ISO', () => {
  const query = domain.auditQuery({
    acao: ' UPDATE ',
    id_usuario: '2',
    data_inicio: '2026-11-08T12:00:00Z',
    data_fim: '',
  })
  assert.deepEqual(query, {
    acao: 'UPDATE',
    id_usuario: 2,
    data_inicio: '2026-11-08T12:00:00.000Z',
  })
  assert.throws(() => domain.auditQuery({ id_usuario: 'abc' }), /ID/)
  assert.throws(
    () =>
      domain.auditQuery({ id_usuario: '', data_inicio: '2026-11-09', data_fim: '2026-11-08' }),
    /data final/,
  )
})
test('histórico combina associação do hotel e mostra ocupação zero como resposta', () => {
  const surveys = [
    {
      id_pesquisa: 's',
      titulo: 'Novembro',
      tipo: 'CONSOLIDADO',
      periodo_inicio: '2026-11-01',
      periodo_fim: '2026-11-30',
      status: 'ABERTA',
      estabelecimentos: ['hotel', 'other'],
    },
  ]
  const history = [
    {
      id_pesquisa: 's',
      id_estabelecimento: 'hotel',
      enviada_em: '2026-11-08T12:00:00Z',
      dados: { taxa_ocupacao: 0 },
    },
  ]
  assert.equal(domain.surveyHistory(surveys, history, 'hotel')[0].responseRate, 100)
  assert.equal(domain.surveyHistory(surveys, history)[0].responseRate, 50)
  const result = render('ResearchHistoryPage', {
    api: {},
    establishmentId: 'hotel',
    initialData: { surveys, history, subject: { nome_fantasia: 'Hotel' } },
  })
  assert.match(result, /Perfil: Hotel/)
  assert.match(result, /Histórico de Pesquisas/)
  assert.match(result, /0%/)
})

test('indicadores de pesquisa usam apenas respostas e destinatários do conjunto consultado', () => {
  const rows = [
    {
      status: 'ABERTA',
      estabelecimentos: ['a', 'b'],
      responses: [{ id_estabelecimento: 'a', enviada_em: '2026-11-08T12:00:00Z' }],
    },
  ]
  assert.deepEqual(domain.researchStats(rows, new Date('2026-11-08T12:00:00Z')), {
    active: 1,
    month: 1,
    rate: 50,
  })
  assert.deepEqual(domain.researchStats([], new Date('2026-11-08T12:00:00Z')), {
    active: 0,
    month: 0,
    rate: null,
  })
})
test('sem categoria de hospedagem não consulta outros segmentos turísticos', async () => {
  const result = await service.loadInventory(
    {
      categories: async () => ({
        data: [{ id_categoria: 9, nome_categoria: 'Outro segmento' }],
      }),
      establishments: async () => {
        throw new Error('Não deve chamar')
      },
    },
    domain.inventoryDefaults,
  )
  assert.equal(result.data.length, 0)
  assert.equal(result.markers.length, 0)
})
test('carregamento inicial das telas não apresenta totais fictícios', () => {
  for (const name of [
    'DashboardPage',
    'InventoryPage',
    'EstablishmentDetail',
    'AuditPage',
    'ResearchHistoryPage',
  ]) {
    const result = render(name, { api: {}, user: admin, id: 'missing' })
    assert.match(result, /Carregando/)
    assert.doesNotMatch(result, />X<|Nenhuma hospedagem encontrada/)
  }
})
test('cliente transmite filtros de auditoria nos parâmetros do contrato', async () => {
  const { createInventoryApi } = await server.ssrLoadModule('/src/services/http.js')
  const calls = []
  const api = createInventoryApi(async (path, options) => {
    calls.push({ path, options })
    return {}
  })
  const controller = new AbortController()
  await api.audit(
    { acao: 'UPDATE', id_usuario: 2, data_inicio: '2026-11-08T12:00:00Z' },
    { signal: controller.signal },
  )
  assert.match(calls[0].path, /^\/auditoria\?/)
  assert.equal(
    new URL(calls[0].path, 'http://test').searchParams.get('data_inicio'),
    '2026-11-08T12:00:00Z',
  )
  assert.equal(calls[0].options.signal, controller.signal)
  await api.dashboard({ signal: controller.signal })
  assert.equal(calls[1].path, '/dashboard')
})

test('HOTEL retorna ao próprio cadastro na consulta, sem atalho ao inventário global', () => {
  const item = seed.estabelecimentos[0]
  const user = { perfil: 'HOTEL', id_estabelecimento: item.id_estabelecimento }
  const detail = render('EstablishmentDetail', {
    api: {},
    user,
    id: item.id_estabelecimento,
    initialData: item,
  })
  assert.match(detail, /Voltar ao meu cadastro/)
  assert.doesNotMatch(detail, /Voltar ao inventário/)
  const history = render('ResearchHistoryPage', {
    api: {},
    user,
    establishmentId: item.id_estabelecimento,
    initialData: { surveys: [], history: [], subject: item },
  })
  assert.match(history, /href="#\/meu-cadastro"/)
})

test('filtro de autor aceita inteiro zero conforme contrato, sem confundir com ausência', () => {
  assert.deepEqual(domain.auditQuery({ id_usuario: '0' }), { id_usuario: 0 })
})
