import React, { useState } from 'react'
import { Field } from '../components/FormFields.jsx'
import { FormErrors } from '../components/Feedback.jsx'
import { ResourceState } from '../components/OperationsUI.jsx'
import Pagination from '../components/Pagination.jsx'
import InventoryMap from '../components/InventoryMap.jsx'
import { useResource } from '../hooks/operations.js'
import { inventoryDefaults, inventoryErrors } from '../domain/reading.js'
import { schemas } from '../domain/establishment.js'
import { loadInventory } from '../services/reading.js'
export default function InventoryPage({ api, user, initialData = null }) {
  const [draft, setDraft] = useState({ ...inventoryDefaults }),
    [query, setQuery] = useState({ ...inventoryDefaults }),
    [errors, setErrors] = useState({})
  const resource = useResource(
    (options) => loadInventory(api, query, options),
    [api, query],
    initialData,
  )
  const data = resource.data
  const change = (key, value) => {
    setDraft((previous) => ({ ...previous, [key]: value }))
    setErrors({})
  }
  const apply = (event) => {
    event.preventDefault()
    const next = inventoryErrors(draft)
    setErrors(next)
    if (!Object.keys(next).length) setQuery({ ...draft, page: 1 })
  }
  return (
    <>
      <header className="page-heading">
        <h1>Inventário Hospedagem OTO</h1>
      </header>
      <form
        className="inventory-filters"
        onSubmit={apply}
        noValidate
        aria-busy={resource.loading}
      >
        <div className="inventory-search">
          <Field
            path="busca"
            labelOverride="Pesquisar Nome/CNPJ"
            schema={{ type: 'string', maxLength: 120 }}
            value={draft.busca}
            onChange={change}
            error={errors.busca}
          />
          <button className="button button-primary" disabled={resource.loading}>
            Pesquisar
          </button>
          {user.perfil === 'ADMINISTRADOR' && (
            <a className="button button-primary" href="#/estabelecimentos/novo">
              Cadastrar Estabelecimento
            </a>
          )}
        </div>
        <details className="filter-details">
          <summary>Filtros e ordenação</summary>
          <div className="field-grid">
            {[
              [
                'id_categoria',
                'Categoria',
                { type: 'string' },
                data?.categories.map((row) => ({
                  value: row.id_categoria,
                  label: row.nome_categoria,
                })) || [],
              ],
              ['status', 'Status', schemas.StatusEstabelecimento],
              ['cadastur_status', 'Situação Cadastur', schemas.CadasturStatus],
              [
                'aceita_pesquisas',
                'Aceita pesquisas',
                { type: 'string' },
                [
                  { value: 'true', label: 'Sim' },
                  { value: 'false', label: 'Não' },
                ],
              ],
              [
                'page_size',
                'Registros por página',
                { type: 'integer', minimum: 1, maximum: 100 },
              ],
              [
                'ordenar_por',
                'Ordenar por',
                { type: 'string' },
                [
                  { value: 'nome_fantasia', label: 'Nome' },
                  { value: 'criado_em', label: 'Data de cadastro' },
                  { value: 'atualizado_em', label: 'Última atualização' },
                ],
              ],
              [
                'ordem',
                'Ordem',
                { type: 'string' },
                [
                  { value: 'asc', label: 'Crescente' },
                  { value: 'desc', label: 'Decrescente' },
                ],
              ],
            ].map(([path, label, schema, options]) => (
              <Field
                key={path}
                path={path}
                labelOverride={label}
                schema={schema}
                options={options}
                value={draft[path]}
                error={errors[path]}
                onChange={change}
              />
            ))}
          </div>
          <button
            type="button"
            className="button button-secondary"
            onClick={() => {
              setDraft({ ...inventoryDefaults })
              setQuery({ ...inventoryDefaults })
              setErrors({})
            }}
          >
            Limpar filtros
          </button>
        </details>
        <FormErrors errors={errors} />
      </form>
      <ResourceState resource={resource} />
      {data && (
        <>
          <div className="data-table">
            <div className="table-scroll">
              <table>
                <caption className="sr-only">Inventário de hospedagens</caption>
                <thead>
                  <tr>
                    {['Nome do Local', 'CNPJ', 'Localização', 'Status', 'Ações'].map(
                      (label) => (
                        <th key={label} scope="col">
                          {label}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {data.data.map((item) => (
                    <tr key={item.id_estabelecimento}>
                      <td>{item.nome_fantasia}</td>
                      <td>{item.cnpj || 'Não informado'}</td>
                      <td>{item.bairro || 'Não informado'}</td>
                      <td>{item.status === 'ATIVO' ? 'Ativo' : 'Inativo'}</td>
                      <td>
                        <div className="document-actions">
                          <a
                            className="button button-small button-secondary"
                            href={`#/estabelecimentos/${item.id_estabelecimento}`}
                          >
                            Ver detalhes
                          </a>
                          {['ADMINISTRADOR', 'EDITOR'].includes(user.perfil) && (
                            <a
                              className="button button-small button-secondary"
                              href={`#/estabelecimentos/${item.id_estabelecimento}/editar`}
                            >
                              Editar
                            </a>
                          )}
                          <a
                            className="button button-small button-secondary"
                            href={`#/estabelecimentos/${item.id_estabelecimento}/pesquisas`}
                          >
                            Ver Pesquisas
                          </a>
                          {user.perfil === 'ADMINISTRADOR' && (
                            <a
                              className="button button-small button-secondary"
                              href={`#/estabelecimentos/${item.id_estabelecimento}/editar?status=confirmar`}
                            >
                              {item.status === 'ATIVO' ? 'Inativar' : 'Reativar'}
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {!data.data.length && (
                    <tr>
                      <td colSpan="5">Nenhuma hospedagem encontrada.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <Pagination
              pagination={data.pagination}
              busy={resource.loading}
              onPage={(page) => setQuery((previous) => ({ ...previous, page }))}
            />
          </div>
          <InventoryMap items={data.markers} title="MAPA" />
          <p className="muted">Mapa com todos os resultados dos filtros aplicados.</p>
        </>
      )}
    </>
  )
}
