import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { testServer } from './testSupport.js'
import { readFile } from 'node:fs/promises'
let server, App, Form, DocumentsPanel, StatusDialog, Field, Feedback, FormErrors, resolveRoute, seed
before(async () => {
  server = await testServer()
  ;({ default: App } = await server.ssrLoadModule('/src/App.jsx'))
  ;({ default: Form } = await server.ssrLoadModule('/src/pages/EstablishmentForm.jsx'))
  ;({ default: DocumentsPanel } = await server.ssrLoadModule('/src/components/DocumentsPanel.jsx'))
  ;({ default: StatusDialog } = await server.ssrLoadModule('/src/components/StatusDialog.jsx'))
  ;({ Field } = await server.ssrLoadModule('/src/components/FormFields.jsx'))
  ;({ Feedback, FormErrors } = await server.ssrLoadModule('/src/components/Feedback.jsx'))
  ;({ resolveRoute } = await server.ssrLoadModule('/src/domain/routing.js'))
  seed = JSON.parse(
    await readFile(
      new URL('../../contratos_api_oto/mocks/seed-data.json', import.meta.url),
      'utf8',
    ),
  )
})
after(async () => {
  await server?.close()
})
const admin = { perfil: 'ADMINISTRADOR' }
const html = (Component, props) => renderToStaticMarkup(React.createElement(Component, props))
const props = () => ({
  mode: 'edit',
  establishment: seed.estabelecimentos[0],
  user: admin,
  categories: seed.categorias_estabelecimento,
  api: {},
})

test('App apresenta carregamento antes da sessão e dos dados', () => {
  const result = html(App)
  assert.match(result, /role="status"/)
  assert.match(result, /Carregando dados da hospedagem/)
  assert.doesNotMatch(result, /<form/)
})
test('cadastro reproduz identificação, vencimentos e ações sem módulos alheios', () => {
  const result = html(App, {
    initialUser: admin,
    initialCategories: seed.categorias_estabelecimento,
  })
  assert.match(result, /Cadastro base do CNPJ/)
  assert.match(result, /Identificação/)
  assert.match(result, /Vencimentos/)
  assert.match(result, /aria-current="page"/)
  assert.match(result, /Observatório de Turismo de Olímpia/)
  assert.match(result, /Salvar e enviar convite/)
  assert.doesNotMatch(result, /Pesquisar Nome|<table|canvas|iframe/)
  assert.match(result, /type="submit"[^>]*>Salvar</)
})
test('campos obrigatórios do contrato estão acessíveis no cadastro', () => {
  const result = html(Form, { ...props(), mode: 'create' })
  for (const name of ['id_categoria', 'nome_fantasia', 'razao_social', 'cnpj', 'endereco']) {
    const tag = result.match(new RegExp(`<(?:input|select)[^>]*name="${name}"[^>]*>`))?.[0]
    assert.ok(tag, name)
    assert.match(tag, /aria-required="true"/)
  }
  assert.match(result, /Dados Operacionais - Hotel/)
  assert.match(result, /Opcional/)
  assert.match(result, /Contatos e informações complementares/)
})
for (const role of ['EDITOR', 'HOTEL'])
  test(`${role} visualiza CNPJ e razão social bloqueados`, () => {
    const result = html(Form, {
      ...props(),
      user: { perfil: role, id_estabelecimento: seed.estabelecimentos[0].id_estabelecimento },
    })
    for (const name of ['cnpj', 'razao_social'])
      assert.match(result.match(new RegExp(`<input[^>]*name="${name}"[^>]*>`))[0], /disabled/)
    assert.doesNotMatch(result.match(/<input[^>]*name="nome_fantasia"[^>]*>/)[0], /disabled/)
  })
