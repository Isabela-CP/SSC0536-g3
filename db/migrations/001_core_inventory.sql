-- ============================================================
-- 001_core_inventory.sql
-- Núcleo relacional do inventário: categorias de estabelecimento,
-- estabelecimentos, meio_hospedagem (relação 1:1) e documentos_controle.
--
-- Fonte de contrato: contratos_api_oto/openapi.json
--
-- Ordem de execução do banco de dados:
--   1. 001_core_inventory.sql       (este arquivo)
--   2. 002_operational_tables.sql  (autenticação, pesquisas, auditoria)
--   3. 001_dev_seed.sql            (seeds fictícios de desenvolvimento)
--
-- Decisões de modelagem e mapeamento OpenAPI -> SQL:
--
-- [M1] Chave primária de estabelecimentos como UUID:
--      Alinhado ao parâmetro id_estabelecimento (format: uuid) do OpenAPI
--      e à chave estrangeira já referenciada em 002_operational_tables.sql.
--      Utiliza gen_random_uuid() nativo do PostgreSQL.
--
-- [M2] Relação 1:1 entre estabelecimentos e meio_hospedagem:
--      Modelado com chave primária compartilhada:
--        meio_hospedagem.id_estabelecimento UUID PRIMARY KEY
--          REFERENCES estabelecimentos (id_estabelecimento)
--      Isso elimina chave artificial desnecessária, garante a cardinalidade
--      exata 1:1 no nível do banco e permite que o cadastro inicial
--      seja criado sem meio_hospedagem (ou com dados parciais).
--
-- [M3] Unicidade e integridade do CNPJ:
--      Restrição UNIQUE(cnpj) em estabelecimentos. O CNPJ é obrigatório
--      no contrato (EstabelecimentoCreate.required: [cnpj, ...]).
--      Índice B-Tree para buscas exatas e limpas.
--
-- [M4] Inativação lógica (Soft Delete):
--      status_estabelecimento enum ('ATIVO', 'INATIVO'). Não há exclusão
--      física de estabelecimentos cadastrados; a inativação persiste
--      motivo_inativacao e inativado_em, preservando o histórico de auditoria
--      e pesquisas anteriores.
--
-- [M5] Checklists flexíveis em JSONB (Infraestrutura e Acessibilidade):
--      Em vez de dezenas de colunas booleanas frágeis a alterações de layout,
--      a infraestrutura detalhada (comodidades UH, recepção, A&B, lazer,
--      eventos e acessibilidade) é armazenada em colunas JSONB com
--      default '{}'::jsonb e constraints que validam tipo de objeto JSON.
--      Índices GIN foram criados para possibilitar consultas eficientes por chave/valor.
--
-- [M6] Formas de pagamento como lista JSON:
--      Preservado como JSONB array (formas_pagamento JSONB NOT NULL DEFAULT '[]'::jsonb),
--      atendendo diretamente a especificação do contrato OpenAPI (array de strings)
--      com constraint jsonb_typeof = 'array'.
--
-- [M7] Métricas em colunas relacionais:
--      tipo_hospedagem, total_uh, total_leitos, uh_pcd, func_fixos,
--      func_temporarios, diaria_media, cadastur_status, coordenadas (latitude/longitude)
--      e bairro permanecem como colunas relacionais nativas com índices B-Tree,
--      assegurando máxima velocidade para filtros, agrupamentos e relatórios estatísticos.
--
-- [M8] Documentos de controle e metadados de arquivo:
--      documentos_controle gerencia alvará, AVCB e vigilância sanitária.
--      Permite cadastro inicial do documento com datas e metadados mínimos
--      (data_vencimento obrigatória no contrato), enquanto colunas do arquivo
--      físico (nome_arquivo, content_type, tamanho_bytes, checksum_sha256,
--      caminho_storage, enviado_em) são preenchidas após upload multipart.
--
-- [M9] Suporte a cadastro inicial incompleto:
--      Apenas id_categoria, nome_fantasia, razao_social, cnpj e endereco
--      são estritamente NOT NULL em estabelecimentos. Todos os dados operacionais
--      de capacidade, horários e documentos admitem nulo para viabilizar
--      cadastros em etapas.
--
-- [M10] Seed idempotente:
--       Garante a existência da categoria 'Meios de hospedagem' (id=1)
--       com ON CONFLICT DO UPDATE/NOTHING.
-- ============================================================

BEGIN;

-- ──────────────────────────────────────────────────────────
-- EXTENSÕES
-- ──────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ──────────────────────────────────────────────────────────
-- TIPOS ENUMERADOS
-- ──────────────────────────────────────────────────────────

