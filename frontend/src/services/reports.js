import { saveDownload } from '../domain/documents.js'
export async function prepareReport(
  api,
  payload,
  { wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)), attempts = 20 } = {},
) {
  let report = await api.createReport(payload)
  for (let attempt = 0; attempt < attempts && report.status !== 'CONCLUIDO'; attempt++) {
    if (['FALHOU', 'ERRO'].includes(report.status))
      throw new Error('A geração do relatório falhou.')
    await wait(500)
    report = await api.report(report.id_relatorio)
  }
  if (report.status !== 'CONCLUIDO')
    throw new Error('O relatório ainda está em processamento. Tente novamente em instantes.')
  const file = await api.downloadReport(report.id_relatorio)
  const expected = payload.formato === 'PDF' ? 'application/pdf' : 'text/csv'
  if (!file.blob.type.startsWith(expected))
    throw new Error('O serviço ainda não disponibilizou um arquivo válido para este relatório.')
  return { file, name: `relatorio.${payload.formato.toLowerCase()}` }
}
export async function exportReport(api, payload) {
  const result = await prepareReport(api, payload)
  saveDownload(result.file, result.name)
}
