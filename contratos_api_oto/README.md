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

Os mocks ficam em `mocks/responses/<módulo>/<operação>/`. O nome de cada
arquivo é o método HTTP e o status da resposta, por exemplo
`estabelecimentos/inativacao/post-409.json`. Os sucessos de estabelecimento
usam o formato `Estabelecimento`; os erros usam `ErrorResponse` do OpenAPI.

| Arquivo | Operação/status | Fonte do cenário |
| --- | --- | --- |
| `estabelecimentos/inativacao/` | Inativação bem-sucedida e erros | Registro ativo do seed e regra `ATIVO → INATIVO`. |
| `estabelecimentos/reativacao/` | Reativação bem-sucedida e erros | Registro inativo do seed e regra `INATIVO → ATIVO`. |
| `estabelecimentos/cadastro/`, `estabelecimentos/edicao/` | Validação de CNPJ e perfil | Unicidade do CNPJ e permissões de edição. |
| `autenticacao/login/` | Login | Credenciais de demonstração ou credenciais inválidas. |
| `usuarios/criacao/`, `convites/criacao/`, `perfil/consulta/` | Acesso e perfil | Conta pendente, convite e usuário autenticado. |
| `pesquisas-ocupacao/criacao/`, `pesquisas-ocupacao/encerramento/`, `respostas-ocupacao/envio/` | Coleta de ocupação | Pesquisa aberta, encerramento e resposta submetida. |
| `relatorios/geracao/`, `relatorios/download/`, `auditoria/consulta/`, `dashboard/consulta/` | Saídas consolidadas | Relatório concluído/baixado, evento auditado e indicadores. |

## Dicionário de campos do inventário turístico de Olímpia

O contrato `openapi.json` modela integralmente os 9 segmentos visíveis do dicionário da planilha oficial de Olímpia (mais os campos da aba auxiliar), utilizando tipos compostos (`SimOuNaoComDetalhe`, `TextoComIndicacao`, `DataOuAno`, `PublicoPrincipalPercentual`, `AtendimentoIdiomas` e `ItemMobiliarioQuantidade`) e a matriz compartilhada `AcessibilidadeDetalhada`:

1. **Meios de hospedagem**: `MeioHospedagem` + `InfraestruturaHospedagem` (`uh_detalhes`, `recepcao`, `alimentos_bebidas`, `eventos`, `recreacao`).
2. **Meios de alimentação e bebidas**: `MeioAlimentacaoBebidas` (`alimentacao_bebidas`).
3. **Agências e operadoras de turismo**: `AgenciaOperadoraTurismo` (`agencia_turismo`).
4. **Atrativos, lazer e entretenimento**: `AtrativoLazerEntretenimento` (`atrativo_lazer`, com `visitacao`, `instalacoes_gerais` / indicadores ODS e `acervo`).
5. **Locadoras de veículos e transporte turístico**: `LocadoraTransporteTuristico` (`locadora_transporte`).
6. **Espaços para eventos**: `EspacoEventos` (`espaco_eventos`, com `subtipos`, `espaco`, `estacionamento`, `instalacoes_espaco`, `mobiliario_eventos`, `equipamentos_servicos`, `seguranca` e `energia_eletrica`).
7. **Organizadores e serviços para eventos**: `OrganizadorServicosEventos` (`organizador_eventos`).
8. **Guias de turismo**: `GuiaTurismo` (`guia_turismo`, com suporte a `cpf` e `categorias`).
9. **Artesanato e comércio diferenciado**: `ArtesanatoComercio` (`artesanato_comercio`).
