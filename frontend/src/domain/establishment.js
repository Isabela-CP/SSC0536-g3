import contract from '../../../contratos_api_oto/openapi.json'

export const schemas = contract.components.schemas
export const REQUIRED = schemas.EstabelecimentoCreate.required
export const BASIC_FIELDS = [
  'nome_fantasia',
  'razao_social',
  'id_categoria',
  'cnpj',
  'email_comercial',
  'endereco',
  'latitude',
  'longitude',
]
export const CONTACT_FIELDS = [
  'bairro',
  'cnae',
  'data_abertura',
  'telefone_comercial',
  'telefones_comerciais',
  'emails_comerciais',
  'telefone_pesquisas',
  'email_pesquisas',
  'aceita_pesquisas',
  'contato',
  'cargo_contato',
  'proprietarios',
  'site',
  'facebook',
  'instagram',
  'redes_sociais',
  'observacoes',
]
export const CADASTUR_FIELDS = [
  'cadastur_status',
  'possui_cadastur',
  'numero_cadastur',
  'vencimento_cadastur',
]
export const SECTION_FIELDS = ['meio_hospedagem', 'infraestrutura', 'acessibilidade']
export const EDITABLE_FIELDS = [
  ...BASIC_FIELDS,
  ...CONTACT_FIELDS,
  ...CADASTUR_FIELDS,
  ...SECTION_FIELDS,
]

export function resolveSchema(schema) {
  if (schema.$ref) return resolveSchema(schemas[schema.$ref.split('/').at(-1)])
  if (schema.oneOf)
    return {
      ...resolveSchema(schema.oneOf.find((s) => s.type !== 'null')),
      nullable: schema.oneOf.some((s) => s.type === 'null'),
    }
  if (Array.isArray(schema.type))
    return {
      ...schema,
      type: schema.type.find((t) => t !== 'null'),
      nullable: schema.type.includes('null'),
    }
  return schema
}

export function fieldsFor(schema, prefix = '') {
  const fields = []
  for (const [key, raw] of Object.entries(resolveSchema(schema).properties || {})) {
    const path = prefix ? `${prefix}.${key}` : key
    const field = resolveSchema(raw)
    if (field.type === 'object') fields.push(...fieldsFor(field, path))
    else fields.push({ ...field, path })
  }
  return fields
}

export const formSchema = {
  type: 'object',
  properties: Object.fromEntries(
    EDITABLE_FIELDS.map((key) => [key, schemas.EstabelecimentoCreate.properties[key]]),
  ),
}
export const formFields = fieldsFor(formSchema)
export const getPath = (object, path) =>
  path.split('.').reduce((value, key) => value?.[key], object)
export function setPath(object, path, value) {
  const keys = path.split('.')
  const last = keys.pop()
  let cursor = object
  for (const key of keys) cursor = cursor[key] ??= {}
  cursor[last] = value
  return object
}

export function permissions(user, establishment) {
  const admin = user?.perfil === 'ADMINISTRADOR'
  const own =
    user?.perfil === 'HOTEL' &&
    !!user.id_estabelecimento &&
    user.id_estabelecimento === establishment?.id_estabelecimento
  return {
    create: admin,
    edit: admin || user?.perfil === 'EDITOR' || own,
    protected: admin,
    status: admin,
    documents: admin || user?.perfil === 'EDITOR' || own,
  }
}

export function normalizeCnpj(value = '') {
  return String(value).replace(/\D/g, '')
}
export function validCnpj(value) {
  if (!/^\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}$/.test(value || '')) return false
  const digits = normalizeCnpj(value)
  if (/^(\d)\1+$/.test(digits)) return false
  const numbers = [...digits].map(Number)
  return [
    [12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]],
    [13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]],
  ].every(([length, weights]) => {
    const rest = weights.reduce((sum, weight, index) => sum + numbers[index] * weight, 0) % 11
    return numbers[length] === (rest < 2 ? 0 : 11 - rest)
  })
}

export function draftFrom(item) {
  return Object.fromEntries(
    formFields
      .filter((field) => getPath(item, field.path) !== undefined)
      .map((field) => [field.path, getPath(item, field.path)]),
  )
}
export const emptyDraft = () => ({
  aceita_pesquisas: true,
  cadastur_status: 'OBRIGATORIO',
  possui_cadastur: false,
})

export function normalizeField(field, value) {
  if (value === null || value === undefined) return value
  if (field.type === 'array')
    return Array.isArray(value)
      ? value
      : value
          .split(/\n/)
          .map((entry) => entry.trim())
          .filter(Boolean)
  if (value === '' && field.nullable) return null
  if (['number', 'integer'].includes(field.type) && value !== '') return Number(value)
  if (field.path === 'cnpj' && value) return normalizeCnpj(value)
  if (field.format === 'time' && /^\d{2}:\d{2}$/.test(value)) return `${value}:00`
  return value
}

export function buildPayload(
  draft,
  { mode = 'create', dirty = Object.keys(draft), user, establishment } = {},
) {
  const access = permissions(user, establishment)
  if (!(mode === 'create' ? access.create : access.edit))
    throw new Error('Você não tem permissão para salvar esta hospedagem.')
  const payload = {}
  for (const field of formFields) {
    if (!(field.path in draft) || (mode === 'edit' && !dirty.includes(field.path))) continue
    if (mode === 'edit' && ['cnpj', 'razao_social'].includes(field.path) && !access.protected)
      throw new Error('CNPJ e razão social só podem ser alterados por administrador.')
    const value = normalizeField(field, draft[field.path])
    if (
      value === undefined ||
      (mode === 'create' && value === '' && !REQUIRED.includes(field.path))
    )
      continue
    setPath(payload, field.path, value)
  }
  return payload
}

