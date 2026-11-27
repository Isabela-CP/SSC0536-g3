import React from 'react'

const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'America/Sao_Paulo',
})

export default function CadasturBanner({ establishment, user, today = saoPauloDate.format() }) {
  if (!['ADMINISTRADOR', 'GESTOR', 'EDITOR'].includes(user?.perfil)) return null
  const expiration = establishment?.vencimento_cadastur
  if (!establishment?.possui_cadastur || !expiration) return null

  // Compara datas civis em UTC para evitar efeitos de fuso e horário de verão.
  const days = (Date.parse(expiration) - Date.parse(today)) / 86_400_000
  if (!Number.isFinite(days) || days > 90) return null

  const expired = days < 0
  const remaining = days === 0 ? 'vence hoje' : days === 1 ? 'falta 1 dia' : `faltam ${days} dias`
  return (
    <p className={`cadastur-banner ${expired ? 'cadastur-banner-expired' : ''}`} role="status">
      {expired
        ? '[Atenção] CADASTUR vencido — regularização pendente.'
        : `[Atenção] CADASTUR próximo do vencimento — ${remaining}.`}
    </p>
  )
}
