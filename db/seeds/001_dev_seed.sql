-- ============================================================
-- 001_dev_seed.sql
-- Seeds de desenvolvimento — dados totalmente fictícios.
-- NÃO usar em produção. Não contém dados reais nem segredos.
--
-- Idempotente: re-execução é segura; registros existentes
-- não são duplicados nem sobrescritos.
--
-- Dependências de execução:
--   1. 001_core_inventory.sql  — cria 'estabelecimentos'
--   2. 002_operational_tables.sql — cria tabelas abaixo
--
-- UUIDs de estabelecimentos usados abaixo correspondem ao
-- seed-data.json (contratos_api_oto/mocks/seed-data.json)
-- para manter consistência com os mocks do frontend.
--
-- Hashes de senha fictícios (placeholder): a aplicação deve
-- gerar bcrypt reais ao criar usuários via API. Os valores
-- abaixo são strings que não coliderão com nenhum bcrypt válido
-- pois não seguem o formato $2b$NN$...
-- ============================================================

BEGIN;

-- ──────────────────────────────────────────────────────────
-- USUARIOS
-- ──────────────────────────────────────────────────────────

INSERT INTO usuarios (id, email, senha_hash, perfil, status, nome)
VALUES
    (
        1,
        'admin@oto.dev',
        'DEV_PLACEHOLDER_HASH_ADMINISTRADOR',
        'ADMINISTRADOR', 'ATIVO', 'Administrador OTO'
    ),
    (
        2,
        'gestor@oto.dev',
        'DEV_PLACEHOLDER_HASH_GESTOR',
        'GESTOR', 'ATIVO', 'Gestor Inventário'
    ),
    (
        3,
        'editor@oto.dev',
        'DEV_PLACEHOLDER_HASH_EDITOR',
        'EDITOR', 'ATIVO', 'Editora Cadastros'
    )
ON CONFLICT (email) DO NOTHING;

-- Usuário HOTEL precisa de id_estabelecimento (constraint ck_usuarios_hotel_estabelecimento).
-- Inserido em bloco separado para clareza sobre a dependência.
INSERT INTO usuarios (id, email, senha_hash, perfil, status, nome, id_estabelecimento)
VALUES
    (
        4,
        'hotel.serraazul@oto.dev',
        'DEV_PLACEHOLDER_HASH_HOTEL_SERRAAZUL',
        'HOTEL', 'ATIVO', 'Responsável Serra Azul',
        '11111111-1111-4111-8111-111111111111'
    ),
    (
        5,
        'hotel.ipeamarelo@oto.dev',
        'DEV_PLACEHOLDER_HASH_HOTEL_IPE',
        'HOTEL', 'ATIVO', 'Responsável Ipê Amarelo',
        '22222222-2222-4222-8222-222222222222'
    )
ON CONFLICT (email) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- CONVITES
-- ──────────────────────────────────────────────────────────

INSERT INTO convites (
    id, token_hash, email_destinatario, perfil,
    id_criador, estado, expira_em
)
VALUES
    (
        1,
        'a3f5c8e2d1b0493e7f6a9c4d8e2f1a5b3c7d9e0f2a4b6c8d0e2f4a6b8c0d2e4',
        'novo.editor@oto.dev',
        'EDITOR',
        1,      -- criado pelo admin
        'PENDENTE',
        NOW() + INTERVAL '7 days'
    ),
    (
        2,
        'b9e1f3a5c7d2e4f6a8b0c2d4e6f8a0b2c4d6e8f0a2b4c6d8e0f2a4b6c8d0e2',
        'gestor.novo@oto.dev',
        'GESTOR',
        1,
        'EXPIRADO',
        NOW() - INTERVAL '1 day'
    )
ON CONFLICT (token_hash) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- PESQUISAS DE OCUPAÇÃO
-- ──────────────────────────────────────────────────────────

INSERT INTO pesquisas_ocupacao (
    id, tipo, periodo_referencia, data_inicio, data_fim,
    estado, id_criador, aberta_em, encerrada_em
)
VALUES
    (
        1,
        'CONSOLIDADO',
        '2026-09-01',
        '2026-10-01',
        '2026-10-15',
        'ENCERRADA',
        1,
        '2026-10-01 08:00:00-03',
        '2026-10-15 18:00:00-03'
    ),
    (
        2,
        'EXPECTATIVA',
        '2026-11-01',
        '2026-10-20',
        '2026-10-31',
        'ABERTA',
        1,
        '2026-10-20 08:00:00-03',
        NULL
    ),
    (
        3,
        'CONSOLIDADO',
        '2026-10-01',
        '2026-11-01',
        '2026-11-15',
        'RASCUNHO',
        1,
        NULL,
        NULL
    )
ON CONFLICT (id) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- RESPOSTAS DE OCUPAÇÃO
-- UUIDs de estabelecimentos do seed-data.json
-- ──────────────────────────────────────────────────────────

