import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { testServer } from './testSupport.js'
import { createSession } from './services/session.js'
import { readPreferences, savePreferences, applyPreferences } from './services/preferences.js'
import { createHttpClient, createInventoryApi } from './services/http.js'
let prepareReport
let server,
  domain,
  navigation,
  pages = {}
before(async () => {
  server = await testServer()
  domain = await server.ssrLoadModule('/src/domain/operations.js')
  navigation = await server.ssrLoadModule('/src/domain/navigation.js')
  ;({ prepareReport } = await server.ssrLoadModule('/src/services/reports.js'))
  for (const name of ['AccessPage', 'ProfilePage', 'AccountsPage', 'SurveysPage', 'HotelHome'])
    pages[name] = (await server.ssrLoadModule(`/src/pages/${name}.jsx`)).default
})
after(async () => {
  await server?.close()
})
const storage = () => {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  }
}
const user = {
  id_usuario: 1,
  nome: 'Marina Administradora',
  email: 'marina@example.test',
  perfil: 'ADMINISTRADOR',
}
const render = (name, props) => renderToStaticMarkup(React.createElement(pages[name], props))

test('sessão expira e remove as credenciais', () => {
  let time = 1000
  const local = storage(),
    session = createSession(local, () => time)
  session.save({ access_token: 'token', expires_in: 1 })
  assert.equal(session.token(), 'token')
  time = 2000
  assert.equal(session.token(), null)
  assert.equal(local.getItem('oto.accessToken'), null)
  assert.throws(() => session.save({ access_token: 'bad', expires_in: 0 }))
})
test('falha de storage não deixa token parcial', () => {
  const local = storage(),
    set = local.setItem
  local.setItem = (key, value) => {
    if (key === 'oto.expiresAt') throw new Error('quota')
    set(key, value)
  }
  assert.throws(() => createSession(local).save({ access_token: 'token', expires_in: 1 }))
  assert.equal(local.getItem('oto.accessToken'), null)
})
test('requisição protegida sem sessão não chega ao proxy local', async () => {
  let count = 0,
    expired = 0
  const request = createHttpClient({
    requireSession: true,
    fetchImpl: async () => {
      count++
      return Response.json({})
    },
    onUnauthorized: () => expired++,
  })
  await assert.rejects(request('/perfil'), (error) => error.status === 401)
  assert.equal(count, 0)
  assert.equal(expired, 1)
  await request('/auth/login', {
    method: 'POST',
    body: { email: 'a@b', senha: 'x' },
  })
  assert.equal(count, 1)
})
test('login inválido não dispara o tratamento de expiração', async () => {
  let expired = 0
  const request = createHttpClient({
    requireSession: true,
    onUnauthorized: () => expired++,
    fetchImpl: async () =>
      Response.json({ error: { code: 'INVALID_CREDENTIALS' } }, { status: 401 }),
  })
  await assert.rejects(request('/auth/login', { method: 'POST', body: {} }))
  assert.equal(expired, 0)
})
test('valida login, convite, senha confirmada e recuperação', () => {
  assert.ok(domain.validateAccess({ email: 'errado', senha: '' }).email)
  assert.ok(domain.validateAccess({ senha: 'a', confirmacao: 'b' }, 'activate').confirmacao)
  assert.deepEqual(domain.validateAccess({ senha: 'abc', confirmacao: 'abc' }, 'activate'), {})
  assert.deepEqual(domain.validateAccess({ email: 'usuario@example.test' }, 'recover'), {})
})
test('perfil envia somente nome/email alterados e ignora cargo', () => {
  assert.deepEqual(domain.profilePayload({ ...user, nome: ' Novo ' }, user), {
    nome: 'Novo',
  })
  assert.ok(domain.validateProfile({ nome: '', email: 'errado' }).email)
})
test('preferências são isoladas por usuário e validadas ao carregar', () => {
  const local = storage(),
    other = { id_usuario: 2 }
  savePreferences(local, user, { theme: 'dark', font: 'large' })
  assert.deepEqual(readPreferences(local, user), {
    theme: 'dark',
    font: 'large',
  })
  assert.deepEqual(readPreferences(local, other), {
    theme: 'light',
    font: 'normal',
  })
  local.setItem('oto.preferences.2', 'invalid')
  assert.equal(readPreferences(local, other).theme, 'light')
  const root = {
    dataset: {},
    style: {
      setProperty(key, value) {
        this[key] = value
      },
    },
  }
  applyPreferences({ theme: 'dark', font: 'larger' }, root)
  assert.equal(root.style['--font-scale'], 1.28)
})
test('convite exige vínculo HOTEL e payload de outra conta não carrega vínculo antigo', () => {
  assert.ok(
    domain.validateAccount({ nome: 'Hotel', email: 'a@b', perfil: 'HOTEL' }).id_estabelecimento,
  )
  assert.deepEqual(
    domain.accountPayload({
      nome: 'Nome',
      email: 'A@B',
      perfil: 'GESTOR',
      id_estabelecimento: 'id',
    }),
    { nome: 'Nome', email: 'a@b', perfil: 'GESTOR' },
  )
})
test('falha parcial de convite retoma sem criar outra conta', async () => {
  let created = 0,
    sent = 0
  const account = { email: 'a@b' }
  const api = {
    async createUser() {
      created++
      return account
    },
    async createInvite() {
      sent++
      if (sent === 1) throw new Error('rede')
      return { id_convite: 'id' }
    },
  }
  let previous
  try {
    await domain.createAccountAndInvite(api, account)
  } catch (error) {
    previous = error.account
  }
  assert.equal(previous, account)
  const result = await domain.createAccountAndInvite(api, account, previous)
  assert.equal(result.account, account)
  assert.equal(created, 1)
  assert.equal(sent, 2)
})
test('recipientes carregam todas as páginas, não apenas a primeira', async () => {
  const seen = []
  const rows = await domain.loadRecipients({
    categories: async () => ({
      data: [{ id_categoria: 1, nome_categoria: 'Meios de hospedagem' }],
    }),
    establishments: async (params) => {
      seen.push(params.page)
      return {
        data: [{ id_estabelecimento: String(params.page) }],
        pagination: { total_pages: 2 },
      }
    },
  })
  assert.equal(rows.length, 2)
  assert.deepEqual(seen, [1, 2])
})
test('pesquisa valida período e destinatários, PATCH não envia campos intocados', () => {
  const draft = {
    titulo: 'Teste',
    tipo: 'CONSOLIDADO',
    periodo_inicio: '2026-11-01',
    periodo_fim: '2026-11-30',
    estabelecimentos: ['id'],
  }
  assert.deepEqual(domain.validateSurvey(draft), {})
  assert.ok(domain.validateSurvey({ ...draft, periodo_fim: '2026-10-01' }).periodo_fim)
  assert.ok(domain.validateSurvey({ ...draft, estabelecimentos: [] }).estabelecimentos)
  assert.deepEqual(domain.surveyPayload({ ...draft, titulo: 'Novo' }, draft), {
    titulo: 'Novo',
  })
  for (const rate of ['', '   ', false, [], -1, 101, 'abc'])
    assert.ok(domain.validateOccupancy(rate).taxa_ocupacao)
  assert.deepEqual(domain.validateOccupancy('0'), {})
  assert.deepEqual(domain.validateOccupancy('100'), {})
})
test('navegação bloqueia contas e fichas alheias por perfil', () => {
  assert.equal(navigation.portalRoute('#/contas', { perfil: 'GESTOR' }).kind, 'forbidden')
  assert.equal(
    navigation.portalRoute('#/estabelecimentos/other/editar', {
      perfil: 'HOTEL',
      id_estabelecimento: 'own',
    }).kind,
    'forbidden',
  )
  assert.equal(navigation.portalRoute('#/inicio', { perfil: 'HOTEL' }).kind, 'hotel')
  assert.equal(navigation.portalRoute('#/inicio', user).kind, 'reading')
  assert.equal(navigation.portalRoute('#/auditoria', { perfil: 'EDITOR' }).kind, 'forbidden')
})
test('acesso usa campos de senha protegidos e link de recuperação', () => {
  const result = render('AccessPage', { api: {}, onNavigate() {} })
  assert.match(result, /type="password"/)
  assert.match(result, /autoComplete="current-password"/)
  assert.match(result, /Entrar no Sistema/)
  assert.match(result, /Esqueci minha senha/)
  const invalid = render('AccessPage', {
    api: {},
    kind: 'activate',
    invitation: {},
    onNavigate() {},
  })
  assert.match(invalid, /Link de ativação inválido/)
  assert.doesNotMatch(invalid, /<form/)
  const active = render('AccessPage', {
    api: {},
    kind: 'activate',
    invitation: { id: 'id', token: 'token' },
    onNavigate() {},
  })
  assert.match(active, /Repetir Senha/)
  assert.match(active, /autoComplete="new-password"/)
})
test('perfil renderiza cargo protegido e preferências do protótipo', () => {
  const result = render('ProfilePage', { user, api: {}, onUpdated() {} })
  assert.match(result, /Meus Dados/)
  assert.match(result, /Tamanho da Fonte/)
  assert.match(result, /Escuro/)
  assert.match(result.match(/<input[^>]*name="perfil"[^>]*>/)[0], /disabled/)
  assert.doesNotMatch(result, /name="senha"/)
})
test('painel de contas preserva equipe, hospedagens e limita remoção indisponível', () => {
  const result = render('AccountsPage', {
    api: {},
    initialData: {
      users: [user, { ...user, id_usuario: 2, perfil: 'HOTEL', ativo: false }],
      recipients: [],
    },
  })
  assert.match(result, /Equipe Interna/)
  assert.match(result, /Hospedagens/)
  assert.match(result, /Reenviar convite/)
  assert.match(result, /Remoção de acesso ainda não disponível/)
})
test('GESTOR consulta pesquisas sem receber ações de gestão', () => {
  const survey = {
    id_pesquisa: 'id',
    titulo: 'Teste',
    tipo: 'CONSOLIDADO',
    status: 'ABERTA',
    periodo_inicio: '2026-11-01',
    periodo_fim: '2026-11-30',
    estabelecimentos: ['id'],
  }
  const result = render('SurveysPage', {
    api: {},
    user: { perfil: 'GESTOR' },
    initialData: { surveys: [survey], recipients: [], history: [] },
  })
  assert.doesNotMatch(result, /Preparar Nova Pesquisa|>Editar<|>Encerrar</)
  assert.match(result, /Baixar CSV/)
  const admin = render('SurveysPage', {
    api: {},
    user,
    initialData: { surveys: [survey], recipients: [], history: [] },
  })
  assert.match(admin, /Preparar Nova Pesquisa/)
  assert.match(admin, />Encerrar</)
})
test('início HOTEL cobre pendências e estado sem pesquisas', () => {
  assert.match(
    render('HotelHome', { api: {}, initialData: { pending: [], history: [] } }),
    /Você não tem pesquisas pendentes/,
  )
  assert.match(
    render('HotelHome', {
      api: {},
      initialData: {
        pending: [
          {
            id_pesquisa: 'id',
            titulo: 'Pesquisa',
            periodo_inicio: '2026-11-01',
            periodo_fim: '2026-11-30',
          },
        ],
        history: [],
      },
    }),
    /Enviar Resposta/,
  )
})
test('relatórios aguardam geração e rejeitam JSON disfarçado de arquivo', async () => {
  let calls = 0
  const result = await prepareReport(
    {
      createReport: async () => ({ id_relatorio: 'id', status: 'PENDENTE' }),
      report: async () => {
        calls++
        return { id_relatorio: 'id', status: 'CONCLUIDO' }
      },
      downloadReport: async () => ({
        blob: new Blob(['pdf'], { type: 'application/pdf' }),
      }),
    },
    { formato: 'PDF' },
    { wait: async () => {} },
  )
  assert.equal(calls, 1)
  assert.equal(result.name, 'relatorio.pdf')
  await assert.rejects(
    prepareReport(
      {
        createReport: async () => ({ id_relatorio: 'id', status: 'CONCLUIDO' }),
        downloadReport: async () => ({
          blob: new Blob(['{}'], { type: 'application/json' }),
        }),
      },
      { formato: 'PDF' },
    ),
    /arquivo válido/,
  )
  await assert.rejects(
    prepareReport(
      {
        createReport: async () => ({ id_relatorio: 'id', status: 'PENDENTE' }),
        report: async () => ({ id_relatorio: 'id', status: 'PENDENTE' }),
      },
      { formato: 'CSV' },
      { wait: async () => {}, attempts: 2 },
    ),
    /processamento/,
  )
})
test('novas operações reutilizam o cliente HTTP e os caminhos existentes', async () => {
  const calls = [],
    api = createInventoryApi(async (...args) => {
      calls.push(args)
      return {}
    })
  await api.login({ email: 'a@b', senha: 'x' })
  await api.activate('id', { token: 'token', senha: 'nova' })
  await api.updateProfile({ nome: 'Nome' })
  await api.createUser({})
  await api.createInvite({})
  await api.createSurvey({})
  await api.answerSurvey('id', { taxa_ocupacao: 50 })
  await api.logout()
  assert.deepEqual(
    calls.map(([url]) => url),
    [
      '/auth/login',
      '/convites/id/aceitacao',
      '/perfil',
      '/usuarios',
      '/convites',
      '/pesquisas-ocupacao',
      '/pesquisas-ocupacao/id/respostas',
      '/auth/logout',
    ],
  )
})
