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
-- CATEGORIAS DE ESTABELECIMENTO (Catálogo completo OTO)
-- ──────────────────────────────────────────────────────────

INSERT INTO categorias_estabelecimento (id_categoria, nome_categoria, descricao)
VALUES
    (1, 'Meios de hospedagem', 'Hotéis, pousadas, resorts e outros meios de hospedagem.'),
    (2, 'Meios de alimentação e bebidas', 'Restaurantes, bares, lanchonetes, cafeterias e similares.'),
    (3, 'Agências e operadoras de turismo', 'Agências de viagens, receptivo e operadoras turísticas.'),
    (4, 'Atrativos lazer e entretenimento', 'Parques, museus, atrativos culturais, naturais e de lazer.'),
    (5, 'Locadoras de veículos e transporte turístico', 'Locadoras de automóveis, vans, ônibus e transporte turístico.'),
    (6, 'Espaços para eventos', 'Centros de convenções, auditórios, salões e pavilhões de feiras.'),
    (7, 'Organizadores e serviços para eventos', 'Empresas organizadoras, cerimonial, buffet e serviços de apoio a eventos.'),
    (8, 'Guias de turismo', 'Profissionais e guias de turismo cadastrados.'),
    (9, 'Artesanato e comércio diferenciado', 'Lojas de artesanato, souvenirs e comércio turístico diferenciado.')
ON CONFLICT (id_categoria) DO UPDATE
    SET nome_categoria = EXCLUDED.nome_categoria,
        descricao      = EXCLUDED.descricao;

SELECT setval(
    pg_get_serial_sequence('categorias_estabelecimento', 'id_categoria'),
    COALESCE((SELECT MAX(id_categoria) FROM categorias_estabelecimento), 1),
    true
);

-- ──────────────────────────────────────────────────────────
-- ESTABELECIMENTOS DO INVENTÁRIO (4 registros fictícios do seed-data.json)
-- ──────────────────────────────────────────────────────────

INSERT INTO estabelecimentos (
    id_estabelecimento, id_categoria, nome_fantasia, razao_social, cnpj,
    cnae, status, motivo_inativacao, inativado_em, data_abertura, endereco, bairro,
    latitude, longitude, telefone_comercial, email_comercial,
    telefone_pesquisas, email_pesquisas, aceita_pesquisas,
    cadastur_status, possui_cadastur, numero_cadastur, vencimento_cadastur,
    site, facebook, instagram, observacoes, id_origem, contato, cargo_contato
)
VALUES
    -- Hotel Serra Azul (completo)
    (
        '11111111-1111-4111-8111-111111111111', 1,
        'Hotel Serra Azul', 'Serra Azul Hospedagem Ltda.', '54.839.271/0001-64',
        '5510801', 'ATIVO', NULL, NULL, '2018-03-15',
        'Av. das Palmeiras, 120, Cidade Exemplo - SP', 'Centro',
        -22.0174, -47.8908, '+55 16 3333-1000', 'contato@serra-azul.example',
        '+55 16 99999-1000', 'pesquisas@serra-azul.example', TRUE,
        'OBRIGATORIO', TRUE, 'CAD-OTO-000123', '2027-08-31',
        'https://www.serra-azul.example', 'https://facebook.com/hotelserraazul', 'https://instagram.com/hotelserraazul',
        'Estabelecimento completo com dados de referência do dicionário de Olímpia.', '001', 'Carlos Eduardo', 'Gerente Geral'
    ),
    -- Pousada Ipê Amarelo
    (
        '22222222-2222-4222-8222-222222222222', 1,
        'Pousada Ipê Amarelo', 'Ipê Amarelo Hospedagem Ltda.', '67.294.153/0001-60',
        '5590601', 'ATIVO', NULL, NULL, '2021-06-10',
        'Rua do Lago, 45, Cidade Exemplo - SP', 'Jardim das Flores',
        -22.0111, -47.9012, '+55 16 3333-2000', 'contato@ipe-amarelo.example',
        '+55 16 98888-2000', 'pesquisas@ipe-amarelo.example', TRUE,
        'OBRIGATORIO', FALSE, NULL, NULL,
        NULL, NULL, NULL,
        NULL, NULL, NULL, NULL
    ),
    -- Hotel Vale do Sol (inativo)
    (
        '33333333-3333-4333-8333-333333333333', 1,
        'Hotel Vale do Sol', 'Vale do Sol Turismo Ltda.', '81.937.462/0001-31',
        '5510801', 'INATIVO', 'Encerramento de atividades informado pela administração.', '2026-09-15 16:45:00+00', '2012-09-20',
        'Rodovia Municipal, km 4, Cidade Exemplo - SP', 'Zona Rural',
        -22.0350, -47.8650, '+55 16 3333-3000', 'contato@vale-sol.example',
        '+55 16 97777-3000', 'pesquisas@vale-sol.example', FALSE,
        'OPCIONAL', FALSE, NULL, NULL,
        NULL, NULL, NULL,
        NULL, NULL, NULL, NULL
    ),
    -- Hospedagem em Cadastro (exemplo de cadastro inicial incompleto do OpenAPI)
    (
        '44444444-4444-4444-8444-444444444444', 1,
        'Hospedagem em Cadastro', 'Hospedagem em Cadastro Ltda.', '12.345.678/0001-95',
        NULL, 'ATIVO', NULL, NULL, NULL,
        'Rua de Exemplo, 10, Cidade Exemplo - SP', NULL,
        NULL, NULL, NULL, NULL,
        NULL, NULL, TRUE,
        'OBRIGATORIO', FALSE, NULL, NULL,
        NULL, NULL, NULL,
        'Exemplo de cadastro inicial incompleto persistido com dados mínimos.', NULL, NULL, NULL
    )
