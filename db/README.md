# Banco de Dados — Inventário OTO

Camada de persistência relacional do Inventário de Meios de Hospedagem (disciplina SSC0536). Modelada em **PostgreSQL**, tendo como fonte única de verdade o contrato OpenAPI em [`../contratos_api_oto/openapi.json`](../contratos_api_oto/openapi.json).

---

## 1. Estrutura de Arquivos

```
db/
├── migrations/
│   ├── 001_core_inventory.sql       # Núcleo relacional: categorias, estabelecimentos, meio_hospedagem, documentos
│   └── 002_operational_tables.sql  # Operacional: autenticação, convites, pesquisas, respostas, logs, relatórios
├── seeds/
│   └── 001_dev_seed.sql            # Povoamento fictício de desenvolvimento (idempotente)
└── README.md                       # Documentação da arquitetura e decisões de mapeamento
```

---

## 2. Ordem de Execução

As migrations e seeds foram estruturadas em ordem estrita de dependência de chaves estrangeiras (`FK`):

1. **`db/migrations/001_core_inventory.sql`**
   * Cria extensões (`pgcrypto`), tipos enumerados (`status_estabelecimento`, `cadastur_status`, `tipo_hospedagem`, `tipo_documento`, `status_documento`).
   * Cria as tabelas `categorias_estabelecimento`, `estabelecimentos`, `meio_hospedagem` e `documentos_controle`.
   * Cria triggers de `atualizado_em` e índices estratégicos (B-Tree e GIN).
   * Insere o seed base da categoria `1 - Meios de hospedagem` com `ON CONFLICT DO UPDATE`.

2. **`db/migrations/002_operational_tables.sql`**
   * Cria tipos enumerados de usuários, convites, pesquisas e relatórios.
   * Cria tabelas operacionais referenciando `estabelecimentos(id_estabelecimento) UUID`.

3. **`db/seeds/001_dev_seed.sql`**
   * Povoa o catálogo completo de categorias (1 a 9).
   * Povoa os 4 estabelecimentos fictícios do mock oficial (`seed-data.json`), incluindo o caso de cadastro inicial incompleto.
   * Povoa os meios de hospedagem, documentos de controle, usuários, convites, pesquisas, respostas, auditoria e relatórios.
   * Totalmente idempotente (`ON CONFLICT DO NOTHING`).

### Execução via `psql` (exemplo)

```bash
# Executando no banco configurado (ex: oto_db)
psql -d oto_db -f db/migrations/001_core_inventory.sql
psql -d oto_db -f db/migrations/002_operational_tables.sql
psql -d oto_db -f db/seeds/001_dev_seed.sql
```

---

## 3. Decisões de Mapeamento (OpenAPI ➔ SQL)

### [M1] Identificação e Chaves Primárias
* **`estabelecimentos`**: Chave primária `UUID` gerada automaticamente com `gen_random_uuid()`. Garante conformidade direta com o OpenAPI (`format: uuid`) e desacoplamento de sequências previsíveis.
* **`categorias_estabelecimento`**: Chave `SERIAL / INTEGER` alinhada ao catálogo de códigos inteiros (1 a 9).

### [M2] Modelagem 1:1 de `meio_hospedagem`
* **Abordagem adotada**: Chave primária compartilhada (`id_estabelecimento UUID PRIMARY KEY REFERENCES estabelecimentos (id_estabelecimento)`).
* **Justificativa**:
  * Garante integridade referencial e cardinalidade estrita 1:1 no nível do SGBD sem sobrecarga de colunas ou chaves artificiais excedentes.
  * Permite que um estabelecimento seja criado em etapas (cadastro inicial apenas com dados de identificação/endereço, sem linha correspondente em `meio_hospedagem` ou com campos operacionais nulos).

### [M3] Unicidade e Validação de CNPJ
* `estabelecimentos.cnpj` possui restrição `UNIQUE (cnpj)` e `NOT NULL`.
* O contrato OpenAPI exige CNPJ no payload mínimo de criação (`EstabelecimentoCreate.required: [cnpj, ...]`), garantindo que não haja duplicidades de pessoas jurídicas na base.

### [M4] Inativação Lógica (*Soft Delete*)
* Para preservar integridade histórica de pesquisas estatísticas, auditoria e relatórios, não é permitida a exclusão física (`DELETE`) de estabelecimentos com histórico.
* Coluna `status status_estabelecimento NOT NULL DEFAULT 'ATIVO'`.
* Quando inativado, registram-se `motivo_inativacao` e `inativado_em`.

