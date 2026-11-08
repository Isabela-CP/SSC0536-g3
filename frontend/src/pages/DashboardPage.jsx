import React from 'react'
import { useResource } from '../hooks/operations.js'
import { ResourceState } from '../components/OperationsUI.jsx'
import DataTable from '../components/DataTable.jsx'
import InventoryMap from '../components/InventoryMap.jsx'
import { loadDashboard } from '../services/reading.js'
import { dateLabel } from '../domain/reading.js'
export default function DashboardPage({ api, initialData = null }) {
  const resource = useResource((options) => loadDashboard(api, options), [api], initialData)
  const data = resource.data
  return (
    <>
      <header className="page-heading">
        <h1>Dashboard OTO</h1>
      </header>
      <ResourceState resource={resource} />
      {data && (
        <>
          <div className="stat-grid dashboard-stats">
            {[
              ['Total Empresas', data.indicadores.total_empresas],
              ['Leitos', data.indicadores.total_leitos],
              ['Ativas', data.indicadores.estabelecimentos_ativos],
            ].map(([label, value]) => (
              <article className="stat-card" key={label}>
                <h2>
                  {label}
                  {label === 'Leitos' &&
                    !!data.indicadores.leitos_nao_informados &&
                    ' (parcial)'}
                </h2>
                <strong>{value}</strong>
                {label === 'Leitos' && !!data.indicadores.leitos_nao_informados && (
                  <small className="stat-note">
                    {data.indicadores.leitos_nao_informados} ficha(s) sem dado
                  </small>
                )}
              </article>
            ))}
          </div>
          <div className="dashboard-grid">
            <section className="dashboard-alerts">
              <h2>ALERTA DE VENCIMENTOS CADASTUR</h2>
              <DataTable
                caption="Vencimentos Cadastur"
                pageSize={3}
                rows={data.alertas_cadastur}
                empty="Nenhum vencimento Cadastur informado."
                columns={[
                  {
                    key: 'nome_fantasia',
                    label: 'Empresa',
                    render: (row) => (
                      <a href={`#/estabelecimentos/${row.id_estabelecimento}`}>
                        {row.nome_fantasia}
                      </a>
                    ),
                  },
                  { key: 'data', label: 'Data', render: (row) => dateLabel(row.data) },
                  {
                    key: 'dias_ate_vencimento',
                    label: 'Dias até o vencimento',
                    render: (row) =>
                      row.dias_ate_vencimento < 0
                        ? `Vencido há ${-row.dias_ate_vencimento} dia(s)`
                        : row.dias_ate_vencimento,
                  },
                ]}
              />
              <p className="muted">
                Todos os vencimentos informados, do mais antigo ao mais recente.
              </p>
            </section>
            <InventoryMap items={data.markers} title="MAPA DA CIDADE" />
          </div>
        </>
      )}
    </>
  )
}