ON CONFLICT (id_estabelecimento) DO NOTHING;

-- Atualiza inativado_em para o estabelecimento inativo
UPDATE estabelecimentos
SET inativado_em = '2026-09-15 16:45:00+00'
WHERE id_estabelecimento = '33333333-3333-4333-8333-333333333333'
  AND inativado_em IS NULL;

-- ──────────────────────────────────────────────────────────
-- MEIOS DE HOSPEDAGEM (Relação 1:1)
-- ──────────────────────────────────────────────────────────

INSERT INTO meio_hospedagem (
    id_estabelecimento, tipo_hospedagem, total_uh, total_leitos, uh_pcd,
    func_fixos, func_temporarios, funcionamento_24h,
    checkin_horario, checkout_horario, formas_pagamento,
    horario_funcionamento_descritivo, horario_checkin_checkout_descritivo,
    reservas, infraestrutura
)
VALUES
    (
        '11111111-1111-4111-8111-111111111111',
        'HOTEL', 48, 96, 3, 18, 4, TRUE,
        '14:00:00', '12:00:00',
        '["PIX", "CREDITO", "DEBITO", "DINHEIRO"]'::jsonb,
        '24 horas, todos os dias', 'Check-in às 14h / Check-out às 12h',
        'Site próprio, telefone, WhatsApp e OTAs',
        '{"wifi": true, "academia": true, "pcd_rampa": true, "restaurante": true, "pcd_elevador": true, "estacionamento": true, "piscina_adulto": true, "pcd_sanitario_adaptado": true}'::jsonb
    ),
    (
        '22222222-2222-4222-8222-222222222222',
        'POUSADA', 16, 34, 1, 6, 2, FALSE,
        '15:00:00', '11:00:00',
        '["PIX", "CREDITO", "DINHEIRO"]'::jsonb,
        NULL, NULL, NULL,
        '{"wifi": true, "pcd_rampa": true, "estacionamento": true, "pcd_sanitario_adaptado": true}'::jsonb
    ),
    (
        '33333333-3333-4333-8333-333333333333',
        'HOTEL_FAZENDA', 30, 72, 2, 12, 8, TRUE,
        '14:00:00', '12:00:00',
        '["PIX", "CREDITO", "DEBITO"]'::jsonb,
        NULL, NULL, NULL,
        '{"wifi": true, "pcd_rampa": true, "restaurante": true, "estacionamento": true, "piscina_adulto": true}'::jsonb
    )
    -- Nota: '44444444-4444-4444-8444-444444444444' propositalmente não possui meio_hospedagem (cadastro incompleto)