### [M5] Checklists Flexíveis em `JSONB` vs. Colunas Relacionais
* **Checklists extensos (Infraestrutura e Acessibilidade)**:
  * Acessibilidade física/sensorial, facilidades de lazer, recepção e alimentação possuem dezenas de itens detalhados.
  * Modelar cada item como coluna booleana tornaria a tabela excessivamente larga e rígida a alterações de formulário.
  * Adotou-se `infraestrutura JSONB NOT NULL DEFAULT '{}'::jsonb` e `acessibilidade JSONB NOT NULL DEFAULT '{}'::jsonb`, com índices `GIN` para consultas flexíveis e `CHECK (jsonb_typeof(...) = 'object')`.
* **Colunas Relacionais Dedicadas (Métricas e Relatórios)**:
  * `tipo_hospedagem`, `total_uh`, `total_leitos`, `uh_pcd`, `func_fixos`, `func_temporarios`, `diaria_media`, `cadastur_status`, `latitude`, `longitude` e `bairro` são colunas relacionais nativas.
  * Permitem índices B-Tree, agregações (`SUM`, `AVG`), filtros de faixa (`BETWEEN`, `>=`, `<=`) e ordenação com alta performance em relatórios da prefeitura/OTO.

### [M6] Formas de Pagamento como Lista
* No OpenAPI: `formas_pagamento: array[string]` (suporta códigos fixos como `PIX`, `CREDITO`, `DEBITO`, `DINHEIRO` e descritivos legados).
* Modelado como `formas_pagamento JSONB NOT NULL DEFAULT '[]'::jsonb` com `CHECK (jsonb_typeof(formas_pagamento) = 'array')` e índice `GIN`.

### [M7] Documentos de Controle e Metadados de Arquivo
* Tabela `documentos_controle` atende ao ciclo de vida REST em duas etapas:
  1. Criação do metadado do documento (`POST /estabelecimentos/{id}/documentos`): exige `tipo_documento` e `data_vencimento`.
  2. Upload físico do arquivo (`POST /.../arquivo` via multipart): preenche `nome_arquivo`, `content_type` (MIME type), `tamanho_bytes`, `checksum_sha256`, `caminho_storage` (referência interna no storage) e `enviado_em`.
* Colunas de arquivo físico admitem `NULL` na criação inicial, tornando o fluxo assíncrono e consistente.

### [M8] Suporte a Cadastro Inicial Incompleto
* Conforme especificação em `EstabelecimentoCreate`:
  * Campos mínimos obrigatórios: `id_categoria`, `nome_fantasia`, `razao_social`, `cnpj`, `endereco`.
  * Todos os demais campos operacionais e de capacidade admitem nulo ou possuem valores default adequados, permitindo salvar rascunhos e cadastros parciais (ex.: registro `44444444-4444-4444-8444-444444444444`).

---

## 4. Índices Estratégicos Criados

| Tabela | Índice | Tipo | Propósito |
| :--- | :--- | :--- | :--- |
| `estabelecimentos` | `idx_estabelecimentos_cnpj` | B-Tree | Busca exata e integridade de CNPJ |
| `estabelecimentos` | `idx_estabelecimentos_nome_fantasia` | B-Tree | Filtros e busca textual da API |
| `estabelecimentos` | `idx_estabelecimentos_razao_social` | B-Tree | Filtros e busca textual da API |
| `estabelecimentos` | `idx_estabelecimentos_categoria` | B-Tree | `JOIN` e filtros por segmento |
| `estabelecimentos` | `idx_estabelecimentos_status` | B-Tree | Filtro rápido por ativos/inativos |
| `estabelecimentos` | `idx_estabelecimentos_bairro` | B-Tree | Agrupamento geográfico e relatórios |
| `estabelecimentos` | `idx_estabelecimentos_coords` | B-Tree (parcial) | Filtro geoespacial de latitude/longitude |
| `estabelecimentos` | `idx_estabelecimentos_pesquisas` | B-Tree (parcial) | Seleção de público-alvo para pesquisas ativas |
| `meio_hospedagem` | `idx_meio_hospedagem_tipo` | B-Tree | Filtro por tipo de hospedagem |
| `meio_hospedagem` | `idx_meio_hospedagem_total_uh` | B-Tree | Ordenação e filtros por capacidade |
| `meio_hospedagem` | `idx_meio_hospedagem_infraestrutura_gin` | GIN | Consultas eficientes em itens de infraestrutura |
| `meio_hospedagem` | `idx_meio_hospedagem_formas_pagamento_gin` | GIN | Consultas sobre formas de pagamento aceitas |
| `documentos_controle` | `idx_documentos_estab` | B-Tree | `JOIN` e listagem de documentos por hotel |
| `documentos_controle` | `idx_documentos_vencimento` | B-Tree | Monitoramento de prazos e alertas de vencimento |
