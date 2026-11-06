import { schemas, validateSchema } from './establishment.js'
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024
const allowed = { 'application/pdf': ['pdf'], 'image/jpeg': ['jpg', 'jpeg'], 'image/png': ['png'] }
export function validateFile(file, maxBytes = MAX_UPLOAD_BYTES) {
  if (!file) return 'Selecione um arquivo.'
  if (!file.size) return 'O arquivo não pode estar vazio.'
  if (file.size > maxBytes) return `O arquivo deve ter no máximo ${Number((maxBytes / 1024 / 1024).toFixed(2))} MiB.`
  if (!allowed[file.type]?.includes(file.name.split('.').at(-1).toLowerCase())) return 'Use um arquivo PDF, JPEG ou PNG com a extensão correspondente.'
  if (file.name.replaceAll('\\', '/').split('/').at(-1).length > 255) return 'O nome do arquivo deve ter no máximo 255 caracteres.'
  return null
}
export function documentPayload(draft, initial) {
  const result = {}
  for (const key of Object.keys(schemas.DocumentoControleCreate.properties)) {
    const value = draft[key] === '' && ['numero', 'data_emissao'].includes(key) ? null : draft[key]
    if (value !== undefined && (!initial || value !== (initial[key] ?? null))) result[key] = value
  }
  return result
}
export function validateDocument(payload, edit = false) { return validateSchema(payload, schemas[edit ? 'DocumentoControleUpdate' : 'DocumentoControleCreate']) }
export function documentFormData(payload, file) {
  const form = new FormData()
  for (const key of Object.keys(schemas.DocumentoControleCreate.properties)) if (payload[key] != null) form.append(key, payload[key])
  form.append('arquivo', file, file.name)
  return form
}
export function replacementFormData(file) {
  const form = new FormData()
  form.append('arquivo', file, file.name)
  return form
}
export function downloadName(disposition, fallback) {
  const encoded = disposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const simple = disposition?.match(/filename="?([^";]+)"?/i)?.[1]
  let name = simple || fallback || 'documento'
  if (encoded) { try { name = decodeURIComponent(encoded) } catch { /* Usa o nome público dos metadados. */ } }
  return name.replaceAll('\\', '/').split('/').at(-1).replace(/[\x00-\x1f]/g, '') || 'documento'
}
export function saveDownload({ blob, disposition }, fallback, browser = globalThis) {
  const url = browser.URL.createObjectURL(blob)
  const link = browser.document.createElement('a')
  link.href = url
  link.download = downloadName(disposition, fallback)
  browser.document.body.appendChild(link)
  link.click()
  link.remove()
  browser.setTimeout(() => browser.URL.revokeObjectURL(url), 1000)
}
