import { inventoryDefaults, inventoryErrors, inventoryQuery } from '../domain/reading.js'
import { hostingCategories } from '../domain/establishment.js'
export function mockInventory(items, user, searchParams) {
  const draft = { ...inventoryDefaults, ...Object.fromEntries(searchParams) }
  const errors = inventoryErrors(draft)
  if (Object.keys(errors).length) return { errors }
  const query = inventoryQuery(draft)
  let rows = items.filter(
    (row) => user.perfil !== 'HOTEL' || row.id_estabelecimento === user.id_estabelecimento,
  )
  const term = query.busca?.trim().toLowerCase()
  if (term)
    rows = rows.filter(
      (row) =>
        [row.nome_fantasia, row.razao_social, row.cnpj].some((value) =>
          value?.toLowerCase().includes(term),
        ) ||
        (/^[\d./-]+$/.test(term) &&
          term.replace(/\D/g, '').length > 0 &&
          row.cnpj?.replace(/\D/g, '').includes(term.replace(/\D/g, ''))),
    )
  for (const key of ['id_categoria', 'status', 'cadastur_status', 'aceita_pesquisas'])
    if (query[key] != null)
      rows = rows.filter(
        (row) => row[key] === (key === 'aceita_pesquisas' ? query[key] === 'true' : query[key]),
      )
  rows.sort((a, b) => a.id_estabelecimento.localeCompare(b.id_estabelecimento))
  rows.sort(
    (a, b) =>
      (query.ordenar_por === 'nome_fantasia'
        ? a.nome_fantasia.toLowerCase().localeCompare(b.nome_fantasia.toLowerCase())
        : new Date(a[query.ordenar_por]) - new Date(b[query.ordenar_por])) *
      (query.ordem === 'desc' ? -1 : 1),
  )
  return {
    data: rows.slice((query.page - 1) * query.page_size, query.page * query.page_size),
    pagination: {
      page: query.page,
      page_size: query.page_size,
      total: rows.length,
      total_pages: Math.max(1, Math.ceil(rows.length / query.page_size)),
    },
  }
}
export function mockDashboard(
  items,
  categories,
  today = new Date().toISOString().slice(0, 10),
) {
  const ids = hostingCategories(categories).map((row) => row.id_categoria)
  const rows = items.filter((row) => ids.includes(row.id_categoria))
  const beds = rows.map((row) => row.meio_hospedagem?.total_leitos)
  return {
    indicadores: {
      total_empresas: rows.length,
      total_leitos: beds.reduce((sum, value) => sum + (value || 0), 0),
      leitos_nao_informados: beds.filter((value) => value == null).length,
      estabelecimentos_ativos: rows.filter((row) => row.status === 'ATIVO').length,
    },
    referencia: today,
    alertas_cadastur: rows
      .filter((row) => row.possui_cadastur && row.vencimento_cadastur)
      .map((row) => ({
        id_estabelecimento: row.id_estabelecimento,
        nome_fantasia: row.nome_fantasia,
        data: row.vencimento_cadastur,
        dias_ate_vencimento: Math.round(
          (Date.parse(row.vencimento_cadastur) - Date.parse(today)) / 86400000,
        ),
      }))
      .sort(
        (a, b) =>
          a.data.localeCompare(b.data) ||
          a.id_estabelecimento.localeCompare(b.id_estabelecimento),
      ),
  }
}
