import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { testServer } from './testSupport.js'
let server, domain, documents
before(async () => {
  server = await testServer()
  domain = await server.ssrLoadModule('/src/domain/establishment.js')
  documents = await server.ssrLoadModule('/src/domain/documents.js')
})
after(async () => {
  await server?.close()
})
const admin = { perfil: 'ADMINISTRADOR' }
const item = { id_estabelecimento: 'own' }
const minimal = () => ({
  id_categoria: 1,
  nome_fantasia: 'Hotel Novo',
  razao_social: 'Hotel Novo Ltda.',
  cnpj: '11.222.333/0001-81',
  endereco: 'Rua dos Testes, 123',
})

test('cadastro mínimo não exige hospedagem nem checklists', () => {
  const payload = domain.buildPayload(minimal(), { user: admin })
  assert.deepEqual(domain.validateEstablishment(payload), {})
  assert.equal(payload.cnpj, '11222333000181')
  assert.equal('meio_hospedagem' in payload, false)
})
for (const field of ['id_categoria', 'nome_fantasia', 'razao_social', 'cnpj', 'endereco'])
  test(`cadastro exige ${field}`, () => {
    for (const value of [undefined, null, '']) {
      const payload = { ...minimal(), [field]: value }
      assert.ok(domain.validateEstablishment(payload)[field])
    }
  })
for (const cnpj of ['11.222.333/0001-81', '11222333000181'])
  test(`CNPJ válido: ${cnpj}`, () => assert.equal(domain.validCnpj(cnpj), true))
for (const cnpj of [
  '00.000.000/0000-00',
  '11.222.333/0001-80',
  '1122233300018',
  'abc11222333000181',
])
  test(`CNPJ inválido: ${cnpj}`, () => assert.equal(domain.validCnpj(cnpj), false))
for (const [changes, key] of [
  [{ latitude: 91 }, 'latitude'],
  [{ longitude: -181 }, 'longitude'],
  [{ id_categoria: 0 }, 'id_categoria'],
  [{ nome_fantasia: 'a' }, 'nome_fantasia'],
  [{ email_comercial: 'ruim' }, 'email_comercial'],
  [{ cadastur_status: 'INVALIDO' }, 'cadastur_status'],
  [{ status: 'INATIVO' }, 'status'],
  [{ data_abertura: '2026-02-30' }, 'data_abertura'],
  [{ aceita_pesquisas: 'true' }, 'aceita_pesquisas'],
  [{ meio_hospedagem: { total_uh: -1 } }, 'meio_hospedagem.total_uh'],
  [{ meio_hospedagem: { total_uh: 1.5 } }, 'meio_hospedagem.total_uh'],
  [{ meio_hospedagem: { formas_pagamento: ['PIX', 'PIX'] } }, 'meio_hospedagem.formas_pagamento'],
  [{ acessibilidade: { possui_facilidade_pcd: 'sim' } }, 'acessibilidade.possui_facilidade_pcd'],
])
  test(`validação do contrato: ${key}`, () =>
    assert.ok(domain.validateEstablishment({ ...minimal(), ...changes })[key]))

test('PATCH contém somente campos alterados e mantém false, zero e null', () => {
  const draft = {
    ...domain.draftFrom(minimal()),
    bairro: null,
    aceita_pesquisas: false,
    'meio_hospedagem.total_uh': '0',
  }
  const payload = domain.buildPayload(draft, {
    mode: 'edit',
    dirty: ['bairro', 'aceita_pesquisas', 'meio_hospedagem.total_uh'],
    user: admin,
    establishment: item,
  })
  assert.deepEqual(payload, {
    bairro: null,
    aceita_pesquisas: false,
    meio_hospedagem: { total_uh: 0 },
  })
  assert.deepEqual(domain.validateEstablishment(payload, 'edit'), {})
  assert.ok(domain.validateEstablishment({}, 'edit')[''])
})
test('converte horários e listas sem apagar valores omitidos', () => {
  const payload = domain.buildPayload(
    {
      'meio_hospedagem.checkin_horario': '14:00',
      emails_comerciais: 'um@example.test\ndois@example.test',
    },
    { mode: 'edit', user: admin, establishment: item },
  )
  assert.deepEqual(payload, {
    meio_hospedagem: { checkin_horario: '14:00:00' },
    emails_comerciais: ['um@example.test', 'dois@example.test'],
  })
})
for (const role of ['EDITOR', 'HOTEL'])
  test(`${role} não envia CNPJ nem razão social`, () => {
    for (const field of ['cnpj', 'razao_social'])
      assert.throws(
        () =>
          domain.buildPayload(
            { [field]: null },
            {
              mode: 'edit',
              user: { perfil: role, id_estabelecimento: 'own' },
              establishment: item,
            },
          ),
        /administrador/,
      )
  })
