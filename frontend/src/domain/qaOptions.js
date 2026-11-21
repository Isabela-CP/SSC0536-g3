export const lodgingNames = [
  'HOTEL', 'POUSADA', 'RESORT', 'HOTEL FAZENDA', 'HOSTEL', 'FLAT', 'ACAMPAMENTO TURÍSTICO',
]

export const cadasturOptions = [
  ['REGULAR', 'Regular'],
  ['PROXIMO_VENCIMENTO', 'Próximo vencimento (90 dias para o vencimento)'],
  ['EM_ALERTA', 'EM ALERTA (30 dias para o vencimento)'],
  ['VENCIDO', 'Vencido'],
  ['SEM_VALIDADE', 'Sem validade / Não informado'],
].map(([value, label]) => ({ value, label }))

export function mockCadasturStatus(expiration, today = new Date().toISOString().slice(0, 10)) {
  if (!expiration) return 'SEM_VALIDADE'
  const days = (Date.parse(expiration) - Date.parse(today)) / 86400000
  if (days < 0) return 'VENCIDO'
  if (days <= 30) return 'EM_ALERTA'
  if (days <= 90) return 'PROXIMO_VENCIMENTO'
  return 'REGULAR'
}
