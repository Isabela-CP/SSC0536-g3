-- ============================================================
-- 001_dev_seed.sql
-- Seeds de desenvolvimento — dados totalmente fictícios.
-- NÃO usar em produção. Sem dados reais ou segredos.
--
-- Dependências de execução (nesta ordem):
--   1. 001_core_inventory.sql  →  cria a tabela 'estabelecimentos'
--   2. 002_operational_tables.sql  →  cria as tabelas abaixo
--
-- Idempotente: re-execução não duplica nem sobrescreve registros.
--
-- Estabelecimentos referenciados (UUIDs do seed-data.json):
--   11111111-1111-4111-8111-111111111111  Hotel Serra Azul       48 UH
--   22222222-2222-4222-8222-222222222222  Pousada Ipê Amarelo    16 UH
--   33333333-3333-4333-8333-333333333333  Hotel Vale do Sol      30 UH
--   44444444-4444-4444-8444-444444444444  Hospedagem em Cadastro  0 UH (incompleto)
--
-- Hashes de senha: valores fictícios não válidos como bcrypt;
-- a aplicação deve gerar hashes reais ao criar contas via API.
-- ============================================================

BEGIN;

-- ──────────────────────────────────────────────────────────
-- USUÁRIOS  (10 registros)
--   Perfis: 1 ADMINISTRADOR, 2 GESTORES, 3 EDITORES, 4 HOTEL
--   Estados: ATIVO, INATIVO, PENDENTE
-- ──────────────────────────────────────────────────────────

INSERT INTO usuarios (id, email, senha_hash, perfil, status, nome)
VALUES
    -- administrador
    (1,  'marina.admin@example.test',
         'DEV_PLACEHOLDER_HASH_001',
         'ADMINISTRADOR', 'ATIVO',   'Marina Administradora'),

    -- gestores
    (2,  'rafael.consulta@example.test',
         'DEV_PLACEHOLDER_HASH_002',
         'GESTOR',        'ATIVO',   'Rafael Consulta'),
    (3,  'fernanda.gestora@example.test',
         'DEV_PLACEHOLDER_HASH_003',
         'GESTOR',        'INATIVO', 'Fernanda Gestora'),   -- desligada

    -- editores
    (4,  'camila.editora@example.test',
         'DEV_PLACEHOLDER_HASH_004',
         'EDITOR',        'ATIVO',   'Camila Editora'),
    (5,  'bruno.editor@example.test',
         'DEV_PLACEHOLDER_HASH_005',
         'EDITOR',        'ATIVO',   'Bruno Editor'),
    (6,  'juliana.editor@example.test',
         'DEV_PLACEHOLDER_HASH_006',
         'EDITOR',        'PENDENTE', 'Juliana Editora')    -- convite pendente
ON CONFLICT (email) DO NOTHING;

INSERT INTO usuarios (id, email, senha_hash, perfil, status, nome, id_estabelecimento)
VALUES
    -- hotéis (vínculo obrigatório com estabelecimento)
    (7,  'hotel.serraazul@example.test',
         'DEV_PLACEHOLDER_HASH_007',
         'HOTEL', 'ATIVO',    'Responsável Serra Azul',
         '11111111-1111-4111-8111-111111111111'),
    (8,  'hotel.ipeamarelo@example.test',
         'DEV_PLACEHOLDER_HASH_008',
         'HOTEL', 'ATIVO',    'Responsável Ipê Amarelo',
         '22222222-2222-4222-8222-222222222222'),
    (9,  'hotel.valedosol@example.test',
         'DEV_PLACEHOLDER_HASH_009',
         'HOTEL', 'ATIVO',    'Responsável Vale do Sol',
         '33333333-3333-4333-8333-333333333333'),
    (10, 'hotel.cadastro@example.test',
         'DEV_PLACEHOLDER_HASH_010',
         'HOTEL', 'PENDENTE', 'Responsável Hospedagem Cadastro',
         '44444444-4444-4444-8444-444444444444')  -- convite ainda pendente
ON CONFLICT (email) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- CONVITES  (7 registros)
--   Estados: ACEITO (3), PENDENTE (2), EXPIRADO (1), CANCELADO (1)
-- ──────────────────────────────────────────────────────────