test('GESTOR não recebe ações de escrita', () => {
  const result = html(App, {
    initialUser: { perfil: 'GESTOR' },
    initialMode: 'edit',
    initialEstablishment: seed.estabelecimentos[0],
    initialCategories: seed.categorias_estabelecimento,
  })
  assert.match(result, /somente à consulta/)
  assert.doesNotMatch(
    result,
    /type="submit"|Adicionar documento|Substituir arquivo|Inativar hospedagem|Reativar hospedagem/,
  )
  assert.match(result, />Baixar</)
})
test('HOTEL não pode editar registro de outra conta nem receber ações de documentos', () => {
  const result = html(App, {
    initialUser: {
      perfil: 'HOTEL',
      id_estabelecimento: seed.estabelecimentos[1].id_estabelecimento,
    },
    initialMode: 'edit',
    initialEstablishment: seed.estabelecimentos[0],
  })
  assert.doesNotMatch(result, /type="submit"|Adicionar documento|Inativar hospedagem/)
})
test('ADMINISTRADOR recebe manutenção conforme status', () => {
  for (const [index, action] of [
    [0, 'Inativar hospedagem'],
    [2, 'Reativar hospedagem'],
  ])
    assert.match(
      html(App, {
        initialUser: admin,
        initialMode: 'edit',
        initialEstablishment: seed.estabelecimentos[index],
      }),
      new RegExp(action),
    )
})
test('modo HOTEL segue o frame Meus dados e Meu cadastro', () => {
  const result = html(App, {
    initialUser: {
      perfil: 'HOTEL',
      id_estabelecimento: seed.estabelecimentos[0].id_estabelecimento,
    },
    initialMode: 'edit',
    initialEstablishment: seed.estabelecimentos[0],
  })
  assert.match(result, /Meus dados/)
  assert.match(result, /Meu cadastro/)
  assert.match(result, /Salvar Meus Dados/)
  assert.doesNotMatch(result, /<span>Convites|Inativar hospedagem/)
})
test('checklists completos são renderizados conforme schemas de hospedagem', () => {
  const result = html(Form, props())
  for (const name of [
    'meio_hospedagem.total_uh',
    'meio_hospedagem.formas_pagamento',
    'infraestrutura.wifi',
    'infraestrutura.recepcao.internet_sem_fio.possui',
    'acessibilidade.sanitario.barra_apoio',
    'acessibilidade.capacidade_receber_pcd.auditiva_nivel',
  ]) {
    if (name.endsWith('formas_pagamento')) assert.match(result, /Outras formas de pagamento/)
    else assert.ok(result.includes(`name="${name}"`), name)
  }
  assert.doesNotMatch(result, /agencia_turismo|artesanato_comercio|locadora_transporte/)
})
test('cadastro incompleto mantém preenchimento operacional opcional', () => {
  const result = html(Form, { ...props(), establishment: seed.estabelecimentos[3] })
  assert.match(result, /Aguardando preenchimento do hotel/)
  const tag = result.match(/<input[^>]*name="meio_hospedagem.total_uh"[^>]*>/)[0]
  assert.doesNotMatch(tag, /aria-required="true"/)
})
test('estado de envio desabilita ações e informa tecnologia assistiva', () => {
  const result = html(Form, { ...props(), initialStatus: 'submitting' })
  assert.match(result, /aria-busy="true"/)
  assert.match(result, /Salvando…/)
  assert.match(result, /type="submit" disabled=""/)
  assert.match(result.match(/<input[^>]*name="nome_fantasia"[^>]*>/)[0], /disabled/)
})
test('erros vinculados ao campo e resumo acessível', () => {
  const result = html(Form, { ...props(), initialErrors: { nome_fantasia: 'Campo obrigatório.' } })
  assert.match(result, /role="alert"/)
  assert.match(result, /id="field-nome_fantasia-error"/)
  assert.match(result, /aria-describedby="field-nome_fantasia-error"/)
  assert.match(result, /href="#field-nome_fantasia"/)
})
test('mensagens de sucesso e erro têm semântica consistente', () => {
  assert.match(html(Feedback, { kind: 'success', message: 'Salvo com sucesso.' }), /role="status"/)
  assert.match(html(Feedback, { message: 'Falha no envio.' }), /role="alert"/)
  assert.equal(html(FormErrors, {}), '')
})
test('documentos mostram metadados e ações permitidas', () => {
  const result = html(DocumentsPanel, {
    establishment: seed.estabelecimentos[0],
    api: {},
    canManage: true,
  })
  assert.match(result, /alvara-funcionamento.pdf/)
  assert.match(result, /Adicionar documento/)
  assert.match(result, /Substituir arquivo/)
  assert.match(result, /type="file"/)
  assert.match(result, /Baixar Alvará/)
})
test('documentos vazios, indisponíveis e em envio', () => {
  const result = html(DocumentsPanel, {
    establishment: seed.estabelecimentos[3],
    api: {},
    canManage: true,
    initialBusy: true,
    initialError: 'Não foi possível enviar.',
  })
  assert.match(result, /Nenhum documento cadastrado/)
  assert.match(result, /aria-busy="true"/)
  assert.match(result, /role="alert"/)
  assert.match(result, /disabled=""/)
})
test('inativação usa modal com motivo e confirmação; reativação não pede motivo', () => {
  const inactive = html(StatusDialog, {
    establishment: seed.estabelecimentos[0],
    api: {},
    onClose() {},
  })
  assert.match(inactive, /role="dialog" aria-modal="true"/)
  assert.match(inactive, /Justificativa de Remoção/)
  assert.match(inactive, /minLength="3" maxLength="500"/)
  assert.match(inactive, />Cancelar</)
  assert.match(inactive, />Inativar</)
  const active = html(StatusDialog, {
    establishment: seed.estabelecimentos[2],
    api: {},
    onClose() {},
  })
  assert.match(active, /Confirma a reativação/)
  assert.doesNotMatch(active, /<textarea/)
})
test('limpeza de booleano anulável é explícita', () => {
  const result = html(Field, {
    path: 'infraestrutura.wifi',
    schema: { type: ['boolean', 'null'] },
    value: false,
    onChange() {},
  })
  assert.match(result, /Limpar Wi-Fi/)
  assert.doesNotMatch(result, /checked=""/)
})
test('rotas isolam HOTEL antes de consultar API', () => {
  const hotel = { perfil: 'HOTEL', id_estabelecimento: 'own' }
  assert.deepEqual(resolveRoute('', hotel), { mode: 'edit', id: 'own' })
  assert.throws(
    () => resolveRoute('#/estabelecimentos/other/editar', hotel),
    (error) => error.status === 403,
  )
  assert.throws(
    () => resolveRoute('#/estabelecimentos/novo', { perfil: 'EDITOR' }),
    (error) => error.status === 403,
  )
  assert.deepEqual(resolveRoute('#/estabelecimentos/own/editar', hotel), {
    mode: 'edit',
    id: 'own',
  })
  assert.throws(
    () => resolveRoute('#/pesquisas', admin),
    (error) => error.status === 404,
  )
})

