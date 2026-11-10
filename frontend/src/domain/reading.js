import { schemas, validateSchema } from './establishment.js'
import { labelFor } from './labels.js'
export const inventoryDefaults = {
  busca: '',
  id_categoria: '',
  status: '',
  cadastur_status: '',
  aceita_pesquisas: '',
  page: 1,
  page_size: 20,
  ordenar_por: 'nome_fantasia',
  ordem: 'asc',
}
export function inventoryQuery(draft) {
  return Object.fromEntries(
    Object.keys(inventoryDefaults)
      .filter((key) => draft[key] !== '' && draft[key] != null)
      .map((key) => [
        key,
        ['id_categoria', 'page', 'page_size'].includes(key) ? Number(draft[key]) : draft[key],
      ]),
  )
}
export function inventoryErrors(draft) {
  const query = inventoryQuery(draft)
  return validateSchema(query, {
    type: 'object',
    properties: {
      busca: { type: 'string', maxLength: 120 },
      id_categoria: { type: 'integer', minimum: 1 },
      status: schemas.StatusEstabelecimento,
      cadastur_status: schemas.CadasturStatus,
      aceita_pesquisas: { type: 'string', enum: ['true', 'false'] },
      page: { type: 'integer', minimum: 1 },
      page_size: { type: 'integer', minimum: 1, maximum: 100 },
      ordenar_por: { type: 'string', enum: ['nome_fantasia', 'criado_em', 'atualizado_em'] },
      ordem: { type: 'string', enum: ['asc', 'desc'] },
    },
  })
}
export async function allEstablishments(api, params = {}, options = {}) {
  const rows = []
  let page = 1
  while (true) {
    const result = await api.establishments({ ...params, page, page_size: 100 }, options)
    if (!Number.isInteger(result.pagination?.total_pages) || result.pagination.total_pages < 1)
      throw new Error('Paginação inválida recebida do servidor.')
    rows.push(...result.data)
    if (page >= result.pagination.total_pages) return rows
    page++
  }
}
export const hasCoordinates = (item) =>
  typeof item.latitude === 'number' &&
  typeof item.longitude === 'number' &&
  Number.isFinite(item.latitude) &&
  Number.isFinite(item.longitude) &&
  Math.abs(item.latitude) <= 90 &&
  Math.abs(item.longitude) <= 180
export function displayValue(value) {
  if (value === null) return 'Não informado'
  if (value === undefined) return 'Não informado'
  if (typeof value === 'boolean') return value ? 'Sim' : 'Não'
  if (Array.isArray(value)) return value.length ? value.map(displayValue).join(', ') : 'Nenhum'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
export function flatFields(value, prefix = '') {
  if (value && typeof value === 'object' && !Array.isArray(value))
    return Object.entries(value).flatMap(([key, child]) =>
      flatFields(child, prefix ? `${prefix}.${key}` : key),
    )
  return [{ path: prefix, label: prefix.split('.').map(labelFor).join(' / '), value }]
}
export function changes(before, after) {
  const previous = new Map(flatFields(before).map((item) => [item.path, item.value]))
  const current = new Map(flatFields(after).map((item) => [item.path, item.value]))
  return [...new Set([...previous.keys(), ...current.keys()])]
    .filter(
      (path) =>
        (path !== '' || (previous.size === 1 && current.size === 1)) &&
        JSON.stringify(previous.get(path)) !== JSON.stringify(current.get(path)),
    )
    .map((path) => ({
      path,
      label: path ? path.split('.').map(labelFor).join(' / ') : 'Registro',
      before: previous.get(path),
      after: current.get(path),
    }))
}
export function auditQuery(draft) {
  const query = {}
  if (draft.acao?.trim()) query.acao = draft.acao.trim()
  if (draft.id_usuario !== '') {
    if (
      !/^-?\d+$/.test(String(draft.id_usuario)) ||
      !Number.isSafeInteger(Number(draft.id_usuario))
    )
      throw new Error('Informe um ID de usuário válido.')
    query.id_usuario = Number(draft.id_usuario)
  }
  for (const key of ['data_inicio', 'data_fim'])
    if (draft[key]) {
      const value = new Date(draft[key])
      if (!Number.isFinite(value.getTime())) throw new Error('Informe uma data válida.')
      query[key] = value.toISOString()
    }
  if (query.data_inicio && query.data_fim && query.data_inicio > query.data_fim)
    throw new Error('A data final deve ser posterior ou igual à inicial.')
  return query
}
export function surveyHistory(surveys, history, establishment) {
  return surveys
    .filter((row) => !establishment || row.estabelecimentos.includes(establishment))
    .map((survey) => {
      const responses = history.filter(
        (row) =>
          row.id_pesquisa === survey.id_pesquisa &&
          (!establishment || row.id_estabelecimento === establishment),
      )
      return {
        ...survey,
        responses,
        responseRate: survey.estabelecimentos.length
          ? (100 * new Set(responses.map((row) => row.id_estabelecimento)).size) /
            (establishment ? 1 : survey.estabelecimentos.length)
          : null,
      }
    })
}
export const dateLabel = (value) =>
  value ? value.slice(0, 10).split('-').reverse().join('/') : 'Não informado'

export function researchStats(rows, now = new Date()) {
  const responses = rows.flatMap((row) => row.responses)
  const recipients = rows.reduce((sum, row) => sum + row.estabelecimentos.length, 0)
  const answered = rows.reduce(
    (sum, row) =>
      sum + new Set(row.responses.map((response) => response.id_estabelecimento)).size,
    0,
  )
  return {
    active: rows.filter((row) => row.status === 'ABERTA').length,
    month: responses.filter((row) => {
      const date = new Date(row.enviada_em)
      return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth()
    }).length,
    rate: recipients ? (100 * answered) / recipients : null,
  }
}
