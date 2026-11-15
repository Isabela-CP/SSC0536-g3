// Executa o código REAL da camada de serviços do frontend (frontend/src/services e domain)
// contra a API real (OTO_INT_API_URL) e imprime as observações em JSON. Os oráculos ficam
// no pytest (test_int_04_frontend_api.py); aqui só se observa.
// Uso (a partir de frontend/): node ../testes_integracao_regressao/integracao/frontend/cliente_frontend.mjs <cenario>
import { testServer } from '../../../frontend/src/testSupport.js'

const [cenario] = process.argv.slice(2)
const BASE = process.env.OTO_INT_API_URL
const SENHAS = { ADMINISTRADOR: 'admin-demo', GESTOR: 'gestor-demo', EDITOR: 'editor-demo', HOTEL: 'hotel-demo' }
const CONTAS = {
  ADMINISTRADOR: 'marina.admin@example.test',
  GESTOR: 'rafael.consulta@example.test',
  EDITOR: 'camila.editora@example.test',
  HOTEL: 'responsavel@serra-azul.example',
}
const SERRA_AZUL = '11111111-1111-4111-8111-111111111111'

const server = await testServer()
const carregar = (caminho) => server.ssrLoadModule(caminho)

async function cliente(perfil) {
  const http = await carregar('/src/services/http.js')
  let token = null
  const eventos = { naoAutorizado: 0 }
  const api = http.createInventoryApi(
    http.createHttpClient({
      baseUrl: BASE,
      getToken: () => token,
      requireSession: true,
      onUnauthorized: () => eventos.naoAutorizado++,
    }),
  )
  if (perfil) token = (await api.login({ email: CONTAS[perfil], senha: SENHAS[perfil] })).access_token
  return { api, eventos, http, definirToken: (t) => (token = t) }
}

const erro = async (promessa, operationError) => {
  try {
    await promessa
    return { ok: true }
  } catch (e) {
    return { status: e.status, code: e.code, mensagem: operationError(e).message, campos: operationError(e).fields }
  }
}

