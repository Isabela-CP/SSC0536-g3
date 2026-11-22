import { roles, validateSurvey, surveyPayload } from '../domain/operations.js'
import { tableFile } from './inventoryFiles.js'

export function mockOperations(seed, user, items, audit, json, fail) {
  const users = structuredClone(seed.usuarios_internos)
  if (user.perfil === 'ADMINISTRADOR') users[0] = user
  for (const account of seed.contas_empresario)
    users.push({ ...account, id_usuario: account.id_conta, perfil: 'HOTEL',
      nome: items().find((item) => item.id_estabelecimento === account.id_estabelecimento)?.nome_fantasia || 'Hospedagem' })
  const surveys = seed.periodos_pesquisa.map((row) => ({
    id_pesquisa: String(row.id_periodo), titulo: row.titulo, tipo: row.tipo_pesquisa,
    periodo_inicio: row.data_inicio_ref, periodo_fim: row.data_fim_ref, status: row.status,
    estabelecimentos: items().filter((item) => item.status === 'ATIVO' && item.aceita_pesquisas)
      .map((item) => item.id_estabelecimento),
  }))
  const history = seed.respostas_ocupacao.map((row) => ({
    id_resposta: String(row.id_resposta), id_pesquisa: String(row.id_periodo),
    id_estabelecimento: row.id_estabelecimento, enviada_em: row.respondido_em,
    dados: { taxa_ocupacao: row.taxa_ocupacao },
  }))
  const reports = new Map()
  const forbidden = () => fail(403, 'FORBIDDEN', 'Seu perfil não tem permissão para esta ação.')
  return async (path, method, body) => {
    if (path === '/usuarios' && method === 'GET')
      return user.perfil === 'ADMINISTRADOR' ? json({ data: users }) : forbidden()
    const account = path.match(/^\/usuarios\/(\d+)$/)
    if (account && method === 'PATCH') {
      if (user.perfil !== 'ADMINISTRADOR') return forbidden()
      const target = users.find((row) => String(row.id_usuario) === account[1])
      if (!target) return fail(404, 'NOT_FOUND', 'Conta não encontrada.')
      if (target.id_usuario === user.id_usuario)
        return fail(409, 'CONFLICT', 'Não é possível alterar o próprio perfil.')
      if (!Object.hasOwn(roles, body?.perfil) ||
          (body.perfil === 'HOTEL' && !items().some((item) => item.id_estabelecimento === body.id_estabelecimento)))
        return fail(422, 'VALIDATION_ERROR', 'Informe um perfil e vínculo válidos.')
      const before = { ...target }
      target.perfil = body.perfil
      if (body.perfil === 'HOTEL') target.id_estabelecimento = body.id_estabelecimento
      else delete target.id_estabelecimento
      audit('USUARIO_PERFIL_ALTERADO', 'USUARIO', target.id_usuario, before, target)
      return json(target)
    }
    const hotel = user.perfil === 'HOTEL'
    const visible = hotel
      ? surveys.filter((survey) => survey.estabelecimentos.includes(user.id_estabelecimento))
      : surveys
    const responses = hotel
      ? history.filter((row) => row.id_estabelecimento === user.id_estabelecimento)
      : history
    if (path === '/pesquisas-ocupacao' && method === 'GET') return json({ data: visible })
    const surveyRoute = path.match(/^\/pesquisas-ocupacao\/([^/]+)(\/encerramento)?$/)
    if ((path === '/pesquisas-ocupacao' && method === 'POST') ||
        (surveyRoute && (method === 'PATCH' || (method === 'POST' && surveyRoute[2])))) {
      if (!['ADMINISTRADOR', 'EDITOR'].includes(user.perfil)) return forbidden()
      const previous = surveyRoute && surveys.find((row) => row.id_pesquisa === surveyRoute[1])
      if (surveyRoute && !previous) return fail(404, 'SURVEY_NOT_FOUND', 'Pesquisa não encontrada.')
      if (previous && previous.status !== 'ABERTA')
        return fail(409, 'SURVEY_CLOSED', 'Pesquisa encerrada.')
      if (surveyRoute?.[2]) {
        previous.status = 'ENCERRADA'
        return json(previous)
      }
      const draft = { ...previous, ...body }
      const errors = validateSurvey(draft)
      if (Object.keys(errors).length)
        return fail(422, 'VALIDATION_ERROR', 'Verifique os campos informados.', errors)
      const answered = history.filter((row) => row.id_pesquisa === previous?.id_pesquisa)
      if (answered.some((row) => !draft.estabelecimentos.includes(row.id_estabelecimento)))
        return fail(409, 'CONFLICT', 'Uma hospedagem com resposta não pode ser removida.')
      const changes = surveyPayload(draft)
      if (previous) return json(Object.assign(previous, changes))
      const created = { ...changes, id_pesquisa: crypto.randomUUID(), status: 'ABERTA' }
      surveys.push(created)
      return json(created, 201)
    }
    if (path === '/respostas-ocupacao/historico') return json({ data: responses })
    if (path === '/pesquisas-ocupacao/pendentes')
      return hotel ? json({ data: visible.filter((survey) => survey.status === 'ABERTA' &&
        !responses.some((row) => row.id_pesquisa === survey.id_pesquisa)) }) : forbidden()
    const answer = path.match(/^\/pesquisas-ocupacao\/([^/]+)\/respostas$/)
    if (answer && method === 'POST') {
      if (!hotel) return forbidden()
      const survey = surveys.find((row) => row.id_pesquisa === answer[1])
      if (!survey) return fail(404, 'SURVEY_NOT_FOUND', 'Pesquisa não encontrada.')
      if (!visible.includes(survey)) return forbidden()
      if (survey.status !== 'ABERTA') return fail(409, 'SURVEY_CLOSED', 'Pesquisa encerrada.')
      const rate = body?.taxa_ocupacao
      if (!Number.isFinite(rate) || rate < 0 || rate > 100)
        return fail(422, 'VALIDATION_ERROR', 'Informe uma taxa entre 0 e 100%.')
      const previous = responses.find((row) => row.id_pesquisa === survey.id_pesquisa)
      const entry = { id_resposta: previous?.id_resposta || crypto.randomUUID(),
        id_pesquisa: survey.id_pesquisa, id_estabelecimento: user.id_estabelecimento,
        id_usuario: user.id_usuario, enviada_em: new Date().toISOString(), dados: { taxa_ocupacao: rate } }
      if (previous) history[history.indexOf(previous)] = entry
      else history.push(entry)
      audit(previous ? 'RESPOSTA_OCUPACAO_CORRIGIDA' : 'RESPOSTA_OCUPACAO_ENVIADA',
        'RESPOSTA_OCUPACAO', entry.id_resposta, previous, entry)
      return json(entry, previous ? 200 : 201)
    }
    if (path === '/relatorios' || path.startsWith('/relatorios/')) {
      if (!['ADMINISTRADOR', 'GESTOR'].includes(user.perfil)) return forbidden()
      if (path === '/relatorios' && method === 'POST') {
        const { id_pesquisa, periodo_inicio, periodo_fim, id_categoria, formato, tipo } = body || {}
        if (tipo !== 'OCUPACAO' || !['PDF', 'CSV'].includes(formato))
          return fail(422, 'VALIDATION_ERROR', 'Formato de relatório inválido.')
        if (id_pesquisa && !surveys.some((row) => row.id_pesquisa === id_pesquisa))
          return fail(404, 'SURVEY_NOT_FOUND', 'Pesquisa não encontrada.')
        if ((periodo_inicio || periodo_fim) && (!periodo_inicio || !periodo_fim || periodo_inicio > periodo_fim))
          return fail(422, 'VALIDATION_ERROR', 'Informe um intervalo válido.')
        const rows = history.flatMap((row) => {
          const survey = surveys.find((entry) => entry.id_pesquisa === row.id_pesquisa)
          const item = items().find((entry) => entry.id_estabelecimento === row.id_estabelecimento)
          if (!survey || !item || (id_pesquisa && id_pesquisa !== row.id_pesquisa) ||
              (id_categoria && Number(id_categoria) !== item.id_categoria) ||
              (periodo_inicio && (survey.periodo_fim < periodo_inicio || survey.periodo_inicio > periodo_fim))) return []
          return [[survey.titulo, item.nome_fantasia, survey.periodo_inicio, survey.periodo_fim, row.dados.taxa_ocupacao]]
        })
        if (!rows.length) return fail(409, 'REPORT_NO_DATA', 'Nenhuma resposta encontrada para gerar o relatório.')
        const file = await tableFile([['Pesquisa', 'Hospedagem', 'Início', 'Fim', 'Ocupação (%)'], ...rows], formato, 'Relatório de ocupação')
        const id = crypto.randomUUID()
        const report = { id_relatorio: id, status: 'CONCLUIDO', formato, tipo }
        reports.set(id, { file, report })
        return json(report, 202)
      }
      const [, , id, file] = path.split('/')
      const entry = reports.get(id)
      if (!entry) return fail(404, 'NOT_FOUND', 'Relatório não encontrado.')
      return file === 'arquivo' ? new Response(entry.file) : json(entry.report)
    }
  }
}