test('categoria oferece somente o segmento de hospedagem do MVP', () => {
  const result = html(Form, { ...props(), mode: 'create' })
  assert.match(result, /Meios de hospedagem/)
  assert.doesNotMatch(result, /<option[^>]*>Meios de alimentação|<option[^>]*>Agências/)
})
test('atalhos operacionais não duplicam IDs dos checklists detalhados', () => {
  const result = html(Form, props())
  const ids = [...result.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1])
  assert.equal(new Set(ids).size, ids.length)
  assert.match(result, /Área de Lazer/)
})

test('listas de contatos mostram quebras de linha reais no campo', () => {
  const result = html(Field, {
    path: 'telefones_comerciais',
    schema: { type: 'array', items: { type: 'string' } },
    value: ['1111', '2222'],
    onChange() {},
  })
  assert.ok(result.includes('1111\n2222'))
  assert.ok(!result.includes('1111\\n2222'))
})

test('cadastro não exibe a tag de demonstração', () => {
  const result = html(App, {
    initialUser: admin,
    initialCategories: seed.categorias_estabelecimento,
  })
  assert.doesNotMatch(result, /Demonstração|demo-badge/)
})

test('resumo de validação identifica cada campo obrigatório pelo nome', () => {
  const result = html(FormErrors, { errors: {
    email: 'Campo obrigatório.', senha: 'Campo obrigatório.',
    'meio_hospedagem.total_leitos': 'Informe um número válido.',
  } })
  assert.match(result, /E-mail: Campo obrigatório\./)
  assert.match(result, /Senha: Campo obrigatório\./)
  assert.match(result, /Nº Leitos: Informe um número válido\./)
  assert.match(result, /href="#field-email"/)
  assert.match(result, /href="#field-senha"/)
  assert.match(result, /href="#field-meio_hospedagem-total_leitos"/)
})