INSERT INTO convites (
    id, token_hash, email_destinatario, perfil,
    id_criador, id_estabelecimento, estado, expira_em, aceito_em
)
VALUES
    -- convites aceitos → deram origem aos usuários HOTEL 7, 8 e 9
    (1, 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2',
        'hotel.serraazul@example.test', 'HOTEL',
        1, '11111111-1111-4111-8111-111111111111',
        'ACEITO',
        '2026-02-10 23:59:59-03',
        '2026-02-05 14:32:00-03'),

    (2, 'b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3',
        'hotel.ipeamarelo@example.test', 'HOTEL',
        1, '22222222-2222-4222-8222-222222222222',
        'ACEITO',
        '2026-03-05 23:59:59-03',
        '2026-03-01 09:15:00-03'),

    (3, 'c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4',
        'hotel.valedosol@example.test', 'HOTEL',
        1, '33333333-3333-4333-8333-333333333333',
        'ACEITO',
        '2026-04-15 23:59:59-03',
        '2026-04-10 11:00:00-03'),

    -- convite pendente → usuário 10 (HOTEL, cadastro incompleto)
    (4, 'd4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5',
        'hotel.cadastro@example.test', 'HOTEL',
        1, '44444444-4444-4444-8444-444444444444',
        'PENDENTE',
        NOW() + INTERVAL '4 days',
        NULL),

    -- convite pendente para nova editora (usuária 6)
    (5, 'e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6',
        'juliana.editor@example.test', 'EDITOR',
        1, NULL,
        'PENDENTE',
        NOW() + INTERVAL '6 days',
        NULL),

    -- convite expirado sem uso
    (6, 'f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7',
        'antigo.gestor@example.test', 'GESTOR',
        1, NULL,
        'EXPIRADO',
        '2026-06-01 23:59:59-03',
        NULL),

    -- convite cancelado antes de expirar
    (7, 'a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8',
        'editor.cancelado@example.test', 'EDITOR',
        1, NULL,
        'CANCELADO',
        '2026-09-30 23:59:59-03',
        NULL)
ON CONFLICT (token_hash) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- PESQUISAS DE OCUPAÇÃO  (5 registros)
--   Estados: 2 ENCERRADA, 2 ABERTA, 1 RASCUNHO
--   Tipos: 3 CONSOLIDADO, 2 EXPECTATIVA
-- ──────────────────────────────────────────────────────────

INSERT INTO pesquisas_ocupacao (
    id, tipo, periodo_referencia, data_inicio, data_fim,
    estado, id_criador, aberta_em, encerrada_em
)
VALUES
    -- 1: agosto encerrada (base histórica)
    (1, 'CONSOLIDADO', '2026-08-01',
        '2026-09-01', '2026-09-15',
        'ENCERRADA', 1,
        '2026-09-01 08:00:00-03',
        '2026-09-15 18:00:00-03'),

    -- 2: setembro encerrada (mais recente)
    (2, 'CONSOLIDADO', '2026-09-01',
        '2026-10-01', '2026-10-15',
        'ENCERRADA', 1,
        '2026-10-01 08:00:00-03',
        '2026-10-15 18:00:00-03'),

    -- 3: outubro em coleta (aberta)
    (3, 'CONSOLIDADO', '2026-10-01',
        '2026-11-01', '2026-11-15',
        'ABERTA', 1,
        '2026-11-01 08:00:00-03',
        NULL),

    -- 4: expectativa novembro (aberta, hotéis devem responder)
    (4, 'EXPECTATIVA', '2026-11-01',
        '2026-10-20', '2026-10-31',
        'ABERTA', 1,
        '2026-10-20 08:00:00-03',
        NULL),

    -- 5: dezembro em rascunho (ainda não distribuída)
    (5, 'EXPECTATIVA', '2026-12-01',
        '2026-11-15', '2026-11-30',
        'RASCUNHO', 1,
        NULL,
        NULL)
