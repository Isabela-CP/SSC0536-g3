-- ============================================================
-- 002_operational_tables.sql
-- Tabelas operacionais: autenticação, convites, pesquisas de
-- ocupação, respostas, auditoria e relatórios.
--
-- Depende de: 001_core_inventory.sql
--   Referencia: estabelecimentos(id_estabelecimento) UUID
--
-- Premissas e decisões documentadas:
--
-- [P1] Perfil HOTEL é o mapeamento de CONTA_EMPRESARIO do contrato;
--      nome HOTEL adotado por consistência com x-allowed-roles.
--
-- [P2] status_usuario='PENDENTE' cobre o período entre criação da
--      conta e aceitação do convite; torna-se 'ATIVO' ao aceitar.
--
-- [P3] token_hash em convites e recuperacao_senha armazena SHA-256
--      do token gerado; o valor em texto puro nunca é persistido.
--
-- [P4] periodo_referencia em pesquisas_ocupacao representa o mês
--      de referência como DATE (primeiro dia do mês), pois o
--      OpenAPI não especifica a granularidade. Adotar DATE permite
--      filtros e agregações nativas sem JSONB.
--
-- [P5] Métricas de respostas (uh_disponiveis, uh_ocupadas,
--      taxa_ocupacao, pernoites, hospedes, diaria_media) são colunas
--      relacionais porque o OpenAPI expõe e filtra esses campos;
--      usar JSONB nesse caso substituiria colunas importantes.
--
-- [P6] Estratégia de autenticação: JWT Bearer stateless.
--      Tabela 'sessoes' não foi criada pois JWTs curtos (≤ 15 min)
--      com refresh token cobrem o MVP sem persistir sessões.
--      Tabela 'recuperacao_senha' criada para suportar
--      POST /auth/recuperacao-senha.
--
-- [P7] auditoria_logs.entidade_id é TEXT para acomodar tanto UUIDs
--      (estabelecimentos) quanto BIGINTs (usuarios, pesquisas).
--
-- [P8] relatorios.arquivo_caminho_interno não é exposto pela API;
--      contém o caminho interno no storage (S3 key, path, etc.).
-- ============================================================

BEGIN;

-- ──────────────────────────────────────────────────────────
-- TIPOS ENUMERADOS
-- ──────────────────────────────────────────────────────────

CREATE TYPE perfil_usuario AS ENUM (
    'ADMINISTRADOR',
    'GESTOR',
    'EDITOR',
    'HOTEL'         -- mapeado de CONTA_EMPRESARIO no contrato [P1]
);

CREATE TYPE status_usuario AS ENUM (
    'ATIVO',
    'INATIVO',
    'PENDENTE'      -- conta criada, convite ainda não aceito [P2]
);

CREATE TYPE status_convite AS ENUM (
    'PENDENTE',
    'ACEITO',
    'EXPIRADO',
    'CANCELADO'
);

CREATE TYPE tipo_pesquisa AS ENUM (
    'CONSOLIDADO',
    'EXPECTATIVA'
);

CREATE TYPE status_pesquisa AS ENUM (
    'RASCUNHO',
    'ABERTA',
    'ENCERRADA'
);

CREATE TYPE status_resposta AS ENUM (
    'PENDENTE',     -- estabelecimento ainda não respondeu
    'ENVIADA'
);

CREATE TYPE formato_relatorio AS ENUM (
    'PDF',
    'CSV'
);

CREATE TYPE status_relatorio AS ENUM (
    'PENDENTE',
    'PROCESSANDO',
    'CONCLUIDO',
    'ERRO'
);

-- ──────────────────────────────────────────────────────────
-- USUARIOS
-- ──────────────────────────────────────────────────────────

