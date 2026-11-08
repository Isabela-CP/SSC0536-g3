import React from 'react'
import { useResource } from '../hooks/operations.js'
import { ResourceState } from '../components/OperationsUI.jsx'
import DocumentsPanel from '../components/DocumentsPanel.jsx'
import InventoryMap from '../components/InventoryMap.jsx'
import { flatFields, displayValue } from '../domain/reading.js'
import { permissions } from '../domain/establishment.js'
export default function EstablishmentDetail({ api, user, id, initialData = null }) {
  const resource = useResource(
    (options) => api.establishment(id, options),
    [api, id],
    initialData,
  )
  const item = resource.data
  const basic =
    item &&
    Object.fromEntries(
      Object.entries(item).filter(
        ([key]) =>
          ![
            'id_estabelecimento',
            'id_categoria',
            'categoria',
            'meio_hospedagem',
            'infraestrutura',
            'acessibilidade',
            'documentos',
            'id_origem',
          ].includes(key),
      ),
    )
  return (
    <>
      <header className="page-heading">
        <h1>{item?.nome_fantasia || 'Dados da hospedagem'}</h1>
        <div className="document-actions">
          <a className="button button-secondary" href="#/inventario">
            Voltar ao inventário
          </a>
          {item && permissions(user, item).edit && (
            <a className="button button-primary" href={`#/estabelecimentos/${id}/editar`}>
              Editar dados
            </a>
          )}
        </div>
      </header>
      <ResourceState resource={resource} />
      {item && (
        <>
          <p className="detail-category">
            {item.categoria?.nome_categoria} · {item.status === 'ATIVO' ? 'Ativo' : 'Inativo'}
          </p>
          {[
            [
              'Dados básicos e contatos',
              Object.fromEntries(
                Object.entries(basic).filter(([key]) =>
                  [
                    'nome_fantasia',
                    'razao_social',
                    'cnpj',
                    'endereco',
                    'bairro',
                    'status',
                    'aceita_pesquisas',
                    'cadastur_status',
                    'possui_cadastur',
                    'vencimento_cadastur',
                    'email_comercial',
                    'telefone_comercial',
                  ].includes(key),
                ),
              ),
            ],
            [
              'Contatos e informações complementares',
              Object.fromEntries(
                Object.entries(basic).filter(
                  ([key]) =>
                    ![
                      'nome_fantasia',
                      'razao_social',
                      'cnpj',
                      'endereco',
                      'bairro',
                      'status',
                      'aceita_pesquisas',
                      'cadastur_status',
                      'possui_cadastur',
                      'vencimento_cadastur',
                      'email_comercial',
                      'telefone_comercial',
                    ].includes(key),
                ),
              ),
            ],
            ['Dados de hospedagem', item.meio_hospedagem],
            ['Infraestrutura', item.infraestrutura],
            ['Acessibilidade', item.acessibilidade],
          ].map(([label, value]) => (
            <details
              className="form-card read-detail"
              key={label}
              open={label === 'Dados básicos e contatos' || label === 'Dados de hospedagem'}
            >
              <summary>{label}</summary>
              {value ? (
                <dl className="detail-fields">
                  {flatFields(value).map((field) => (
                    <div key={field.path}>
                      <dt>{field.label}</dt>
                      <dd>{displayValue(field.value)}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p>Dados ainda não informados.</p>
              )}
            </details>
          ))}
          <DocumentsPanel establishment={item} api={api} canManage={false} />
          <a className="button button-secondary" href={`#/estabelecimentos/${id}/pesquisas`}>
            Ver Pesquisas
          </a>
          <InventoryMap items={[item]} />
        </>
      )}
    </>
  )
}
