import { validateSchema } from './establishment.js'
export const roles = {
  ADMINISTRADOR: 'Administrador',
  GESTOR: 'Funcionário — consulta',
  EDITOR: 'Funcionário — edição',
  HOTEL: 'Hospedagem',
}
const email = { type: 'string', format: 'email', minLength: 1 }
const requiredText = { type: 'string', minLength: 1 }
export function validateAccess(draft, kind = 'login') {
  const properties =
    kind === 'activate'
      ? { senha: requiredText, confirmacao: requiredText }
      : kind === 'recover'
        ? { email }
        : { email, senha: requiredText }
  const errors = validateSchema(draft, {
    type: 'object',
    properties,
    required: Object.keys(properties),
  })
  for (const field of Object.keys(properties))
    if (!draft[field]?.trim()) errors[field] = 'Campo obrigatório.'
  if (kind === 'activate' && draft.senha !== draft.confirmacao)
    errors.confirmacao = 'As senhas não conferem.'
  return errors
}
export function profilePayload(draft, user) {
  return Object.fromEntries(
    ['nome', 'email']
      .filter((key) => draft[key]?.trim() !== user[key])
      .map((key) => [key, draft[key]?.trim()]),
  )
}
export function validateProfile(draft) {
  const errors = validateSchema(draft, {
    type: 'object',
    properties: { nome: requiredText, email },
    required: ['nome', 'email'],
  })
  if (!draft.nome?.trim()) errors.nome = 'Campo obrigatório.'
  return errors
}
export function accountPayload(draft) {
  return {
    nome: draft.nome.trim(),
    email: draft.email.trim().toLowerCase(),
    perfil: draft.perfil,
    ...(draft.perfil === 'HOTEL' ? { id_estabelecimento: draft.id_estabelecimento } : {}),
  }
}
export function validateAccount(draft) {
  const errors = validateProfile({ nome: draft.nome, email: draft.email })
  if (!Object.hasOwn(roles, draft.perfil)) errors.perfil = 'Selecione um perfil válido.'
  if (draft.perfil === 'HOTEL' && !draft.id_estabelecimento)
    errors.id_estabelecimento = 'Selecione a hospedagem vinculada.'
  return errors
}
export async function createAccountAndInvite(api, payload, previousAccount) {
  const account = previousAccount || (await api.createUser(payload))
  try {
    return { account, invite: await api.createInvite({ email: account.email }) }
  } catch (error) {
    error.account = account
    throw error
  }
}
export function validateSurvey(draft) {
  const errors = validateSchema(draft, {
    type: 'object',
    properties: {
      titulo: requiredText,
      tipo: { type: 'string', enum: ['CONSOLIDADO', 'EXPECTATIVA'] },
      periodo_inicio: { type: 'string', format: 'date' },
      periodo_fim: { type: 'string', format: 'date' },
      estabelecimentos: { type: 'array', items: { type: 'string' } },
    },
    required: ['titulo', 'tipo', 'periodo_inicio', 'periodo_fim', 'estabelecimentos'],
  })
  if (!draft.titulo?.trim()) errors.titulo = 'Informe o título.'
  if (draft.periodo_inicio > draft.periodo_fim)
    errors.periodo_fim = 'A data final deve ser posterior ou igual à inicial.'
  if (!draft.estabelecimentos?.length)
    errors.estabelecimentos = 'Selecione pelo menos uma hospedagem.'
  return errors
}
export function surveyPayload(draft, initial) {
  return Object.fromEntries(
    ['titulo', 'tipo', 'periodo_inicio', 'periodo_fim', 'estabelecimentos']
      .filter((key) => !initial || JSON.stringify(draft[key]) !== JSON.stringify(initial[key]))
      .map((key) => [key, key === 'titulo' ? draft[key].trim() : draft[key]]),
  )
}
export function validateOccupancy(value) {
  return (typeof value === 'number' || typeof value === 'string') &&
    String(value).trim() !== '' &&
    value != null &&
    Number.isFinite(Number(value)) &&
    Number(value) >= 0 &&
    Number(value) <= 100
    ? {}
    : { taxa_ocupacao: 'Informe uma taxa entre 0 e 100%.' }
}
export function operationError(error) {
  const fields = Object.fromEntries(
    (error.details || []).map((detail) => [detail.field, detail.issue]),
  )
  if (error.code === 'EMAIL_ALREADY_EXISTS') fields.email = 'Já existe uma conta com esse e-mail.'
  const messages = {
    INVALID_CREDENTIALS: 'E-mail ou senha inválidos.',
    INVITE_NOT_FOUND: 'Convite não encontrado ou expirado.',
    INVITE_ALREADY_USED: 'Este convite não está mais disponível.',
    SURVEY_CLOSED: 'Esta pesquisa está encerrada.',
    RESPONSE_ALREADY_SENT: 'A resposta desta hospedagem já foi enviada.',
  }
  return {
    fields,
    message:
      messages[error.code] ||
      (error.status === 403
        ? 'Seu perfil não tem permissão para esta ação.'
        : error.message || 'Não foi possível concluir a operação.'),
  }
}
export async function loadRecipients(api, options = {}) {
  const categories = (await api.categories(options)).data.filter(
    (category) => category.nome_categoria.toLowerCase() === 'meios de hospedagem',
  )
  const result = []
  for (const category of categories) {
    let page = 1
    while (true) {
      const body = await api.establishments(
        { id_categoria: category.id_categoria, page, page_size: 100 },
        options,
      )
      result.push(...body.data)
      if (page >= body.pagination.total_pages) break
      page++
    }
  }
  return result
}