INSERT INTO respostas_ocupacao (
    id, id_pesquisa, id_estabelecimento, id_respondente, status,
    uh_disponiveis, uh_ocupadas, taxa_ocupacao,
    pernoites, hospedes, diaria_media,
    enviada_em
)
VALUES
    (
        1,
        1,
        '11111111-1111-4111-8111-111111111111',
        4,          -- respondeu pelo usuário HOTEL serra azul
        'ENVIADA',
        48, 38, 79.17,
        1520, 2109, 280.00,
        '2026-10-14 15:30:00-03'
    ),
    (
        2,
        1,
        '22222222-2222-4222-8222-222222222222',
        5,
        'ENVIADA',
        30, 20, 66.67,
        820, 1200, 195.00,
        '2026-10-13 10:00:00-03'
    ),
    (
        3,
        2,
        '11111111-1111-4111-8111-111111111111',
        NULL,
        'PENDENTE',
        NULL, NULL, NULL,
        NULL, NULL, NULL,
        NULL
    ),
    (
        4,
        2,
        '22222222-2222-4222-8222-222222222222',
        NULL,
        'PENDENTE',
        NULL, NULL, NULL,
        NULL, NULL, NULL,
        NULL
    )
ON CONFLICT (id_pesquisa, id_estabelecimento) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- AUDITORIA — eventos de exemplo
-- ──────────────────────────────────────────────────────────

INSERT INTO auditoria_logs (
    id, id_usuario, acao, entidade_tipo, entidade_id,
    valor_anterior, valor_novo
)
VALUES
    (
        1,
        1,
        'CRIAR_ESTABELECIMENTO',
        'estabelecimentos',
        '11111111-1111-4111-8111-111111111111',
        NULL,
        '{"nome_fantasia": "Hotel Serra Azul", "status": "ATIVO"}'
    ),
    (
        2,
        1,
        'CRIAR_ESTABELECIMENTO',
        'estabelecimentos',
        '22222222-2222-4222-8222-222222222222',
        NULL,
        '{"nome_fantasia": "Pousada Ipê Amarelo", "status": "ATIVO"}'
    ),
    (
        3,
        1,
        'ENCERRAR_PESQUISA',
        'pesquisas_ocupacao',
        '1',
        '{"estado": "ABERTA"}',
        '{"estado": "ENCERRADA"}'
    ),
    (
        4,
        1,
        'ABRIR_PESQUISA',
        'pesquisas_ocupacao',
        '2',
        '{"estado": "RASCUNHO"}',
        '{"estado": "ABERTA"}'
    )
ON CONFLICT (id) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- RELATÓRIOS — exemplo de relatório concluído e um pendente
-- ──────────────────────────────────────────────────────────

INSERT INTO relatorios (
    id, formato, parametros, status, id_solicitante,
    iniciado_em, concluido_em,
    arquivo_nome, arquivo_caminho_interno, arquivo_tamanho_bytes
)
VALUES
    (
        1,
        'PDF',
        '{"id_pesquisa": 1, "tipo": "CONSOLIDADO", "periodo_referencia": "2026-09-01"}',
        'CONCLUIDO',
        1,
        NOW() - INTERVAL '10 minutes',
        NOW() - INTERVAL '8 minutes',
        'relatorio-ocupacao-consolidado-set-2026.pdf',
        'relatorios/2026/09/relatorio-ocupacao-consolidado-set-2026.pdf',
        51200
    ),
    (
        2,
        'CSV',
        '{"id_pesquisa": 1, "tipo": "CONSOLIDADO", "periodo_referencia": "2026-09-01"}',
        'CONCLUIDO',
        2,
        NOW() - INTERVAL '6 minutes',
        NOW() - INTERVAL '5 minutes',
        'relatorio-ocupacao-consolidado-set-2026.csv',
        'relatorios/2026/09/relatorio-ocupacao-consolidado-set-2026.csv',
        8192
    ),
    (
        3,
        'PDF',
        '{"tipo": "EXPECTATIVA", "periodo_referencia": "2026-11-01"}',
        'PENDENTE',
        1,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL
    )
ON CONFLICT (id) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- AJUSTE DE SEQUÊNCIAS
-- Evita colisão com os IDs inseridos acima.
-- ──────────────────────────────────────────────────────────

SELECT setval('usuarios_id_seq',
    (SELECT MAX(id) FROM usuarios), true);

SELECT setval('convites_id_seq',
    (SELECT MAX(id) FROM convites), true);

SELECT setval('pesquisas_ocupacao_id_seq',
    (SELECT MAX(id) FROM pesquisas_ocupacao), true);

SELECT setval('respostas_ocupacao_id_seq',
    (SELECT MAX(id) FROM respostas_ocupacao), true);

SELECT setval('auditoria_logs_id_seq',
    (SELECT MAX(id) FROM auditoria_logs), true);

SELECT setval('relatorios_id_seq',
    (SELECT MAX(id) FROM relatorios), true);

COMMIT;