CREATE TABLE usuarios (
    id                  BIGSERIAL           PRIMARY KEY,
    email               VARCHAR(254)        NOT NULL,
    senha_hash          TEXT                NOT NULL,
    perfil              perfil_usuario      NOT NULL,
    status              status_usuario      NOT NULL DEFAULT 'PENDENTE',
    nome                VARCHAR(200),
    -- id_estabelecimento vincula perfil HOTEL ao seu estabelecimento;
    -- deve ser NULL para ADMINISTRADOR, GESTOR e EDITOR [P1]
    id_estabelecimento  UUID
        REFERENCES estabelecimentos (id_estabelecimento)
        ON DELETE RESTRICT,
    criado_em           TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ         NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_usuarios_email
        UNIQUE (email),

    -- HOTEL exige vínculo com estabelecimento; demais perfis não [P1]
    CONSTRAINT ck_usuarios_hotel_estabelecimento
        CHECK (
            (perfil = 'HOTEL' AND id_estabelecimento IS NOT NULL)
            OR (perfil <> 'HOTEL' AND id_estabelecimento IS NULL)
        )
);

CREATE INDEX idx_usuarios_perfil  ON usuarios (perfil);
CREATE INDEX idx_usuarios_status  ON usuarios (status);
CREATE INDEX idx_usuarios_estab   ON usuarios (id_estabelecimento)
    WHERE id_estabelecimento IS NOT NULL;

-- ──────────────────────────────────────────────────────────
-- CONVITES
-- ──────────────────────────────────────────────────────────

CREATE TABLE convites (
    id                  BIGSERIAL           PRIMARY KEY,
    -- hash SHA-256 do token; token em texto puro nunca é persistido [P3]
    token_hash          TEXT                NOT NULL,
    email_destinatario  VARCHAR(254)        NOT NULL,
    perfil              perfil_usuario      NOT NULL,
    id_criador          BIGINT              NOT NULL
        REFERENCES usuarios (id)
        ON DELETE RESTRICT,
    -- obrigatório quando perfil = 'HOTEL'
    id_estabelecimento  UUID
        REFERENCES estabelecimentos (id_estabelecimento)
        ON DELETE RESTRICT,
    estado              status_convite      NOT NULL DEFAULT 'PENDENTE',
    expira_em           TIMESTAMPTZ         NOT NULL,
    criado_em           TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    aceito_em           TIMESTAMPTZ,

    CONSTRAINT uq_convites_token_hash
        UNIQUE (token_hash),

    CONSTRAINT ck_convites_hotel_estabelecimento
        CHECK (
            (perfil = 'HOTEL' AND id_estabelecimento IS NOT NULL)
            OR (perfil <> 'HOTEL')
        ),

    -- aceito_em só pode existir quando estado = 'ACEITO'
    CONSTRAINT ck_convites_aceito_em
        CHECK (aceito_em IS NULL OR estado = 'ACEITO')
);

CREATE INDEX idx_convites_email     ON convites (email_destinatario);
CREATE INDEX idx_convites_estado    ON convites (estado);
CREATE INDEX idx_convites_criador   ON convites (id_criador);
-- índice parcial para buscas de convites pendentes a expirar
CREATE INDEX idx_convites_expira_em ON convites (expira_em)
    WHERE estado = 'PENDENTE';

-- ──────────────────────────────────────────────────────────
-- PESQUISAS DE OCUPAÇÃO
-- ──────────────────────────────────────────────────────────

CREATE TABLE pesquisas_ocupacao (
    id                  BIGSERIAL           PRIMARY KEY,
    tipo                tipo_pesquisa       NOT NULL,
    -- mês de referência como primeiro dia do mês (ex.: 2026-09-01) [P4]
    periodo_referencia  DATE                NOT NULL,
    data_inicio         DATE,   -- início do prazo de coleta
    data_fim            DATE,   -- fim do prazo de coleta
    estado              status_pesquisa     NOT NULL DEFAULT 'RASCUNHO',
    id_criador          BIGINT              NOT NULL
        REFERENCES usuarios (id)
        ON DELETE RESTRICT,
    criado_em           TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    aberta_em           TIMESTAMPTZ,
    encerrada_em        TIMESTAMPTZ,

    CONSTRAINT ck_pesquisa_datas
        CHECK (
            data_fim IS NULL
            OR data_inicio IS NULL
            OR data_fim >= data_inicio
        ),

    -- timestamps de transição de estado consistentes com o estado atual
    CONSTRAINT ck_pesquisa_aberta_em
        CHECK (aberta_em IS NULL OR estado IN ('ABERTA', 'ENCERRADA')),

    CONSTRAINT ck_pesquisa_encerrada_em
        CHECK (encerrada_em IS NULL OR estado = 'ENCERRADA')
);