const cenarios = {
  // Todas as operações que o frontend sabe chamar (método + caminho), sem rede.
  async rotas() {
    const http = await carregar('/src/services/http.js')
    const chamadas = []
    const api = http.createInventoryApi(async (path, opcoes = {}) => {
      chamadas.push({ metodo: (opcoes.method || 'GET').toUpperCase(), caminho: path.split('?')[0] })
      return {}
    })
    const form = new FormData()
    for (const [nome, funcao] of Object.entries(api)) {
      const n = chamadas.length
      await funcao('ID-1', nome.includes('Document') ? 'ID-2' : form, form).catch(() => {})
      if (chamadas.length > n) chamadas[chamadas.length - 1].funcao = nome
    }
    return chamadas
  },

  async sessao() {
    const { operationError } = await carregar('/src/domain/operations.js')
    const resultado = {}
    for (const perfil of Object.keys(CONTAS)) {
      const { api } = await cliente(perfil)
      resultado[perfil] = (await api.profile()).perfil
    }
    const { api, eventos } = await cliente('GESTOR')
    await api.logout()
    resultado.depoisDoLogout = await erro(api.profile(), operationError)
    resultado.eventosNaoAutorizado = eventos.naoAutorizado
    const anonimo = await cliente(null)
    resultado.semSessao = await erro(anonimo.api.dashboard(), operationError)
    resultado.eventosSemSessao = anonimo.eventos.naoAutorizado
    anonimo.eventos.naoAutorizado = 0
    resultado.senhaErrada = await erro(
      anonimo.api.login({ email: CONTAS.EDITOR, senha: 'senha-errada' }),
      operationError,
    )
    resultado.eventosNoLoginErrado = anonimo.eventos.naoAutorizado
    return resultado
  },

  async painel() {
    const { loadDashboard, loadInventory } = await carregar('/src/services/reading.js')
    const { inventoryDefaults } = await carregar('/src/domain/reading.js')
    const { api } = await cliente('ADMINISTRADOR')
    const painel = await loadDashboard(api)
    const inventario = await loadInventory(api, { ...inventoryDefaults })
    const busca = await loadInventory(api, { ...inventoryDefaults, busca: 'Serra Azul' })
    return {
      indicadores: painel.indicadores,
      marcadores: painel.markers.length,
      categorias: inventario.categories.map((c) => c.id_categoria),
      total: inventario.pagination.total,
      itens: inventario.data.length,
      busca: busca.data.map((e) => e.nome_fantasia),
    }
  },

  async relatorio() {
    const { prepareReport } = await carregar('/src/services/reports.js')
    const { api } = await cliente('GESTOR')
    const saida = {}
    for (const formato of ['CSV', 'PDF']) {
      const { file, name } = await prepareReport(api, { tipo: 'OCUPACAO', formato })
      const bytes = new Uint8Array(await file.blob.arrayBuffer())
      saida[formato] = {
        nome: name,
        tipo: file.blob.type,
        tamanho: bytes.length,
        inicio: new TextDecoder().decode(bytes.slice(0, 8)),
        disposicao: file.disposition,
      }
    }
    return saida
  },

  async documento() {
    const { validateFile } = await carregar('/src/domain/documents.js')
    const { api } = await cliente('ADMINISTRADOR')
    const conteudo = new TextEncoder().encode('%PDF-1.4\nintegracao frontend\n%%EOF\n')
    const arquivo = new File([conteudo], 'alvará municipal.pdf', { type: 'application/pdf' })
    const form = new FormData()
    form.set('tipo_documento', 'ALVARA')
    form.set('data_vencimento', '2031-05-10')
    form.set('arquivo', arquivo)
    const validacao = validateFile(arquivo) || null
    const criado = await api.uploadDocument(SERRA_AZUL, form)
    const baixado = await api.downloadDocument(SERRA_AZUL, criado.id_documento)
    const novo = new FormData()
    novo.set('arquivo', new File([new TextEncoder().encode('%PDF-1.4\nv2\n')], 'v2.pdf', { type: 'application/pdf' }))
    await api.replaceDocument(SERRA_AZUL, criado.id_documento, novo)
    const depois = await api.downloadDocument(SERRA_AZUL, criado.id_documento)
    const atualizado = await api.updateDocument(SERRA_AZUL, criado.id_documento, { numero: 'ALV-2031' })
    const lista = await api.documents(SERRA_AZUL)
    return {
      validacao,
      criado: { id: criado.id_documento, arquivo: criado.arquivo },
      baixadoIgual: Buffer.from(await baixado.blob.arrayBuffer()).equals(Buffer.from(conteudo)),
      disposicao: baixado.disposition,
      substituido: new TextDecoder().decode(await depois.blob.arrayBuffer()),
      numero: atualizado.numero,
      naLista: lista.data.some((d) => d.id_documento === criado.id_documento),
    }
  },

  async erros() {
    const { operationError, createAccountAndInvite } = await carregar('/src/domain/operations.js')
    const admin = (await cliente('ADMINISTRADOR')).api
    const editor = (await cliente('EDITOR')).api
    const hotel = (await cliente('HOTEL')).api
    const anonimo = (await cliente(null)).api
    const saida = {}
    saida.INVALID_CREDENTIALS = await erro(anonimo.login({ email: CONTAS.HOTEL, senha: 'x-errada' }), operationError)
    const conta = await createAccountAndInvite(admin, { nome: 'Conta Front', email: 'front@example.test', perfil: 'GESTOR' })
    saida.contaCriada = { email: conta.account.email, convite: conta.invite.status }
    saida.EMAIL_ALREADY_EXISTS = await erro(
      admin.createUser({ nome: 'Dup', email: CONTAS.EDITOR, perfil: 'GESTOR' }),
      operationError,
    )
    saida.INVITE_NOT_FOUND = await erro(
      anonimo.activate(conta.invite.id_convite, { token: 'token-inventado', senha: 'senha-segura-1' }),
      operationError,
    )
    const pesquisa = await editor.createSurvey({
      titulo: 'Encerrada pelo front', tipo: 'EXPECTATIVA', periodo_inicio: '2027-01-01',
      periodo_fim: '2027-01-31', estabelecimentos: [SERRA_AZUL],
    })
    await editor.closeSurvey(pesquisa.id_pesquisa)
    saida.SURVEY_CLOSED = await erro(hotel.answerSurvey(pesquisa.id_pesquisa, { taxa_ocupacao: 50 }), operationError)
    saida.RESPONSE_ALREADY_SENT = await erro(hotel.answerSurvey('3', { taxa_ocupacao: 50 }), operationError)
    saida.FORBIDDEN = await erro(hotel.users(), operationError)
    saida.VALIDATION_ERROR = await erro(
      admin.create({ id_categoria: 1, nome_fantasia: 'Sem CNPJ', razao_social: 'X', cnpj: '123', endereco: 'Rua' }),
      operationError,
    )
    return saida
  },

  async empresario() {
    const { api } = await cliente('HOTEL')
    const { validateOccupancy } = await carregar('/src/domain/operations.js')
    const pendentes = await api.pendingSurveys()
    const alvo = pendentes.data[0]
    const resposta = await api.answerSurvey(alvo.id_pesquisa, { taxa_ocupacao: 64.5 })
    const historico = await api.responseHistory()
    return {
      pendentes: pendentes.data.map((p) => p.id_pesquisa),
      validacaoFront: { taxa150: validateOccupancy('150'), taxa64: validateOccupancy('64.5') },
      resposta: { id_pesquisa: resposta.id_pesquisa, estabelecimento: resposta.id_estabelecimento },
      noHistorico: historico.data.some(
        (h) => h.id_pesquisa === alvo.id_pesquisa && h.dados.taxa_ocupacao === 64.5,
      ),
      pendentesDepois: (await api.pendingSurveys()).data.map((p) => p.id_pesquisa),
    }
  },
}

try {
  if (!cenarios[cenario]) throw new Error(`cenário desconhecido: ${cenario}`)
  const resultado = await cenarios[cenario]()
  process.stdout.write('@@RESULTADO@@' + JSON.stringify(resultado))
} finally {
  await server.close()
}