ON CONFLICT (id_estabelecimento) DO NOTHING;

-- ──────────────────────────────────────────────────────────
-- DOCUMENTOS DE CONTROLE
-- ──────────────────────────────────────────────────────────

INSERT INTO documentos_controle (
    id_documento, id_estabelecimento, tipo_documento, numero,
    data_emissao, data_vencimento, status,
    nome_arquivo, content_type, tamanho_bytes, checksum_sha256,
    caminho_storage, enviado_em
)
VALUES
    (
        1001, '11111111-1111-4111-8111-111111111111', 'ALVARA', 'ALV-2026-0042',
        '2026-01-10', '2027-01-10', 'REGULAR',
        'alvara-funcionamento.pdf', 'application/pdf', 245760, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        'estabelecimentos/11111111-1111-4111-8111-111111111111/docs/alvara-funcionamento.pdf', '2026-10-20 14:30:00+00'
    ),
    (
        1002, '11111111-1111-4111-8111-111111111111', 'AVCB', 'AVCB-2025-0781',
        '2025-12-01', '2026-11-30', 'A_VENCER',
        'avcb.pdf', 'application/pdf', 311296, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b856',
        'estabelecimentos/11111111-1111-4111-8111-111111111111/docs/avcb.pdf', '2026-10-20 14:32:00+00'
    ),
    (
        1003, '11111111-1111-4111-8111-111111111111', 'VIGILANCIA_SANITARIA', 'VS-2026-0118',
        '2026-02-01', '2027-02-01', 'REGULAR',
        'licenca-sanitaria.pdf', 'application/pdf', 198144, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b857',
        'estabelecimentos/11111111-1111-4111-8111-111111111111/docs/licenca-sanitaria.pdf', '2026-10-20 14:34:00+00'
    ),
    (
        1004, '22222222-2222-4222-8222-222222222222', 'ALVARA', 'ALV-2026-0112',
        '2026-04-10', '2027-04-10', 'REGULAR',
        'alvara-pousada.pdf', 'application/pdf', 184320, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b858',
        'estabelecimentos/22222222-2222-4222-8222-222222222222/docs/alvara-pousada.pdf', '2026-10-21 10:00:00+00'
    ),
    (
        1005, '33333333-3333-4333-8333-333333333333', 'AVCB', 'AVCB-2024-0098',
        '2024-01-15', '2025-01-15', 'VENCIDO',
        'avcb-vencido.pdf', 'application/pdf', 276480, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b859',
        'estabelecimentos/33333333-3333-4333-8333-333333333333/docs/avcb-vencido.pdf', '2026-09-10 12:00:00+00'
    )
ON CONFLICT (id_documento) DO NOTHING;

SELECT setval(
    pg_get_serial_sequence('documentos_controle', 'id_documento'),
    COALESCE((SELECT MAX(id_documento) FROM documentos_controle), 1),
    true
);

-- ──────────────────────────────────────────────────────────
-- USUÁRIOS  (10 registros)
--   Perfis: 1 ADMINISTRADOR, 2 GESTORES, 3 EDITORES, 4 HOTEL
--   Estados: ATIVO, INATIVO, PENDENTE
-- ──────────────────────────────────────────────────────────