ON CONFLICT (id) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- RESPOSTAS DE OCUPAÇÃO
--
-- Pesquisa 1 (ago/consolidado, encerrada):  4 estabelecimentos
--   Serra Azul ENVIADA, Ipê Amarelo ENVIADA, Vale do Sol ENVIADA,
--   Hospedagem Cadastro PENDENTE (não respondeu)
--
-- Pesquisa 2 (set/consolidado, encerrada):  4 estabelecimentos
--   Serra Azul ENVIADA, Ipê Amarelo ENVIADA, Vale do Sol ENVIADA,
--   Hospedagem Cadastro PENDENTE
--
-- Pesquisa 3 (out/consolidado, aberta):     4 estabelecimentos
--   Serra Azul ENVIADA, demais PENDENTE
--
-- Pesquisa 4 (nov/expectativa, aberta):     3 estabelecimentos ativos
--   todos PENDENTE (ainda dentro do prazo)
-- ──────────────────────────────────────────────────────────

INSERT INTO respostas_ocupacao (
    id, id_pesquisa, id_estabelecimento, id_respondente, status,
    uh_disponiveis, uh_ocupadas, taxa_ocupacao,
    pernoites, hospedes, diaria_media, enviada_em
)
VALUES

    -- ── Pesquisa 1: agosto/consolidado (encerrada) ──
    (1,  1, '11111111-1111-4111-8111-111111111111', 7,  'ENVIADA',
         48, 41, 85.42, 1968, 2814, 295.00,
         '2026-09-12 10:22:00-03'),

    (2,  1, '22222222-2222-4222-8222-222222222222', 8,  'ENVIADA',
         16, 13, 81.25,  558,  812, 185.50,
         '2026-09-10 16:40:00-03'),

    (3,  1, '33333333-3333-4333-8333-333333333333', 9,  'ENVIADA',
         30, 22, 73.33,  924, 1320, 240.00,
         '2026-09-14 09:05:00-03'),

    (4,  1, '44444444-4444-4444-8444-444444444444', NULL, 'PENDENTE',
         NULL, NULL, NULL, NULL, NULL, NULL, NULL),

    -- ── Pesquisa 2: setembro/consolidado (encerrada) ──
    (5,  2, '11111111-1111-4111-8111-111111111111', 7,  'ENVIADA',
         48, 38, 79.17, 1520, 2109, 280.00,
         '2026-10-14 15:30:00-03'),

    (6,  2, '22222222-2222-4222-8222-222222222222', 8,  'ENVIADA',
         16, 11, 68.75,  462,  680, 178.00,
         '2026-10-13 11:15:00-03'),

    (7,  2, '33333333-3333-4333-8333-333333333333', 9,  'ENVIADA',
         30, 20, 66.67,  820, 1155, 225.50,
         '2026-10-12 14:00:00-03'),

    (8,  2, '44444444-4444-4444-8444-444444444444', NULL, 'PENDENTE',
         NULL, NULL, NULL, NULL, NULL, NULL, NULL),

    -- ── Pesquisa 3: outubro/consolidado (aberta) ──
    (9,  3, '11111111-1111-4111-8111-111111111111', 7,  'ENVIADA',
         48, 35, 72.92, 1395, 1940, 270.00,
         '2026-11-03 09:00:00-03'),

    (10, 3, '22222222-2222-4222-8222-222222222222', NULL, 'PENDENTE',
         NULL, NULL, NULL, NULL, NULL, NULL, NULL),

    (11, 3, '33333333-3333-4333-8333-333333333333', NULL, 'PENDENTE',
         NULL, NULL, NULL, NULL, NULL, NULL, NULL),

    (12, 3, '44444444-4444-4444-8444-444444444444', NULL, 'PENDENTE',
         NULL, NULL, NULL, NULL, NULL, NULL, NULL),

    -- ── Pesquisa 4: novembro/expectativa (aberta) ──
    (13, 4, '11111111-1111-4111-8111-111111111111', NULL, 'PENDENTE',
         NULL, NULL, NULL, NULL, NULL, NULL, NULL),

    (14, 4, '22222222-2222-4222-8222-222222222222', NULL, 'PENDENTE',
         NULL, NULL, NULL, NULL, NULL, NULL, NULL),

    (15, 4, '33333333-3333-4333-8333-333333333333', NULL, 'PENDENTE',
         NULL, NULL, NULL, NULL, NULL, NULL, NULL)

ON CONFLICT (id_pesquisa, id_estabelecimento) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- AUDITORIA  (15 eventos)
-- ──────────────────────────────────────────────────────────

