# Contratos e mocks — Inventário OTO

`openapi.json` é o contrato estático do MVP. Os arquivos em `mocks/` são
respostas de referência para desenvolvimento e testes de integração de
consumidores; eles não implementam rotas nem persistência.

## Transição de status

Somente `ADMINISTRADOR` pode alterar o status de um estabelecimento.

| Operação | Origem | Destino | Resultado fora da transição |
| --- | --- | --- | --- |
| `POST /estabelecimentos/{id}/inativacao` | `ATIVO` | `INATIVO` | `409` com `ESTABELECIMENTO_JA_INATIVO` |
| `POST /estabelecimentos/{id}/reativacao` | `INATIVO` | `ATIVO` | `409` com `ESTABELECIMENTO_JA_ATIVO` |

A inativação é lógica: conserva o registro e exige `motivo_inativacao` entre
3 e 500 caracteres. Motivo ausente, curto ou longo retorna `422` com
`details[].field = "motivo_inativacao"`.

`GESTOR` não edita. `EDITOR` e `HOTEL` não podem alterar CNPJ nem razão
social; `HOTEL` só pode atuar sobre sua própria hospedagem.

## Mocks de respostas

Os mocks abaixo ficam em `mocks/responses/`. Os sucessos usam o formato
`Estabelecimento`; os erros usam `ErrorResponse` do OpenAPI.

| Arquivo | Operação/status | Fonte do cenário |
| --- | --- | --- |
| `post-estabelecimento-inativacao-200.json` | Inativação bem-sucedida | Registro ativo `11111111-1111-4111-8111-111111111111` do seed. |
| `post-estabelecimento-reativacao-200.json` | Reativação bem-sucedida | Registro inativo `33333333-3333-4333-8333-333333333333` do seed. |
| `post-estabelecimento-inativacao-401.json`, `post-estabelecimento-reativacao-401.json` | Sem autenticação | Regra de autenticação do contrato. |
| `post-estabelecimento-inativacao-403.json`, `post-estabelecimento-reativacao-403.json` | Perfil não autorizado | Apenas `ADMINISTRADOR` pode transicionar status. |
| `post-estabelecimento-inativacao-404.json`, `post-estabelecimento-reativacao-404.json` | Registro inexistente | Identificador fictício ausente do seed. |
| `post-estabelecimento-inativacao-409.json` | Inativar já inativo | Regra `INATIVO → INATIVO` inválida. |
| `post-estabelecimento-reativacao-409.json` | Reativar já ativo | Regra `ATIVO → ATIVO` inválida. |
| `post-estabelecimento-inativacao-422-*.json` | Motivo ausente, curto ou longo | Limites `minLength: 3` e `maxLength: 500`. |
| `post-estabelecimentos-422-cnpj-invalido.json` | CNPJ inválido no cadastro | Validação de dígitos verificadores. |
| `post-estabelecimentos-409-cnpj-duplicado.json` | CNPJ duplicado no cadastro | CNPJ já existente no seed: `54.839.271/0001-64`. |
| `patch-estabelecimento-422-cnpj-invalido.json` | CNPJ inválido na atualização | Validação de dígitos verificadores. |
| `patch-estabelecimento-403-perfil.json` | Edição bloqueada por perfil | `GESTOR` é somente leitura. |