CREATE INDEX idx_pesquisas_estado    ON pesquisas_ocupacao (estado);
CREATE INDEX idx_pesquisas_periodo   ON pesquisas_ocupacao (periodo_referencia);
CREATE INDEX idx_pesquisas_tipo      ON pesquisas_ocupacao (tipo);
CREATE INDEX idx_pesquisas_criador   ON pesquisas_ocupacao (id_criador);

-- ──────────────────────────────────────────────────────────
-- RESPOSTAS DE OCUPAÇÃO
-- ──────────────────────────────────────────────────────────

CREATE TABLE respostas_ocupacao (
    id                  BIGSERIAL           PRIMARY KEY,
    id_pesquisa         BIGINT              NOT NULL
        REFERENCES pesquisas_ocupacao (id)
        ON DELETE RESTRICT,
    id_estabelecimento  UUID                NOT NULL
        REFERENCES estabelecimentos (id_estabelecimento)
        ON DELETE RESTRICT,
    id_respondente      BIGINT
        REFERENCES usuarios (id)
        ON DELETE SET NULL,
    status              status_resposta     NOT NULL DEFAULT 'PENDENTE',

    -- métricas em colunas relacionais para filtros e relatórios [P5]
    uh_disponiveis      INTEGER             CHECK (uh_disponiveis >= 0),
    uh_ocupadas         INTEGER             CHECK (uh_ocupadas >= 0),
    -- percentual 0–100, informado ou calculado pelo estabelecimento
    taxa_ocupacao       NUMERIC(5, 2)       CHECK (taxa_ocupacao BETWEEN 0 AND 100),
    pernoites           INTEGER             CHECK (pernoites >= 0),
    hospedes            INTEGER             CHECK (hospedes >= 0),
    diaria_media        NUMERIC(12, 2)      CHECK (diaria_media >= 0),
    observacoes         TEXT,

    enviada_em          TIMESTAMPTZ,
    criado_em           TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ         NOT NULL DEFAULT NOW(),

    -- uma resposta por pesquisa por estabelecimento
    CONSTRAINT uq_respostas_pesquisa_estab
        UNIQUE (id_pesquisa, id_estabelecimento),

    CONSTRAINT ck_respostas_enviada_em
        CHECK (enviada_em IS NULL OR status = 'ENVIADA'),

    -- uh_ocupadas não pode exceder uh_disponiveis quando ambos informados
    CONSTRAINT ck_respostas_uh_consistente
        CHECK (
            uh_ocupadas IS NULL
            OR uh_disponiveis IS NULL
            OR uh_ocupadas <= uh_disponiveis
        )
);

CREATE INDEX idx_respostas_pesquisa        ON respostas_ocupacao (id_pesquisa);
CREATE INDEX idx_respostas_estabelecimento ON respostas_ocupacao (id_estabelecimento);
CREATE INDEX idx_respostas_status          ON respostas_ocupacao (status);
CREATE INDEX idx_respostas_respondente     ON respostas_ocupacao (id_respondente)
    WHERE id_respondente IS NOT NULL;
-- índice para relatórios que agregam por período (via pesquisa)
CREATE INDEX idx_respostas_pesquisa_status ON respostas_ocupacao (id_pesquisa, status);

-- ──────────────────────────────────────────────────────────
-- AUDITORIA
-- ──────────────────────────────────────────────────────────

CREATE TABLE auditoria_logs (
    id              BIGSERIAL       PRIMARY KEY,
    -- NULL para ações do sistema sem ator humano
    id_usuario      BIGINT
        REFERENCES usuarios (id)
        ON DELETE SET NULL,
    acao            VARCHAR(100)    NOT NULL,   -- ex.: 'INATIVAR_ESTABELECIMENTO'
    entidade_tipo   VARCHAR(80)     NOT NULL,   -- nome da tabela afetada [P7]
    entidade_id     TEXT            NOT NULL,   -- UUID ou BIGINT como texto [P7]
    valor_anterior  JSONB,
    valor_novo      JSONB,
    ip_origem       INET,
    criado_em       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    -- sem atualizado_em: log de auditoria é imutável após inserção
);

CREATE INDEX idx_auditoria_usuario   ON auditoria_logs (id_usuario)
    WHERE id_usuario IS NOT NULL;