CREATE TYPE status_estabelecimento AS ENUM (
    'ATIVO',
    'INATIVO'
);

CREATE TYPE cadastur_status AS ENUM (
    'OBRIGATORIO',
    'OPCIONAL',
    'NAO_CONSTA'
);

CREATE TYPE tipo_hospedagem AS ENUM (
    'HOTEL',
    'POUSADA',
    'RESORT',
    'FLAT',
    'HOSTEL',
    'HOTEL_FAZENDA'
);

CREATE TYPE tipo_documento AS ENUM (
    'ALVARA',
    'AVCB',
    'VIGILANCIA_SANITARIA'
);

CREATE TYPE status_documento AS ENUM (
    'REGULAR',
    'A_VENCER',
    'VENCIDO'
);

-- ──────────────────────────────────────────────────────────
-- FUNÇÃO AUXILIAR DE TIMESTAMP
-- ──────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION set_atualizado_em()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ──────────────────────────────────────────────────────────
-- CATEGORIAS DE ESTABELECIMENTO
-- ──────────────────────────────────────────────────────────

CREATE TABLE categorias_estabelecimento (
    id_categoria    SERIAL          PRIMARY KEY,
    nome_categoria  VARCHAR(100)    NOT NULL,
    descricao       TEXT,
    criado_em       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_categorias_nome
        UNIQUE (nome_categoria)
);

CREATE TRIGGER trg_categorias_atualizado_em
    BEFORE UPDATE ON categorias_estabelecimento
    FOR EACH ROW
    EXECUTE FUNCTION set_atualizado_em();

-- ──────────────────────────────────────────────────────────
-- ESTABELECIMENTOS
-- ──────────────────────────────────────────────────────────

CREATE TABLE estabelecimentos (
    id_estabelecimento          UUID                    PRIMARY KEY DEFAULT gen_random_uuid(),
    id_categoria                INTEGER                 NOT NULL
        REFERENCES categorias_estabelecimento (id_categoria)
        ON DELETE RESTRICT,
    nome_fantasia               VARCHAR(160)            NOT NULL,
    razao_social                VARCHAR(200)            NOT NULL,
    cnpj                        VARCHAR(20)             NOT NULL,
    status                      status_estabelecimento  NOT NULL DEFAULT 'ATIVO',
    motivo_inativacao           TEXT,
    inativado_em                TIMESTAMPTZ,
    cnae                        VARCHAR(20),
    cnae_secundario             VARCHAR(255),
    data_abertura               DATE,
    endereco                    VARCHAR(300)            NOT NULL,
    bairro                      VARCHAR(120),
    localizacao                 VARCHAR(150),
    regiao                      VARCHAR(100),
    latitude                    NUMERIC(10, 7),
    longitude                   NUMERIC(10, 7),
    cadastur_status             cadastur_status         NOT NULL DEFAULT 'OBRIGATORIO',
    possui_cadastur             BOOLEAN                 NOT NULL DEFAULT FALSE,
    numero_cadastur             VARCHAR(80),
    vencimento_cadastur         DATE,
    tipo_cadastur               VARCHAR(80),
    aceita_pesquisas            BOOLEAN                 NOT NULL DEFAULT TRUE,
    telefone_comercial          VARCHAR(30),
    email_comercial             VARCHAR(254),
    telefone_pesquisas          VARCHAR(30),
    email_pesquisas             VARCHAR(254),
    telefones_comerciais        JSONB                   NOT NULL DEFAULT '[]'::jsonb,
    emails_comerciais           JSONB                   NOT NULL DEFAULT '[]'::jsonb,
    site                        VARCHAR(255),
    facebook                    VARCHAR(255),
    instagram                   VARCHAR(255),
    redes_sociais               JSONB                   NOT NULL DEFAULT '[]'::jsonb,
    rede_ou_franquia            VARCHAR(150),
    contato                     VARCHAR(150),
    cargo_contato               VARCHAR(100),
    proprietarios               TEXT,
    inventariado                BOOLEAN                 NOT NULL DEFAULT FALSE,
    id_origem                   VARCHAR(50),
    cpf                         VARCHAR(14),
    classificacao               VARCHAR(100),
    observacoes                 TEXT,
    descricao_geral             TEXT,
    sobre_area_ab               TEXT,
    sobre_area_recreacao_lazer  TEXT,
    sobre_facilidades_pcd       TEXT,
    sobre_eventos               TEXT,
    responsavel_preenchimento   JSONB,
    criado_em                   TIMESTAMPTZ             NOT NULL DEFAULT NOW(),
    atualizado_em               TIMESTAMPTZ             NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_estabelecimentos_cnpj
        UNIQUE (cnpj),

    CONSTRAINT ck_estabelecimentos_latitude
        CHECK (latitude IS NULL OR (latitude >= -90.0 AND latitude <= 90.0)),

    CONSTRAINT ck_estabelecimentos_longitude
        CHECK (longitude IS NULL OR (longitude >= -180.0 AND longitude <= 180.0)),

    CONSTRAINT ck_estabelecimentos_telefones_array
        CHECK (jsonb_typeof(telefones_comerciais) = 'array'),

    CONSTRAINT ck_estabelecimentos_emails_array
        CHECK (jsonb_typeof(emails_comerciais) = 'array'),

    CONSTRAINT ck_estabelecimentos_redes_array
        CHECK (jsonb_typeof(redes_sociais) = 'array'),

    CONSTRAINT ck_estabelecimentos_status_inativo
        CHECK (status = 'ATIVO' OR (status = 'INATIVO' AND inativado_em IS NOT NULL))
);

