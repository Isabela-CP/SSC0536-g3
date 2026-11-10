import { mockInventory, mockDashboard } from './mockReading.js'
import seed from '../../../contratos_api_oto/mocks/seed-data.json'
import {
  permissions,
  normalizeCnpj,
  validateEstablishment,
  validateReason,
  hostingCategories,
} from '../domain/establishment.js'
import { validateDocument, validateFile } from '../domain/documents.js'

export function mockUser(role = 'ADMINISTRADOR') {
  const account = seed.contas_empresario[0]
  return {
    id_usuario: role === 'HOTEL' ? account.id_conta : 1,
    nome: role === 'HOTEL' ? 'Responsável pela hospedagem' : 'Marina Administradora',
    email: role === 'HOTEL' ? account.email : 'marina.admin@example.test',
    perfil: role,
    ativo: true,
    ...(role === 'HOTEL' ? { id_estabelecimento: account.id_estabelecimento } : {}),
  }
}
export function createMockFetch(user = mockUser()) {
  let items = structuredClone(seed.estabelecimentos)
  let nextDocumentId =
    Math.max(0, ...items.flatMap((item) => item.documentos.map((doc) => doc.id_documento))) + 1
  const files = new Map()
  const json = (value, status = 200) => Response.json(value, { status })
  const fail = (status, code, message, errors = {}) =>
    json(
      {
        error: {
          code,
          message,
          details: Object.entries(errors).map(([field, issue]) => ({ field, issue })),
        },
      },
      status,
    )
  const invalid = (errors) =>
    fail(422, 'VALIDATION_ERROR', 'Verifique os campos informados.', errors)
  const merge = (current, changes) => {
    const result = structuredClone(current)
    for (const [key, value] of Object.entries(changes))
      result[key] =
        value && typeof value === 'object' && !Array.isArray(value)
          ? merge(result[key] || {}, value)
          : value
    return result
  }
  return async function mockFetch(url, options = {}) {
    if (options.signal?.aborted) throw new DOMException('Cancelado', 'AbortError')
    const requestUrl = new URL(url, 'http://mock.local')
    const path = requestUrl.pathname
    const method = options.method || 'GET'
    if (path === '/auth/login') {
      const data = JSON.parse(options.body || '{}')
      const password = {
        ADMINISTRADOR: 'admin-demo',
        GESTOR: 'gestor-demo',
        EDITOR: 'editor-demo',
        HOTEL: 'hotel-demo',
      }[user.perfil]
      return data.email?.trim().toLowerCase() === user.email && data.senha === password
        ? json({
            access_token: 'mock-session',
            expires_in: 3600,
            token_type: 'Bearer',
            usuario: user,
          })
        : fail(401, 'INVALID_CREDENTIALS', 'E-mail ou senha inválidos.')
    }
    if (path === '/auth/logout') return new Response(null, { status: 204 })
    if (path === '/auth/recuperacao-senha')
      return json({ message: 'Solicitação recebida.' }, 202)
    if (path === '/perfil' && method === 'PATCH') {
      const data = JSON.parse(options.body || '{}')
      if (Object.keys(data).some((key) => !['nome', 'email'].includes(key)))
        return fail(422, 'VALIDATION_ERROR', 'Campo não permitido.')
      Object.assign(user, data)
      return json(user)
    }
    if (
      [
        '/usuarios',
        '/convites',
        '/pesquisas-ocupacao',
        '/pesquisas-ocupacao/pendentes',
        '/respostas-ocupacao/historico',
        '/relatorios',
      ].includes(path)
    )
      return fail(503, 'MOCK_NOT_AVAILABLE', 'Este módulo requer a conexão com o backend real.')
    if (path === '/perfil') return json(user)
    if (path === '/categorias-estabelecimento')
      return json({ data: hostingCategories(seed.categorias_estabelecimento) })
    if (path === '/estabelecimentos' && method === 'GET') {
      const result = mockInventory(items, user, requestUrl.searchParams)
      return result.errors ? invalid(result.errors) : json(result)
    }
    if (path === '/dashboard')
      return user.perfil === 'HOTEL'
        ? fail(403, 'FORBIDDEN', 'Seu perfil não pode acessar o dashboard.')
        : json(mockDashboard(items, seed.categorias_estabelecimento))
    if (path === '/auditoria')
      return user.perfil === 'ADMINISTRADOR'
        ? json({ data: [] })
        : fail(403, 'FORBIDDEN', 'Auditoria exclusiva de administrador.')
    const payload = typeof options.body === 'string' ? JSON.parse(options.body) : options.body
    if (path === '/estabelecimentos' && method === 'POST') {
      if (!permissions(user).create)
        return fail(403, 'FORBIDDEN', 'Seu perfil não pode cadastrar.')
      const errors = validateEstablishment(payload)
      if (
        !hostingCategories(seed.categorias_estabelecimento).some(
          (category) => category.id_categoria === payload.id_categoria,
        )
      )
        errors.id_categoria = 'Categoria inválida.'
      if (Object.keys(errors).length) return invalid(errors)
      if (
        items.some(
          (item) => item.cnpj && normalizeCnpj(item.cnpj) === normalizeCnpj(payload.cnpj),
        )
      )
        return fail(409, 'CONFLICT', 'Já existe uma hospedagem com este CNPJ.')
      const item = {
        aceita_pesquisas: true,
        possui_cadastur: false,
        cadastur_status: 'OBRIGATORIO',
        meio_hospedagem: null,
        infraestrutura: null,
        ...payload,
        id_estabelecimento: crypto.randomUUID(),
        status: 'ATIVO',
        motivo_inativacao: null,
        criado_em: new Date().toISOString(),
        atualizado_em: new Date().toISOString(),
        documentos: [],
        categoria: structuredClone(
          seed.categorias_estabelecimento.find(
            (category) => category.id_categoria === payload.id_categoria,
          ),
        ),
      }
      items.push(item)
      return json(item, 201)
    }
    const match = path.match(
      /^\/estabelecimentos\/([^/]+)(?:\/(inativacao|reativacao|documentos)(?:\/(\d+)(?:\/(arquivo))?)?)?$/,
    )
    if (!match) return fail(404, 'NOT_FOUND', 'Recurso não encontrado.')
    const [, id, resource, documentId, fileRoute] = match
    if (user.perfil === 'HOTEL' && (!user.id_estabelecimento || user.id_estabelecimento !== id))
      return fail(403, 'FORBIDDEN', 'Você só pode acessar sua hospedagem.')
    let item = items.find((entry) => entry.id_estabelecimento === id)
    if (!item) return fail(404, 'NOT_FOUND', 'Hospedagem não encontrada.')
    const access = permissions(user, item)
    if (method !== 'GET' && !access.edit)
      return fail(403, 'FORBIDDEN', 'Seu perfil tem acesso somente à consulta.')
    if (!resource) {
      if (method === 'GET') return json(item)
      if (!access.protected && ('cnpj' in payload || 'razao_social' in payload))
        return fail(403, 'FORBIDDEN', 'Campo reservado ao administrador.')
      const errors = validateEstablishment(payload, 'edit')
      if (Object.keys(errors).length) return invalid(errors)
      if (
        payload.cnpj &&
        items.some(
          (entry) =>
            entry.id_estabelecimento !== id &&
            entry.cnpj &&
            normalizeCnpj(entry.cnpj) === normalizeCnpj(payload.cnpj),
        )
      )
        return fail(409, 'CONFLICT', 'Já existe uma hospedagem com este CNPJ.')
      item = merge(item, payload)
      item.atualizado_em = new Date().toISOString()
      items = items.map((entry) => (entry.id_estabelecimento === id ? item : entry))
      return json(item)
    }
    if (['inativacao', 'reativacao'].includes(resource)) {
      if (!access.status)
        return fail(403, 'FORBIDDEN', 'Apenas administradores podem alterar o status.')
      const target = resource === 'inativacao' ? 'INATIVO' : 'ATIVO'
      if (target === 'INATIVO') {
        const errors = validateReason(payload?.motivo_inativacao)
        if (Object.keys(errors).length) return invalid(errors)
      }
      if (item.status === target)
        return fail(
          409,
          `ESTABELECIMENTO_JA_${target}`,
          `O estabelecimento já está ${target.toLowerCase()}.`,
        )
      item.status = target
      item.motivo_inativacao = target === 'INATIVO' ? payload.motivo_inativacao : null
      item.atualizado_em = new Date().toISOString()
      return json(item)
    }
    if (!documentId && method === 'GET') return json({ data: item.documentos })
    const document = item.documentos.find((doc) => doc.id_documento === Number(documentId))
    if (documentId && !document) return fail(404, 'NOT_FOUND', 'Documento não encontrado.')
    if (method === 'GET' && fileRoute) {
      const file = files.get(document.id_documento)
      return file
        ? new Response(file, {
            headers: {
              'Content-Type': 'application/octet-stream',
              'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent(file.name)}`,
            },
          })
        : fail(404, 'NOT_FOUND', 'O arquivo de exemplo ainda não foi enviado.')
    }
    if (method === 'PATCH') {
      const errors = validateDocument(payload, true)
      if (Object.keys(errors).length) return invalid(errors)
      Object.assign(document, payload)
      if (payload.data_vencimento) document.status = statusFor(payload.data_vencimento)
      return json(document)
    }
    const file = payload?.get('arquivo')
    const fileError = validateFile(file)
    if (fileError) {
      const status =
        file?.size > 10 * 1024 * 1024 ? 413 : file?.size && file.name.length <= 255 ? 415 : 422
      return fail(
        status,
        status === 415
          ? 'UNSUPPORTED_MEDIA_TYPE'
          : status === 413
            ? 'PAYLOAD_TOO_LARGE'
            : 'VALIDATION_ERROR',
        fileError,
        { arquivo: fileError },
      )
    }
    const metadata = {
      nome_arquivo: file.name,
      content_type: file.type,
      tamanho_bytes: file.size,
      enviado_em: new Date().toISOString(),
    }
    if (method === 'PUT') {
      document.arquivo = metadata
      files.set(document.id_documento, file)
      return json(document)
    }
    const data = Object.fromEntries([...payload].filter(([key]) => key !== 'arquivo'))
    const errors = validateDocument(data)
    if (Object.keys(errors).length) return invalid(errors)
    const created = {
      ...data,
      id_documento: nextDocumentId++,
      id_estabelecimento: id,
      arquivo: metadata,
      status: statusFor(data.data_vencimento),
    }
    item.documentos.push(created)
    files.set(created.id_documento, file)
    return json(created, 201)
  }
}
function statusFor(expiration) {
  const days = Math.ceil(
    (Date.parse(`${expiration}T00:00:00Z`) -
      Date.parse(`${new Date().toISOString().slice(0, 10)}T00:00:00Z`)) /
      86400000,
  )
  return days < 0 ? 'VENCIDO' : days <= 30 ? 'A_VENCER' : 'REGULAR'
}