INSERT INTO usuarios (id, email, senha_hash, perfil, status, nome)
VALUES
    -- administrador
    (1,  'marina.admin@example.test',
         '$argon2id$v=19$m=65536,t=3,p=4$S5bVApVpPHZC0nGldoIF+w$6SzLIl5nSGKyRIRRcBSEQUmw4bZ/kCLm6R/i9iH7RXs',
         'ADMINISTRADOR', 'ATIVO',   'Marina Administradora'),

    -- gestores
    (2,  'rafael.consulta@example.test',
         '$argon2id$v=19$m=65536,t=3,p=4$q0E6vTL2Sdo72lB3LLpSWQ$LzoxEScoJSp/lDjxMzg7kUq3do+QfrrMlEpTmltzRto',
         'GESTOR',        'ATIVO',   'Rafael Consulta'),
    (3,  'fernanda.gestora@example.test',
         '$argon2id$v=19$m=65536,t=3,p=4$JiD8g1HN87xm4VgxxDi0uA$oymEEpGEoI+e1KUW7D9l+5Ok/UtlYAuGO/N21eiO/bk',
         'GESTOR',        'INATIVO', 'Fernanda Gestora'),   -- desligada

    -- editores
    (4,  'camila.editora@example.test',
         '$argon2id$v=19$m=65536,t=3,p=4$mM9XgOMhc4UOg+05ecgpOw$r9uz79iFW+l9XxuBz3f0X6pcIhNyg8e5s4viDUYhpEI',
         'EDITOR',        'ATIVO',   'Camila Editora'),
    (5,  'bruno.editor@example.test',
         '$argon2id$v=19$m=65536,t=3,p=4$JwP85CimiNcgZLt4V+4r0w$nc3oErqW00gWMtdWUMWDq5IXZ4S+OzTImOZTIZm0Fvc',
         'EDITOR',        'ATIVO',   'Bruno Editor'),
    (6,  'juliana.editor@example.test',
         '$argon2id$v=19$m=65536,t=3,p=4$vUA5PBmaE4R7SYMOu73bQg$8P/dPpqx/GpRm6ZueR9Cz2QcaPMSBdjJ/mJV1bcnPsI',
         'EDITOR',        'PENDENTE', 'Juliana Editora')    -- convite pendente
ON CONFLICT (email) DO NOTHING;

INSERT INTO usuarios (id, email, senha_hash, perfil, status, nome, id_estabelecimento)
VALUES
    -- hotéis (vínculo obrigatório com estabelecimento)
    (7,  'responsavel@serra-azul.example',
         '$argon2id$v=19$m=65536,t=3,p=4$lhxXXlAIGhQX9FAOwOxMfQ$vYo7Nrtn5GxlrC2B5cAOHnsFfmgJTT0wGi+oI7BHXds',
         'HOTEL', 'ATIVO',    'Responsável Serra Azul',
         '11111111-1111-4111-8111-111111111111'),
    (8,  'responsavel@ipe-amarelo.example',
         '$argon2id$v=19$m=65536,t=3,p=4$tuPL/GxOjrrFgwG6FNgYcA$YIVbkQ+qY/vJCOOnSSULGw1HiwChTcL2lAtu/ayRNJk',
         'HOTEL', 'ATIVO',    'Responsável Ipê Amarelo',
         '22222222-2222-4222-8222-222222222222'),
    (9,  'hotel.valedosol@example.test',
         '$argon2id$v=19$m=65536,t=3,p=4$rc9RmVeq4fG1/ZoiqjGEfA$TBaWpYy03+0eX0fFc024nza6ENHTb1xrQKtU29lsYz0',
         'HOTEL', 'ATIVO',    'Responsável Vale do Sol',
         '33333333-3333-4333-8333-333333333333'),
    (10, 'hotel.cadastro@example.test',
         '$argon2id$v=19$m=65536,t=3,p=4$gyVF0yMiq6DxB/fdWvI4xg$RhKskBwu9iv6qQ1hVWQAiF2Sn7ShCEqunjSnGuXdbxI',
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
        'responsavel@serra-azul.example', 'HOTEL',
        1, '11111111-1111-4111-8111-111111111111',
        'ACEITO',
        '2026-02-10 23:59:59-03',
        '2026-02-05 14:32:00-03'),

    (2, 'b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3',
        'responsavel@ipe-amarelo.example', 'HOTEL',
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
         '{"email":"responsavel@serra-azul.example","perfil":"HOTEL"}',
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
