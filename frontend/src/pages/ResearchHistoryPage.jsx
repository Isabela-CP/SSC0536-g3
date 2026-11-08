import React from 'react'
import { useResource } from '../hooks/operations.js'
import { ResourceState } from '../components/OperationsUI.jsx'
import DataTable from '../components/DataTable.jsx'
import { dateLabel, surveyHistory } from '../domain/reading.js'
import { loadRecipients } from '../domain/operations.js'
export default function ResearchHistoryPage({
  api,
  establishmentId,
  surveyId,
  initialData = null,
}) {
  const resource = useResource(
    async (options) => {
      const [surveys, history, subject] = await Promise.all([
        api.surveys(options),
        api.responseHistory(options),
        establishmentId
          ? api.establishment(establishmentId, options)
          : loadRecipients(api, options),
      ])
      if (surveyId && !surveys.data.some((row) => row.id_pesquisa === surveyId))
        throw new Error('Pesquisa não encontrada.')
      return { surveys: surveys.data, history: history.data, subject }
    },
    [api, establishmentId, surveyId],
    initialData,
  )
  const data = resource.data
  const selected =
    data &&
    surveyHistory(data.surveys, data.history, establishmentId).filter(
      (row) => !surveyId || row.id_pesquisa === surveyId,
    )
  return (
    <>
      <header className="page-heading">
        <h1>
          {establishmentId
            ? `Perfil: ${data?.subject.nome_fantasia || 'Hospedagem'}`
            : 'Respostas da pesquisa'}
        </h1>
        <a
          className="button button-secondary"
          href={establishmentId ? '#/inventario' : '#/pesquisas'}
        >
          Voltar
        </a>
      </header>
      <ResourceState resource={resource} />
      {data && (
        <>
          {selected
            .filter(
              (row) => row.status === 'ABERTA' && !row.responses.length && establishmentId,
            )
            .map((row) => (
              <section className="form-card" key={row.id_pesquisa}>
                <strong>{row.titulo}: Aguardando Resposta</strong>
              </section>
            ))}
          <h2>{establishmentId ? 'Histórico de Pesquisas' : selected[0]?.titulo}</h2>
          {establishmentId ? (
            <DataTable
              caption="Histórico da hospedagem"
              rows={selected}
              columns={[
                {
                  key: 'data',
                  label: 'Data',
                  render: (row) =>
                    row.responses.length
                      ? dateLabel(row.responses[0].enviada_em)
                      : 'Sem resposta',
                },
                {
                  key: 'periodo',
                  label: 'Período',
                  render: (row) =>
                    `${dateLabel(row.periodo_inicio)} a ${dateLabel(row.periodo_fim)}`,
                },
                {
                  key: 'expectativa',
                  label: 'Expectativa (%)',
                  render: (row) =>
                    row.tipo === 'EXPECTATIVA' && row.responses.length
                      ? `${row.responses[0].dados.taxa_ocupacao}%`
                      : '—',
                },
                {
                  key: 'realizado',
                  label: 'Realizado (%)',
                  render: (row) =>
                    row.tipo === 'CONSOLIDADO' && row.responses.length
                      ? `${row.responses[0].dados.taxa_ocupacao}%`
                      : '—',
                },
                { key: 'status', label: 'Status' },
              ]}
            />
          ) : (
            <DataTable
              caption="Respostas por hospedagem"
              rows={selected[0]?.responses || []}
              columns={[
                {
                  key: 'hospedagem',
                  label: 'Hospedagem',
                  render: (row) => (
                    <a href={`#/estabelecimentos/${row.id_estabelecimento}/pesquisas`}>
                      {data.subject.find(
                        (item) => item.id_estabelecimento === row.id_estabelecimento,
                      )?.nome_fantasia || 'Hospedagem não disponível'}
                    </a>
                  ),
                },
                {
                  key: 'enviada_em',
                  label: 'Data',
                  render: (row) => dateLabel(row.enviada_em),
                },
                {
                  key: 'taxa',
                  label: 'Ocupação (%)',
                  render: (row) => `${row.dados.taxa_ocupacao}%`,
                },
              ]}
            />
          )}
        </>
      )}
    </>
  )
}