INSERT INTO auditoria_logs (
    id, id_usuario, acao, entidade_tipo, entidade_id,
    valor_anterior, valor_novo, ip_origem, criado_em
)
VALUES
    -- criação de estabelecimentos (feita pelo admin)
    (1,  1, 'CRIAR_ESTABELECIMENTO', 'estabelecimentos',
         '11111111-1111-4111-8111-111111111111',
         NULL,
         '{"nome_fantasia":"Hotel Serra Azul","status":"ATIVO"}',
         '192.168.1.10', '2026-01-12 13:15:00-03'),

    (2,  1, 'CRIAR_ESTABELECIMENTO', 'estabelecimentos',
         '22222222-2222-4222-8222-222222222222',
         NULL,
         '{"nome_fantasia":"Pousada Ipê Amarelo","status":"ATIVO"}',
         '192.168.1.10', '2026-01-15 10:30:00-03'),

    (3,  1, 'CRIAR_ESTABELECIMENTO', 'estabelecimentos',
         '33333333-3333-4333-8333-333333333333',
         NULL,
         '{"nome_fantasia":"Hotel Vale do Sol","status":"ATIVO"}',
         '192.168.1.10', '2026-01-20 09:45:00-03'),

    (4,  1, 'CRIAR_ESTABELECIMENTO', 'estabelecimentos',
         '44444444-4444-4444-8444-444444444444',
         NULL,
         '{"nome_fantasia":"Hospedagem em Cadastro","status":"ATIVO"}',
         '192.168.1.10', '2026-02-03 14:00:00-03'),

    -- edição de contato feita pelo hotel
    (5,  7, 'EDITAR_ESTABELECIMENTO', 'estabelecimentos',
         '11111111-1111-4111-8111-111111111111',
         '{"telefone_pesquisas":"+55 16 3333-2000"}',
         '{"telefone_pesquisas":"+55 16 99999-1000"}',
         '177.42.100.55', '2026-03-10 11:22:00-03'),

    -- envio de convites
    (6,  1, 'CRIAR_CONVITE', 'convites', '1',
         NULL,
         '{"email":"hotel.serraazul@example.test","perfil":"HOTEL"}',
         '192.168.1.10', '2026-01-30 08:00:00-03'),

    (7,  1, 'CRIAR_CONVITE', 'convites', '5',
         NULL,
         '{"email":"juliana.editor@example.test","perfil":"EDITOR"}',
         '192.168.1.10', '2026-10-25 09:30:00-03'),

    -- abertura e encerramento de pesquisas
    (8,  1, 'ABRIR_PESQUISA', 'pesquisas_ocupacao', '1',
         '{"estado":"RASCUNHO"}',
         '{"estado":"ABERTA"}',
         '192.168.1.10', '2026-09-01 08:00:00-03'),

    (9,  1, 'ENCERRAR_PESQUISA', 'pesquisas_ocupacao', '1',
         '{"estado":"ABERTA"}',
         '{"estado":"ENCERRADA"}',
         '192.168.1.10', '2026-09-15 18:00:00-03'),

    (10, 1, 'ABRIR_PESQUISA', 'pesquisas_ocupacao', '2',
         '{"estado":"RASCUNHO"}',
         '{"estado":"ABERTA"}',
         '192.168.1.10', '2026-10-01 08:00:00-03'),

    (11, 1, 'ENCERRAR_PESQUISA', 'pesquisas_ocupacao', '2',
         '{"estado":"ABERTA"}',
         '{"estado":"ENCERRADA"}',
         '192.168.1.10', '2026-10-15 18:00:00-03'),

    -- respostas enviadas
    (12, 7, 'ENVIAR_RESPOSTA', 'respostas_ocupacao', '5',
         '{"status":"PENDENTE"}',
         '{"status":"ENVIADA","taxa_ocupacao":79.17}',
         '177.42.100.55', '2026-10-14 15:30:00-03'),

    (13, 9, 'ENVIAR_RESPOSTA', 'respostas_ocupacao', '7',
         '{"status":"PENDENTE"}',
         '{"status":"ENVIADA","taxa_ocupacao":66.67}',
         '187.10.55.200', '2026-10-12 14:00:00-03'),

    -- inativação e reativação de usuário
    (14, 1, 'INATIVAR_USUARIO', 'usuarios', '3',
         '{"status":"ATIVO"}',
         '{"status":"INATIVO","motivo":"Colaboradora desligada em outubro/2026"}',
         '192.168.1.10', '2026-10-01 09:00:00-03'),

    -- cancelamento de convite
    (15, 1, 'CANCELAR_CONVITE', 'convites', '7',
         '{"estado":"PENDENTE"}',
         '{"estado":"CANCELADO"}',
         '192.168.1.10', '2026-09-20 10:00:00-03')

