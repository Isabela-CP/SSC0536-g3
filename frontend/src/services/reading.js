import { allEstablishments, inventoryQuery } from '../domain/reading.js'
import { hostingCategories } from '../domain/establishment.js'
export async function loadInventory(api, draft, options = {}) {
  const categories = hostingCategories((await api.categories(options)).data)
  if (!categories.length)
    return {
      categories,
      data: [],
      markers: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 },
    }
  const params = {
    ...inventoryQuery(draft),
    id_categoria: Number(draft.id_categoria || categories[0].id_categoria),
  }
  const [result, markers] = await Promise.all([
    api.establishments(params, options),
    allEstablishments(api, params, options),
  ])
  return { ...result, markers, categories }
}
export async function loadDashboard(api, options = {}) {
  const [dashboard, categories] = await Promise.all([
    api.dashboard(options),
    api.categories(options),
  ])
  const groups = hostingCategories(categories.data)
  const markers = (
    await Promise.all(
      groups.map((row) => allEstablishments(api, { id_categoria: row.id_categoria }, options)),
    )
  ).flat()
  if (
    !dashboard.indicadores ||
    !Array.isArray(dashboard.alertas_cadastur) ||
    !Number.isInteger(dashboard.indicadores.total_empresas)
  )
    throw new Error(
      'Indicadores completos do dashboard indisponíveis neste backend. Atualize o servidor.',
    )
  return { ...dashboard, markers }
}