CREATE TRIGGER trg_estabelecimentos_atualizado_em
    BEFORE UPDATE ON estabelecimentos
    FOR EACH ROW
    EXECUTE FUNCTION set_atualizado_em();

-- Índices estratégicos para estabelecimentos
CREATE INDEX idx_estabelecimentos_categoria       ON estabelecimentos (id_categoria);
CREATE INDEX idx_estabelecimentos_status          ON estabelecimentos (status);
CREATE INDEX idx_estabelecimentos_cnpj            ON estabelecimentos (cnpj);
CREATE INDEX idx_estabelecimentos_nome_fantasia   ON estabelecimentos (nome_fantasia);
CREATE INDEX idx_estabelecimentos_razao_social    ON estabelecimentos (razao_social);
CREATE INDEX idx_estabelecimentos_bairro          ON estabelecimentos (bairro);
CREATE INDEX idx_estabelecimentos_cadastur_status ON estabelecimentos (cadastur_status);
CREATE INDEX idx_estabelecimentos_pesquisas       ON estabelecimentos (aceita_pesquisas)
    WHERE status = 'ATIVO';
CREATE INDEX idx_estabelecimentos_coords          ON estabelecimentos (latitude, longitude)
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- ──────────────────────────────────────────────────────────
-- MEIO DE HOSPEDAGEM (RELAÇÃO 1:1 COM ESTABELECIMENTOS)
-- ──────────────────────────────────────────────────────────

CREATE TABLE meio_hospedagem (
    id_estabelecimento                  UUID            PRIMARY KEY
        REFERENCES estabelecimentos (id_estabelecimento)
        ON DELETE RESTRICT,
    tipo_hospedagem                     tipo_hospedagem,
    total_uh                            INTEGER,
    total_leitos                        INTEGER,
    uh_pcd                              INTEGER,
    func_fixos                          INTEGER,
    func_temporarios                    INTEGER,
    funcionamento_24h                   BOOLEAN,
    checkin_horario                     TIME,
    checkout_horario                    TIME,
    formas_pagamento                    JSONB           NOT NULL DEFAULT '[]'::jsonb,
    horario_funcionamento_descritivo    TEXT,
    horario_checkin_checkout_descritivo TEXT,
    reservas                            TEXT,
    regras_reserva                      TEXT,
    diaria_media                        NUMERIC(10, 2),
    atendimento_idiomas                 JSONB           NOT NULL DEFAULT '{}'::jsonb,
    infraestrutura                      JSONB           NOT NULL DEFAULT '{}'::jsonb,
    acessibilidade                      JSONB           NOT NULL DEFAULT '{}'::jsonb,
    criado_em                           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    atualizado_em                       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_meio_hospedagem_total_uh
        CHECK (total_uh IS NULL OR total_uh >= 0),

    CONSTRAINT ck_meio_hospedagem_total_leitos
        CHECK (total_leitos IS NULL OR total_leitos >= 0),

    CONSTRAINT ck_meio_hospedagem_uh_pcd
        CHECK (uh_pcd IS NULL OR uh_pcd >= 0),

    CONSTRAINT ck_meio_hospedagem_uh_pcd_le_total
        CHECK (uh_pcd IS NULL OR total_uh IS NULL OR uh_pcd <= total_uh),

    CONSTRAINT ck_meio_hospedagem_func_fixos
        CHECK (func_fixos IS NULL OR func_fixos >= 0),

    CONSTRAINT ck_meio_hospedagem_func_temporarios
        CHECK (func_temporarios IS NULL OR func_temporarios >= 0),

    CONSTRAINT ck_meio_hospedagem_diaria_media
        CHECK (diaria_media IS NULL OR diaria_media >= 0.0),

    CONSTRAINT ck_meio_hospedagem_formas_pagamento_array
        CHECK (jsonb_typeof(formas_pagamento) = 'array'),

    CONSTRAINT ck_meio_hospedagem_idiomas_object
        CHECK (jsonb_typeof(atendimento_idiomas) = 'object'),

    CONSTRAINT ck_meio_hospedagem_infraestrutura_object
        CHECK (jsonb_typeof(infraestrutura) = 'object'),

    CONSTRAINT ck_meio_hospedagem_acessibilidade_object
        CHECK (jsonb_typeof(acessibilidade) = 'object')
);