CREATE INDEX idx_auditoria_acao      ON auditoria_logs (acao);
CREATE INDEX idx_auditoria_entidade  ON auditoria_logs (entidade_tipo, entidade_id);
CREATE INDEX idx_auditoria_criado_em ON auditoria_logs (criado_em);

-- ──────────────────────────────────────────────────────────
-- RELATÓRIOS
-- ──────────────────────────────────────────────────────────

CREATE TABLE relatorios (
    id                      BIGSERIAL           PRIMARY KEY,
    formato                 formato_relatorio   NOT NULL,
    -- parâmetros variáveis por tipo de relatório (filtros, período) [P8]
    parametros              JSONB               NOT NULL DEFAULT '{}',
    status                  status_relatorio    NOT NULL DEFAULT 'PENDENTE',
    id_solicitante          BIGINT              NOT NULL
        REFERENCES usuarios (id)
        ON DELETE RESTRICT,
    criado_em               TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    iniciado_em             TIMESTAMPTZ,
    concluido_em            TIMESTAMPTZ,
    -- metadados do arquivo gerado; NULL enquanto status <> 'CONCLUIDO'
    arquivo_nome            VARCHAR(255),
    arquivo_caminho_interno TEXT,   -- caminho no storage; não exposto pela API [P8]
    arquivo_tamanho_bytes   BIGINT              CHECK (arquivo_tamanho_bytes > 0),
    mensagem_erro           TEXT,

    -- arquivo obrigatório quando concluído
    CONSTRAINT ck_relatorio_concluido
        CHECK (
            status <> 'CONCLUIDO'
            OR (
                arquivo_nome IS NOT NULL
                AND concluido_em IS NOT NULL
            )
        ),

    -- mensagem_erro obrigatória quando status = 'ERRO'
    CONSTRAINT ck_relatorio_erro
        CHECK (
            status <> 'ERRO'
            OR mensagem_erro IS NOT NULL
        )
);

CREATE INDEX idx_relatorios_solicitante ON relatorios (id_solicitante);
CREATE INDEX idx_relatorios_status      ON relatorios (status);
CREATE INDEX idx_relatorios_criado_em   ON relatorios (criado_em);

-- ──────────────────────────────────────────────────────────
-- RECUPERAÇÃO DE SENHA
-- Suporte ao endpoint POST /auth/recuperacao-senha. [P6]
-- ──────────────────────────────────────────────────────────

CREATE TABLE recuperacao_senha (
    id          BIGSERIAL       PRIMARY KEY,
    id_usuario  BIGINT          NOT NULL
        REFERENCES usuarios (id)
        ON DELETE CASCADE,
    token_hash  TEXT            NOT NULL,   -- SHA-256 do token [P3]
    expira_em   TIMESTAMPTZ     NOT NULL,
    usado_em    TIMESTAMPTZ,
    criado_em   TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_recuperacao_token_hash
        UNIQUE (token_hash),

    -- token usado antes de expirar é válido
    CONSTRAINT ck_recuperacao_uso_antes_expiracao
        CHECK (usado_em IS NULL OR usado_em <= expira_em)
);

CREATE INDEX idx_recuperacao_usuario ON recuperacao_senha (id_usuario);
-- índice parcial para buscas de tokens ainda válidos
CREATE INDEX idx_recuperacao_expira  ON recuperacao_senha (expira_em)
    WHERE usado_em IS NULL;

-- ──────────────────────────────────────────────────────────
-- TRIGGER: atualiza atualizado_em automaticamente
-- ──────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION fn_set_atualizado_em()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_usuarios_atualizado_em
    BEFORE UPDATE ON usuarios
    FOR EACH ROW EXECUTE FUNCTION fn_set_atualizado_em();

CREATE TRIGGER trg_pesquisas_atualizado_em
    BEFORE UPDATE ON pesquisas_ocupacao
    FOR EACH ROW EXECUTE FUNCTION fn_set_atualizado_em();

CREATE TRIGGER trg_respostas_atualizado_em
    BEFORE UPDATE ON respostas_ocupacao
    FOR EACH ROW EXECUTE FUNCTION fn_set_atualizado_em();

COMMIT;