function formatValid(value, format) {
  if (format === 'email') return /^[^\s@]+@[^\s@]+$/.test(value)
  if (format === 'date')
    return (
      /^\d{4}-\d{2}-\d{2}$/.test(value) &&
      Number.isFinite(Date.parse(value)) &&
      new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value
    )
  if (format === 'time') return /^([01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?$/.test(value)
  return true
}

export function validateSchema(value, raw, path = '', errors = {}) {
  const schema = resolveSchema(raw)
  const fail = (message) => {
    errors[path] ??= message
  }
  if (value === undefined) return errors
  if (value === null) {
    if (!schema.nullable && schema.type !== 'null') fail('Este campo não pode ficar vazio.')
    return errors
  }
  if (schema.type === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      fail('Informe os dados deste grupo.')
      return errors
    }
    for (const key of schema.required || [])
      if (value[key] === undefined) errors[path ? `${path}.${key}` : key] = 'Campo obrigatório.'
    if (schema.minProperties && Object.keys(value).length < schema.minProperties)
      fail('Altere ao menos um campo antes de salvar.')
    for (const [key, entry] of Object.entries(value)) {
      const childPath = path ? `${path}.${key}` : key
      if (schema.properties?.[key]) validateSchema(entry, schema.properties[key], childPath, errors)
      else if (schema.additionalProperties === false) errors[childPath] = 'Campo não permitido.'
    }
    return errors
  }
  if (schema.type === 'array') {
    if (!Array.isArray(value)) {
      fail('Informe uma lista de valores.')
      return errors
    }
    if (schema.uniqueItems && new Set(value.map((v) => JSON.stringify(v))).size !== value.length)
      fail('Não repita valores nesta lista.')
    value.forEach((entry, i) => validateSchema(entry, schema.items, `${path}.${i}`, errors))
    return errors
  }
  const validType =
    schema.type === 'integer'
      ? Number.isInteger(value)
      : schema.type === 'number'
        ? typeof value === 'number' && Number.isFinite(value)
        : typeof value === schema.type
  if (!validType) {
    fail(schema.type === 'integer' ? 'Informe um número inteiro.' : 'Informe um valor válido.')
    return errors
  }
  if (schema.enum && !schema.enum.includes(value)) fail('Selecione uma opção válida.')
  if (schema.minLength && value.length < schema.minLength)
    fail(`Use pelo menos ${schema.minLength} caracteres.`)
  if (schema.maxLength && value.length > schema.maxLength)
    fail(`Use no máximo ${schema.maxLength} caracteres.`)
  if (schema.minimum !== undefined && value < schema.minimum)
    fail(`O valor mínimo é ${schema.minimum}.`)
  if (schema.maximum !== undefined && value > schema.maximum)
    fail(`O valor máximo é ${schema.maximum}.`)
  if (schema.pattern && !new RegExp(schema.pattern).test(value))
    fail('Informe um valor no formato correto.')
  if (schema.format && !formatValid(value, schema.format))
    fail(
      schema.format === 'date'
        ? 'Informe uma data válida.'
        : schema.format === 'email'
          ? 'Informe um e-mail válido.'
          : 'Informe um horário válido.',
    )
  return errors
}

export function validateEstablishment(payload, mode = 'create') {
  const errors = validateSchema(
    payload,
    schemas[mode === 'create' ? 'EstabelecimentoCreate' : 'EstabelecimentoUpdate'],
  )
  if (mode === 'create')
    for (const field of REQUIRED)
      if (payload[field] == null || payload[field] === '') errors[field] = 'Campo obrigatório.'
  if (payload.cnpj != null && !validCnpj(payload.cnpj))
    errors.cnpj = 'CNPJ inválido. Verifique os dígitos informados.'
  return errors
}

export function validateReason(reason) {
  const schema =
    contract.paths['/estabelecimentos/{id_estabelecimento}/inativacao'].post.requestBody.content[
      'application/json'
    ].schema
  return validateSchema({ motivo_inativacao: reason }, schema)
}

export function applyApiError(error) {
  const fields = {}
  for (const detail of error.details || []) fields[detail.field] = detail.issue
  const messages = {
    401: 'Sua sessão expirou. Entre novamente para continuar.',
    403: 'Você não tem permissão para esta ação.',
    404: 'Hospedagem, documento ou arquivo não encontrado.',
    409: error.message || 'Os dados já existem ou o status foi alterado. Atualize a ficha.',
    413: 'O arquivo excede o tamanho máximo permitido.',
    415: 'Tipo de arquivo não permitido. Use PDF, JPEG ou PNG.',
  }
  if (error.status === 409 && error.code === 'CONFLICT')
    fields.cnpj ??= 'Já existe uma hospedagem com este CNPJ.'
  return {
    message:
      messages[error.status] ||
      error.message ||
      'Não foi possível concluir a operação. Tente novamente.',
    fields,
  }
}

export const hostingCategories = (categories) =>
  categories.filter(
    (category) => category.nome_categoria.toLocaleLowerCase('pt-BR') === 'meios de hospedagem',
  )