CREATE TRIGGER trg_meio_hospedagem_atualizado_em
    BEFORE UPDATE ON meio_hospedagem
    FOR EACH ROW
    EXECUTE FUNCTION set_atualizado_em();

-- Índices estratégicos para meio_hospedagem
CREATE INDEX idx_meio_hospedagem_tipo                 ON meio_hospedagem (tipo_hospedagem);
CREATE INDEX idx_meio_hospedagem_total_uh             ON meio_hospedagem (total_uh);
CREATE INDEX idx_meio_hospedagem_total_leitos         ON meio_hospedagem (total_leitos);
CREATE INDEX idx_meio_hospedagem_diaria_media         ON meio_hospedagem (diaria_media);
CREATE INDEX idx_meio_hospedagem_infraestrutura_gin   ON meio_hospedagem USING gin (infraestrutura);
CREATE INDEX idx_meio_hospedagem_acessibilidade_gin   ON meio_hospedagem USING gin (acessibilidade);
CREATE INDEX idx_meio_hospedagem_formas_pagamento_gin ON meio_hospedagem USING gin (formas_pagamento);

-- ──────────────────────────────────────────────────────────
-- DOCUMENTOS DE CONTROLE (ALVARÁ, AVCB, VIGILÂNCIA SANITÁRIA)
-- ──────────────────────────────────────────────────────────

CREATE TABLE documentos_controle (
    id_documento        BIGSERIAL           PRIMARY KEY,
    id_estabelecimento  UUID                NOT NULL
        REFERENCES estabelecimentos (id_estabelecimento)
        ON DELETE CASCADE,
    tipo_documento      tipo_documento      NOT NULL,
    numero              VARCHAR(120),
    data_emissao        DATE,
    data_vencimento     DATE                NOT NULL,
    status              status_documento    NOT NULL DEFAULT 'REGULAR',
    nome_arquivo        VARCHAR(255),
    content_type        VARCHAR(100),
    tamanho_bytes       BIGINT,
    checksum_sha256     VARCHAR(64),
    caminho_storage     TEXT,
    enviado_em          TIMESTAMPTZ,
    criado_em           TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ         NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_documentos_datas
        CHECK (data_emissao IS NULL OR data_emissao <= data_vencimento),

    CONSTRAINT ck_documentos_tamanho_bytes
        CHECK (tamanho_bytes IS NULL OR tamanho_bytes > 0),

    CONSTRAINT ck_documentos_checksum_sha256
        CHECK (checksum_sha256 IS NULL OR length(checksum_sha256) = 64)
);

CREATE TRIGGER trg_documentos_atualizado_em
    BEFORE UPDATE ON documentos_controle
    FOR EACH ROW
    EXECUTE FUNCTION set_atualizado_em();

-- Índices estratégicos para documentos_controle
CREATE INDEX idx_documentos_estab       ON documentos_controle (id_estabelecimento);
CREATE INDEX idx_documentos_tipo        ON documentos_controle (tipo_documento);
CREATE INDEX idx_documentos_status      ON documentos_controle (status);
CREATE INDEX idx_documentos_vencimento  ON documentos_controle (data_vencimento);

-- ──────────────────────────────────────────────────────────
-- SEED INICIAL: CATEGORIAS OFICIAIS DO CATÁLOGO
-- ──────────────────────────────────────────────────────────

INSERT INTO categorias_estabelecimento (id_categoria, nome_categoria, descricao)
VALUES
    (1, 'Meios de hospedagem', 'Hotéis, pousadas, resorts e outros meios de hospedagem.')
ON CONFLICT (id_categoria) DO UPDATE
    SET nome_categoria = EXCLUDED.nome_categoria,
        descricao      = EXCLUDED.descricao;

-- Ajusta a sequence para evitar conflitos em futuros inserts seriais
SELECT setval(
    pg_get_serial_sequence('categorias_estabelecimento', 'id_categoria'),
    COALESCE((SELECT MAX(id_categoria) FROM categorias_estabelecimento), 1),
    true
);

COMMIT;