test('permissões de criação, escrita e isolamento HOTEL', () => {
  assert.equal(domain.permissions(admin, item).create, true)
  for (const role of ['EDITOR', 'HOTEL', 'GESTOR'])
    assert.equal(domain.permissions({ perfil: role }, item).create, false)
  assert.equal(domain.permissions({ perfil: 'HOTEL', id_estabelecimento: 'own' }, item).edit, true)
  assert.equal(
    domain.permissions({ perfil: 'HOTEL', id_estabelecimento: 'other' }, item).edit,
    false,
  )
  assert.equal(domain.permissions({ perfil: 'HOTEL' }, item).edit, false)
  assert.equal(domain.permissions({ perfil: 'GESTOR' }, item).edit, false)
  assert.throws(
    () =>
      domain.buildPayload(
        { bairro: 'Novo' },
        { mode: 'edit', user: { perfil: 'GESTOR' }, establishment: item },
      ),
    /permissão/,
  )
})
for (const reason of ['', 'ab', 'x'.repeat(501)])
  test(`motivo inválido com ${reason.length} caracteres`, () =>
    assert.ok(domain.validateReason(reason).motivo_inativacao))
for (const reason of ['abc', 'x'.repeat(500)])
  test(`motivo válido com ${reason.length} caracteres`, () =>
    assert.deepEqual(domain.validateReason(reason), {}))
test('mensagens HTTP e erros por campo', () => {
  for (const status of [401, 403, 404, 409, 413, 415, 422, 0])
    assert.ok(domain.applyApiError({ status }).message)
  assert.equal(
    domain.applyApiError({ status: 409, code: 'CONFLICT' }).fields.cnpj,
    'Já existe uma hospedagem com este CNPJ.',
  )
  assert.deepEqual(
    domain.applyApiError({ status: 422, details: [{ field: 'endereco', issue: 'Inválido' }] })
      .fields,
    { endereco: 'Inválido' },
  )
})
test('upload e substituição usam FormData com arquivo e campos permitidos', () => {
  const file = new File(['%PDF'], 'alvara.pdf', { type: 'application/pdf' })
  const form = documents.documentFormData(
    { tipo_documento: 'ALVARA', data_vencimento: '2099-01-01', numero: null, status: 'REGULAR' },
    file,
  )
  assert.equal(form.get('arquivo').name, 'alvara.pdf')
  assert.equal(form.get('tipo_documento'), 'ALVARA')
  assert.equal(form.has('numero'), false)
  assert.equal(form.has('status'), false)
  assert.deepEqual([...documents.replacementFormData(file).keys()], ['arquivo'])
})
test('valida MIME, extensão, arquivo vazio e limite inclusive', () => {
  assert.equal(
    documents.validateFile(new File(['pdf'], 'a.pdf', { type: 'application/pdf' }), 3),
    null,
  )
  for (const file of [
    null,
    new File([], 'a.pdf', { type: 'application/pdf' }),
    new File(['1234'], 'a.pdf', { type: 'application/pdf' }),
    new File(['x'], 'a.exe', { type: 'application/pdf' }),
    new File(['x'], 'a.txt', { type: 'text/plain' }),
  ])
    assert.ok(documents.validateFile(file, 3))
})
test('metadados de documento respeitam PATCH e datas', () => {
  assert.deepEqual(
    documents.documentPayload(
      { numero: '', data_emissao: '', tipo_documento: 'AVCB' },
      { numero: 'antigo', data_emissao: null, tipo_documento: 'AVCB' },
    ),
    { numero: null },
  )
  assert.ok(documents.validateDocument({ data_vencimento: '2026-02-30' }).data_vencimento)
  assert.ok(documents.validateDocument({}, true)[''])
})
test('nome de download preserva acentos e remove caminhos', () => {
  assert.equal(
    documents.downloadName("attachment; filename*=UTF-8''alvar%C3%A1.pdf", 'documento.pdf'),
    'alvará.pdf',
  )
  assert.equal(documents.downloadName('attachment; filename="../../a.pdf"'), 'a.pdf')
  assert.equal(
    documents.downloadName("attachment; filename*=UTF-8''%zz", 'arquivo.pdf'),
    'arquivo.pdf',
  )
})

test('download cria link temporário e libera URL após o acionamento', () => {
  const events = []
  const browser = {
    URL: {
      createObjectURL: () => 'blob:test',
      revokeObjectURL: (url) => events.push(['revoke', url]),
    },
    document: {
      createElement: () => ({
        click() {
          events.push(['click', this.download, this.href])
        },
        remove() {
          events.push(['remove'])
        },
      }),
      body: { appendChild() {} },
    },
    setTimeout: (callback) => callback(),
  }
  documents.saveDownload(
    { blob: new Blob(['pdf']), disposition: "attachment; filename*=UTF-8''alvar%C3%A1.pdf" },
    'fallback.pdf',
    browser,
  )
  assert.deepEqual(events, [
    ['click', 'alvará.pdf', 'blob:test'],
    ['remove'],
    ['revoke', 'blob:test'],
  ])
})