ON CONFLICT (id) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- RELATÓRIOS  (5 registros)
--   2 PDF concluídos, 1 CSV concluído, 1 PDF pendente, 1 com erro
-- ──────────────────────────────────────────────────────────

INSERT INTO relatorios (
    id, formato, parametros, status, id_solicitante,
    iniciado_em, concluido_em,
    arquivo_nome, arquivo_caminho_interno, arquivo_tamanho_bytes,
    mensagem_erro
)
VALUES
    (1, 'PDF',
        '{"id_pesquisa":1,"tipo":"CONSOLIDADO","periodo_referencia":"2026-08-01","incluir_graficos":true}',
        'CONCLUIDO', 1,
        '2026-09-16 09:05:00-03',
        '2026-09-16 09:07:22-03',
        'relatorio-ocupacao-consolidado-ago-2026.pdf',
        'relatorios/2026/08/consolidado/relatorio-ocupacao-consolidado-ago-2026.pdf',
        72840, NULL),

    (2, 'CSV',
        '{"id_pesquisa":1,"tipo":"CONSOLIDADO","periodo_referencia":"2026-08-01"}',
        'CONCLUIDO', 2,
        '2026-09-16 10:00:00-03',
        '2026-09-16 10:00:45-03',
        'relatorio-ocupacao-consolidado-ago-2026.csv',
        'relatorios/2026/08/consolidado/relatorio-ocupacao-consolidado-ago-2026.csv',
        9216, NULL),

    (3, 'PDF',
        '{"id_pesquisa":2,"tipo":"CONSOLIDADO","periodo_referencia":"2026-09-01","incluir_graficos":true}',
        'CONCLUIDO', 1,
        '2026-10-16 08:30:00-03',
        '2026-10-16 08:32:55-03',
        'relatorio-ocupacao-consolidado-set-2026.pdf',
        'relatorios/2026/09/consolidado/relatorio-ocupacao-consolidado-set-2026.pdf',
        68096, NULL),

    -- relatório em fila aguardando processamento
    (4, 'PDF',
        '{"id_pesquisa":3,"tipo":"CONSOLIDADO","periodo_referencia":"2026-10-01","incluir_graficos":true}',
        'PENDENTE', 1,
        NULL, NULL, NULL, NULL, NULL, NULL),

    -- relatório que falhou (storage indisponível no momento)
    (5, 'PDF',
        '{"tipo":"CONSOLIDADO","periodo_referencia":"2026-07-01"}',
        'ERRO', 2,
        '2026-08-16 11:00:00-03',
        NULL, NULL, NULL, NULL,
        'Timeout ao gravar arquivo no storage após 3 tentativas.')

ON CONFLICT (id) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- RECUPERAÇÃO DE SENHA  (2 registros)
--   1 já utilizada, 1 ainda válida
-- ──────────────────────────────────────────────────────────

INSERT INTO recuperacao_senha (
    id, id_usuario, token_hash, expira_em, usado_em
)
VALUES
    -- token já utilizado pelo usuário 8 (Ipê Amarelo) em outubro
    (1, 8,
        'c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9',
        '2026-10-05 12:00:00-03',
        '2026-10-04 16:45:00-03'),

    -- token pendente válido para o usuário 6 (Juliana, ainda PENDENTE)
    (2, 6,
        'd9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0',
        NOW() + INTERVAL '2 hours',
        NULL)

ON CONFLICT (token_hash) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- AJUSTE DE SEQUÊNCIAS
-- Garante que próximos INSERTs não colidam com IDs acima.
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

SELECT setval('recuperacao_senha_id_seq',
    (SELECT MAX(id) FROM recuperacao_senha), true);

COMMIT;
