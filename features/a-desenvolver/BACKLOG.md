# Backlog de coordenação — Orca (features 01 + 02)

Run Orca: `run_2b2ba472438b`. Coordenador: esta sessão Claude (Sonnet 5), rodando no worktree
`C:\Users\felip\orca\workspaces\myglico\doliolid` (branch `felipe-cale/doliolid`).

## Estado real do repositório (inspecionado em 2026-10-06)

- Backend FastAPI (`app/`) hoje é 100% público: nenhuma UserAccount, Doctor, sessão,
  criptografia, SHORTID ou vínculo existe. `Patient.name`/`Patient.email` são colunas
  em claro. Rotas (`app/api/routes.py`) não têm nenhuma autorização.
- `app/models/entities.py`: Patient, DataSource, ImportBatch, PatientSourceLink,
  RawImportRecord, GlucoseRecord, GlucoseRecordSource, DataQualityIssue,
  ProvenanceEvent, ProvenanceArtifact, DailyMetricsCurrent, AnalysisRun,
  DailyIndicator, AnalysisOutbox. `ProvenanceEvent` já tem campos genéricos
  (activity_type, entity_type, entity_id, actor_user_id, source_type, source_id,
  occurred_at, prov_json, metadata_json, content_hash) — **reutilizar esta tabela**
  para os eventos dos dois SDDs em vez de criar um log paralelo.
- `AnalysisOutbox` já existe mas é específico de reprocessamento de analytics — não é
  uma outbox genérica; CSCW precisa da sua própria outbox/notificação durável.
- Migrações: `alembic/versions/20260414_0001_initial.py`,
  `20260504_0002_clinical_core_uuid.py`. Uma única cadeia linear até agora.
- `pyproject.toml` já inclui `cryptography>=42.0.0` (AES-GCM disponível). Não há
  `pytest` instalado nem testes de backend além de `tests/test_clinical_pdf.py`.
- Frontend `frontend-react/` (Vite + React 18 + react-router-dom + i18next, 3 locales
  pt-BR/en-US/es) não tem nenhuma infra de teste (sem vitest/playwright).
- `app/main.py` não tem SessionMiddleware nem CORS/auth configurados.
- `app/core/config.py`: settings via `MYGLICO_` env prefix — chaves de criptografia
  devem seguir essa convenção (nome + finalidade, sem valor no repo).

## Ferramentas de delegação confirmadas

- CLI `orca` (242 comandos) com orquestração real: `orca orchestration worker-start
  --agent <codex|claude|antigravity|opencode|...> --worktree current`. Contas
  confirmadas ativas: **codex** (oauth), **antigravity** (sessão ok), **claude**
  (esta própria sessão). `opencode` sem conta listada em `account list`, mas aceito
  como `--agent` (usa config própria) — será testado no momento do despacho E2E.
- **MCP Playwright**: indisponível. Fallback adotado: Playwright real instalado como
  devDependency de `frontend-react` e executado via CLI/test runner (não leitura de
  código, não mock). O `orca` também expõe automação de navegador nativa
  (`orca tab/goto/snapshot/click/fill/...`), usada pelo coordenador para inspeção
  manual pontual — não substitui a suíte versionada.
- Revisor independente: um worker **claude** novo, dispatch dedicado, que só lê e
  nunca edita, acionado após a integração de backend+frontend+E2E.

## Distribuição de agentes (conforme PROMPT-ORCA.md, ajustada à disponibilidade real)

| Agente Orca | Responsabilidade | Worktree |
| --- | --- | --- |
| codex | Modelo de dados, migrações, criptografia/índices cegos, SHORTIDs, sessão/autorização, vínculos, CSCW/proveniência, importador UCI | current (owns `app/`, `alembic/`, `scripts/import_uci_diabetes.py`) |
| antigravity | Frontend React: landing pública, cadastro/login, busca/vínculos, investigações, popup/filtros de dias atípicos, notificações, 3 idiomas, acessibilidade | current (owns `frontend-react/src/`) |
| opencode | Suíte E2E Playwright real + fixtures sintéticas + testes de integração complementares | current (owns `tests/e2e/`, `frontend-react/tests-e2e` ou equivalente a definir) |
| claude (coordenador, esta sessão) | Contratos, dependency graph, integração, decisões de conflito, migração/validação final, preenchimento da matriz de aceite | current |
| claude (revisor dedicado) | Revisão independente final contra os dois SDDs e a matriz de 68 critérios | leitura apenas, sem edição |

## Decisões de arquitetura fixadas pelo coordenador

1. **Sessão**: cookie HttpOnly+Secure+SameSite=Lax com identificador opaco
   validado contra uma tabela `user_sessions` no servidor a cada requisição
   (não JWT stateless) — permite invalidação imediata em logout/revogação de
   conta. Autorização de recursos (vínculo/investigação) é sempre recalculada
   no servidor a partir do estado atual do banco, nunca confiada ao token.
2. **Criptografia autenticada**: AES-256-GCM via `cryptography` (biblioteca já
   presente), nonce de 12 bytes por operação, AAD = `f"{tabela}:{coluna}:{id}"`
   (ou equivalente) para impedir troca de ciphertext entre registros, versão de
   chave armazenada junto ao payload. Chaves via variáveis de ambiente
   `MYGLICO_*` carregadas apenas no backend; nunca persistidas no banco.
3. **Índice cego**: HMAC-SHA256 com chave separada da de criptografia, para
   `email`, `(crm, uf)` normalizado. Normalização de e-mail: lowercase + trim.
4. **SHORTID**: 6 caracteres `A-Z0-9` maiúsculos, CSPRNG, retry em colisão via
   constraint UNIQUE por tabela (Patient e Doctor separadamente).
5. **Proveniência**: reaproveitar `ProvenanceEvent` (não criar tabela paralela);
   mapear os eventos obrigatórios do SDD2 (`AssociationRequested`,
   `AssociationConfirmed`, ... `NotificationRead`) para `activity_type`.
6. **Associação paciente-médico**: nova tabela `patient_doctor_links` (N:N com
   estado PENDING/ACTIVE/REJECTED/CANCELLED/REVOKED, versionamento otimista).
7. **Investigation/Message/Notification**: novas tabelas, nomes a definir pelo
   Codex seguindo convenções do projeto (snake_case, `String(36)` uuid pk como
   o resto do schema).

## Grafo de dependências (tasks Orca)

```
B1 (codex: modelo+migração+cripto+SHORTID)
 └─> B2 (codex: auth/sessão/busca médico)
      └─> B3 (codex: ciclo de vínculo + proveniência + notificações)
           └─> B4 (codex: CSCW investigações + convite dia atípico + outbox)
                └─> B5 (codex: importador UCI idempotente)
                     ├─> F1 (antigravity: frontend completo contra API real)
                     └─> E1 (opencode: suíte E2E Playwright + integração)
                          └─> R1 (claude revisor: parecer final — aprovado/reprovado)
```

B1–B5 rodam sequencialmente no mesmo terminal Codex (mesmo worktree) para preservar
contexto de decisões de arquivamento e evitar heads concorrentes do Alembic. F1 e E1
começam só depois de B5 (contratos de API estáveis) — SDD exige validação contra
backend real, não mocks.

## Log de progresso

- 2026-10-06 22:03 — Run criado (`run_2b2ba472438b`). Pasta `features/a-desenvolver`
  copiada de `D:\work\myglico` (preexistente, sem conflito). Despachando B1 ao codex.
- 2026-10-06 — B1 (modelo fundacional) concluido. Arquivos alterados: `app/models/entities.py`, `app/models/__init__.py`, `app/core/config.py`, `app/core/crypto.py`, `app/core/CRYPTO_CONFIGURATION.md`, `app/services/reports.py`, `alembic/versions/20261006_0003_accounts_encryption.py`, `scripts/validate_foundational_security.py` e `scripts/validate_account_migration.py`. Comandos e resultados: `python -m alembic upgrade head` em SQLite isolado vazio — PASSOU; `python scripts/validate_account_migration.py` — PASSOU com cifra de nome/e-mail legados, remocao das colunas em claro e preservacao de IDs/FK; `python scripts/validate_foundational_security.py` — PASSOU com consulta SQL direta sem valores sensiveis, hashes scrypt distintos, verificacao de senha e retry de SHORTID; `python -m compileall -q ...` — PASSOU; `git diff --check` — PASSOU. Nao havia `data/myglico.db` para copiar. Coordenacao Orca: `orca orchestration check` indisponivel (`runtime_unavailable`, runtime nao encontrado).

  `git status --short` ao concluir:
  ```text
   M app/core/config.py
   M app/models/__init__.py
   M app/models/entities.py
   M app/services/reports.py
  ?? alembic/versions/20261006_0003_accounts_encryption.py
  ?? app/core/CRYPTO_CONFIGURATION.md
  ?? app/core/crypto.py
  ?? features/
  ?? scripts/validate_account_migration.py
  ?? scripts/validate_foundational_security.py
  ```
- 2026-10-06 22:16 — Launcher `codex` inicialmente reportou `agent_unconfigured`;
  usuário habilitou nas configurações do Orca e funcionou no retry. Testes de ping
  confirmaram `claude`, `antigravity` e `opencode` operacionais via
  `orca orchestration worker-start`. Nota: Antigravity pede confirmação de shell
  por padrão (travaria `check --wait` longos) — ver memória
  `feedback_orca_antigravity_confirmations`; usar checks curtos e aprovar os
  prompts manualmente quando necessário. B1 real despachado ao codex em
  `term_0473947c-b234-4f5e-b865-695a28e13167` (task `task_17505c85f23b`,
  dispatch `ctx_97cf481ab9ab`), turno confirmado iniciado. Um dispatch de teste
  anterior (`ctx_c280d17fdc0f`, terminal `term_5b44d7c0...`) ficou preso sem
  chamar `worker_done` via shell; não bloqueia o trabalho real, será limpo
  separadamente.
- 2026-10-06 22:20 — Escrito `features/a-desenvolver/CONTRATOS-API.md` (contrato
  de rotas acordado entre backend e frontend). Paralelizando conforme pedido do
  usuário: despachado **F1** (antigravity, frontend completo das duas features
  contra o contrato, terminal `term_a058bf02...`, task `task_0a4998627799`) e
  **E1** (opencode, infraestrutura E2E Playwright + fixtures + esqueletos dos
  10 grupos de fluxo/68 critérios, terminal `term_97662e32...`, task
  `task_500cfe27fa91`) simultaneamente ao **B1** do codex (já em andamento,
  terminal `term_0473947c...`). Os três rodam em paralelo no mesmo worktree,
  com propriedade de arquivos separada (app/+alembic vs frontend-react/src vs
  novo diretório de testes e2e). F1/E1 foram instruídos a construir contra o
  contrato mesmo com o backend incompleto (não é mock final - é o mesmo
  contrato que o backend vai implementar) e a não pedir confirmação a cada
  passo.
- 2026-10-06 22:30 — **Limitação confirmada**: o Codex não consegue chamar
  `orca orchestration check/send` de dentro do seu próprio processo neste
  ambiente (`runtime_unavailable`/`runtimeId: null`), mesmo com o terminal
  `live` e conectado. B1 foi verificada manualmente pelo coordenador (arquivos
  no disco, `git status --short` confere com o relatado). Decisão: para
  **codex**, não usar `worker-start`/`check --wait` para settlement — dirigir
  diretamente via `orca terminal send` nesse mesmo terminal
  (`term_0473947c...`) e verificar progresso por `terminal read` + pelas
  próprias entradas que ele escreve neste BACKLOG.md. B2 (auth/sessão/busca de
  médico/proteção das rotas antigas) despachada por esse caminho.
- 2026-10-06 - B2 (autenticacao, sessao e autorizacao) concluida. Arquivos deste passo: `app/api/routes.py`, `app/core/config.py`, `app/core/security.py`, `app/main.py`, `app/models/entities.py`, `app/models/__init__.py`, `app/services/auth_service.py`, `app/services/reports.py`, `alembic/versions/20261006_0004_user_sessions.py`, `app/core/CRYPTO_CONFIGURATION.md` e `scripts/validate_auth_flows.py`. Resultados: `python scripts/validate_auth_flows.py` - PASSOU (cadastro/login/sessao/logout de paciente e medico, cookie Secure/HttpOnly/SameSite=Lax, 401 sem sessao, tentativa admin rejeitada sem ecoar senha, acesso cruzado negado, listagem limitada ao paciente e busca de medico com allowlist); `python scripts/validate_account_migration.py` - PASSOU; `python scripts/validate_foundational_security.py` - PASSOU; `python -m compileall -q ...` - PASSOU; `git diff --check` - PASSOU. Migracao validada em SQLite temporario isolado; nenhum banco de producao foi acessado. A busca retorna `link_status: none` nesta etapa, pois a tabela de vinculos pertence a B3; medicos ficam sem acesso a pacientes ate existir vinculo ativo persistido.

  `git status --short` registrado apos validacao:
  ```text
   M app/api/routes.py
   M app/core/config.py
   M app/main.py
   M app/models/__init__.py
   M app/models/entities.py
   M app/services/reports.py
   M frontend-react/package-lock.json
   M frontend-react/package.json
  ?? alembic/versions/20261006_0003_accounts_encryption.py
  ?? alembic/versions/20261006_0004_user_sessions.py
  ?? app/core/CRYPTO_CONFIGURATION.md
  ?? app/core/crypto.py
  ?? app/core/security.py
  ?? app/services/auth_service.py
  ?? features/
  ?? frontend-react/e2e/
  ?? frontend-react/playwright.config.mjs
  ?? scripts/validate_account_migration.py
  ?? scripts/validate_auth_flows.py
  ?? scripts/validate_foundational_security.py
  ```
  `frontend-react/*` e o diretorio E2E foram alterados por trabalho paralelo e nao foram editados por este B2.

- 2026-10-06 19:42 (relogio deste terminal) — **E1 (opencode) entregue: infraestrutura
  E2E + fixtures + esqueletos.** Decisoes: (a) Playwright como devDependency de
  `frontend-react` (`@playwright/test@1.63.0`, chromium instalado) — teste
  empirico mostrou que specs fora do pacote nao resolvem `@playwright/test`
  (`Cannot find package`), entao a suite fica em `frontend-react/e2e/` (convencao
  Playwright) com config em `frontend-react/playwright.config.mjs` (ESM, como o
  `vite.config.mjs`); (b) testes de integracao backend ficam em
  `tests/integration/` (pytest) junto ao `tests/test_clinical_pdf.py` ja
  existente; (c) banco de teste = SQLite descartavel `data/e2e-myglico.db`
  (coberto pelo `data/*.db` do .gitignore), recriado a cada execucao por
  `frontend-react/e2e/scripts/start-backend.mjs` (delete + `alembic upgrade head`
  + uvicorn em :8001), com `reuseExistingServer: false` para que servidor de dev
  nunca sirva assercoes; (d) chaves (`MYGLICO_ENCRYPTION_KEY_V1`,
  `MYGLICO_LOOKUP_HMAC_KEY`) e senhas dos 5 perfis geradas em runtime — nenhum
  segredo em arquivo versionado; (e) `pip install ".[test]"` adicionado em
  `pyproject.toml` (pytest + httpx + `[tool.pytest.ini_options]`).
  Entregas: 10 specs (um por grupo de fluxo do PROMPT-ORCA.md) com **71 cenarios
  `test.fixme`** referenciando os **68 criterios** AUT-CA-01..23/CSCW-CA-01..45,
  fixtures (`profiles.mjs` com paciente A/B, medico A/B e conta dupla de papel,
  `api.mjs` fiel ao CONTRATOS-API, `routes.mjs` com rotas provisorias do F1),
  `test-fixtures.mjs` (sessao isolada por perfil), 7 arquivos de integracao
  (41 testes `pytest.mark.skip`) cobrindo atomicidade/rollback, concorrencia,
  criptografia/AAD, idempotencia, outbox, autorizacao e proveniencia, e READMEs
  com o mapa criterio->arquivo. Comandos executados: `npx playwright --version`
  (1.63.0), `npx playwright install chromium`, `npx playwright test --list`
  (71 testes/10 arquivos, sem subir servidores), `python -m pytest --collect-only`
  (49 testes: 41 integracao + 8 clinical_pdf). **Nenhum teste foi executado** e
  `app/`, `alembic/` e `frontend-react/src/` nao foram tocados — conforme
  combinado, os esqueletos serao preenchidos e rodados quando o coordenador
  confirmar a integracao. Pendente do F1: reconciliar `e2e/fixtures/routes.mjs`
  com o router final; pendente geral: habilitar `test.fixme`/remover skips.

  `git status --short` ao fim da tarefa:
  ```text
   M frontend-react/package-lock.json
   M frontend-react/package.json
   M pyproject.toml
  ?? frontend-react/e2e/
  ?? frontend-react/playwright.config.mjs
  ?? tests/integration/
  ```
  (alteracoes de `app/`, `alembic/` e `scripts/validate_*` sao do B1/B2 do
  codex; `features/` e preexistente nesta branch.)

- 2026-10-06 - B3 (ciclo de vinculos paciente-medico) concluida. Arquivos deste passo: `app/models/entities.py`, `app/models/__init__.py`, `app/services/doctor_links.py`, `app/api/routes.py`, `alembic/versions/20261006_0005_patient_doctor_links_notifications.py` e `scripts/validate_doctor_links.py`. A tabela `patient_doctor_links` preserva ciclos terminais, usa marcador `open_pair_key` com UNIQUE composto para impedir ciclos PENDING/ACTIVE duplicados em SQLite/MySQL e controla transicoes por `version`; `notifications` guarda destinatario, payload minimo, evento causal e leitura. Solicitar/confirmar/rejeitar/cancelar/revogar, eventos (`Association*`, `NotificationCreated`, `NotificationRead`) e notificacoes persistem na mesma transacao; confirmacao repetida e idempotente, e autorizacao de medico consulta o estado ACTIVE em cada requisicao de recurso do paciente. Busca de medico retorna somente os campos permitidos e o estado atual none/pending/active; paciente revoga imediatamente o acesso do medico e qualquer participante pode revogar.

  Comandos/resultados: `python -m alembic upgrade head` - PASSOU no SQLite configurado localmente, cuja cadeia estava vazia; `python -m compileall -q app alembic/versions scripts/validate_doctor_links.py` - PASSOU; `python scripts/validate_doctor_links.py` - PASSOU em SQLite temporario isolado, validando CSCW-CA-01..08 e CA-10 (busca SHORTID e CRM+UF, allowlist, solicitacao+evento+notificacao, outro medico negado, aceite e replay idempotente com um unico evento, rejeicao, cancelamento, revogacoes dos dois lados, bloqueio imediato com sessao ativa, novo ciclo pendente, conflito de aceite/cancelamento, inbox/leitura e rollback de mutacao+notificacao quando a proveniencia falha); `python scripts/validate_auth_flows.py` - PASSOU como regressao B2; `git diff --check` - PASSOU. CSCW-CA-09 (investigacoes), CA-11/12 (reimportacao/provisionamento UCI) nao fazem parte das tabelas/fluxos desta entrega e permanecem para a etapa correspondente.

  `git status --short` ao concluir B3:
  ```text
   M app/api/routes.py
   M app/core/config.py
   M app/main.py
   M app/models/__init__.py
   M app/models/entities.py
   M app/services/reports.py
   M frontend-react/package-lock.json
   M frontend-react/package.json
   M pyproject.toml
  ?? alembic/versions/20261006_0003_accounts_encryption.py
  ?? alembic/versions/20261006_0004_user_sessions.py
  ?? alembic/versions/20261006_0005_patient_doctor_links_notifications.py
  ?? app/core/CRYPTO_CONFIGURATION.md
  ?? app/core/crypto.py
  ?? app/core/security.py
  ?? app/services/auth_service.py
  ?? app/services/doctor_links.py
  ?? features/
  ?? frontend-react/e2e/
  ?? frontend-react/playwright.config.mjs
  ?? scripts/validate_account_migration.py
  ?? scripts/validate_auth_flows.py
  ?? scripts/validate_doctor_links.py
  ?? scripts/validate_foundational_security.py
  ?? tests/integration/
  ```
  Alteracoes de `frontend-react/`, `pyproject.toml` e `tests/integration/` sao de trabalho paralelo e nao foram editadas neste passo.

- 2026-10-06 - B4 (investigacoes CSCW, mensagens, leitura e convites de dias atipicos) concluida. Arquivos alterados neste passo: `app/models/entities.py`, `app/models/__init__.py`, `app/api/routes.py`, `app/services/investigations.py`, `app/services/analytics.py`, `app/services/doctor_links.py`, `alembic/versions/20261006_0006_investigations_prompts.py` e `scripts/validate_investigations.py`. A revisao cria Investigation/InvestigationMessage/posicoes de leitura/prompts e NotificationOutbox; titulos e mensagens usam cifra autenticada por campo, autoria e sequencias vem do servidor, leituras sao monotonicamente idempotentes, e escrita/leitura de mensagem respeita o estado do vinculo ACTIVE e o fechamento concorrente. A revogacao B3 fecha conversas abertas do ciclo e grava evento causal na mesma transacao. O processamento analitico cria convite/notificacao/outbox deduplicados por paciente/dia sem abrir conversa; Agora nao registra evento e nao bloqueia abertura manual posterior. Conversas preservam a referencia historica ao DailyIndicator mesmo apos recalc.

  Comandos/resultados: `python scripts/validate_investigations.py` - PASSOU em banco SQLite temporario isolado, incluindo CSCW-CA-13..23, CA-26, CA-28..30 e CA-36..38: abertura com/sem evento, abertura por medico, evento de outro paciente negado, isolamento para varios medicos, autoria/sequencia/idempotencia, leitura sem evento duplicado, encerramento pelos dois papéis, tentativa de envio apos fechamento (incluindo escrita com estado OPEN obsoleto), preservacao apos reprocessamento, rollback de falha de proveniencia, outbox duravel, convite/Agora nao e notificacao apenas ao medico escolhido; `python scripts/validate_doctor_links.py` - PASSOU; `python scripts/validate_auth_flows.py` - PASSOU; `python scripts/validate_account_migration.py` - PASSOU; `python scripts/validate_foundational_security.py` com chaves efemeras em variaveis de ambiente - PASSOU; `python -m compileall -q app alembic/versions scripts/validate_investigations.py` - PASSOU; `git diff --check -- app/... alembic/versions scripts/...` - PASSOU. A checagem global `git diff --check` reportou whitespace em `frontend-react/src/App.jsx` (linhas 35/39) e `frontend-react/src/components/AppShell.jsx` (linhas 16/18), arquivos em modificacao paralela que nao foram editados por B4. Os criterios UI CSCW-CA-24/25/27 permanecem com o owner frontend, conforme limite de propriedade deste dispatch.

  `git status --short` ao concluir B4:
  ```text
   M app/api/routes.py
   M app/core/config.py
   M app/main.py
   M app/models/__init__.py
   M app/models/entities.py
   M app/services/analytics.py
   M app/services/reports.py
   M frontend-react/package-lock.json
   M frontend-react/package.json
   M frontend-react/src/App.jsx
   M frontend-react/src/api.js
   M frontend-react/src/components/AppShell.jsx
   M frontend-react/src/locales/en-US.json
   M frontend-react/src/locales/es.json
   M frontend-react/src/locales/pt-BR.json
   M frontend-react/src/pages/OverviewPage.jsx
   M frontend-react/src/pages/PatientDetailPage.jsx
   M pyproject.toml
  ?? alembic/versions/20261006_0003_accounts_encryption.py
  ?? alembic/versions/20261006_0004_user_sessions.py
  ?? alembic/versions/20261006_0005_patient_doctor_links_notifications.py
  ?? alembic/versions/20261006_0006_investigations_prompts.py
  ?? app/core/CRYPTO_CONFIGURATION.md
  ?? app/core/crypto.py
  ?? app/core/security.py
  ?? app/services/auth_service.py
  ?? app/services/doctor_links.py
  ?? app/services/investigations.py
  ?? features/
  ?? frontend-react/e2e/
  ?? frontend-react/playwright.config.mjs
  ?? frontend-react/src/components/AtypicalDaysPopup.jsx
  ?? frontend-react/src/components/DoctorLinksManager.jsx
  ?? frontend-react/src/components/InvestigationsList.jsx
  ?? frontend-react/src/components/NotificationCenter.jsx
  ?? frontend-react/src/components/ProactivePrompt.jsx
  ?? frontend-react/src/contexts/
  ?? frontend-react/src/pages/InvestigationPage.jsx
  ?? frontend-react/src/pages/LandingPage.jsx
  ?? frontend-react/src/pages/LoginPage.jsx
  ?? frontend-react/src/pages/RegisterPage.jsx
  ?? patch_app.js
  ?? patch_detail.js
  ?? patch_detail2.js
  ?? patch_detail3.js
  ?? patch_overview.js
  ?? scripts/validate_account_migration.py
  ?? scripts/validate_auth_flows.py
  ?? scripts/validate_doctor_links.py
  ?? scripts/validate_foundational_security.py
  ?? scripts/validate_investigations.py
  ?? tests/integration/
  ?? update_locales.js
  ```

### B5-FIX - credenciais publicas explicitas para a demonstracao UCI

- 2026-10-06 - Correcao pontual solicitada pelo dono do produto; esta decisao substitui o padrao de credenciais descrito na entrada B5 acima. Pacientes demo usam `patient1@email.com`, `patient2@email.com` etc., alocados sequencialmente na ordem estavel de `external_patient_code`; numeros gravados em contas existentes sao reconhecidos e mantidos em reexecucoes. A conta unica do medico demo usa `doctor@email.com`. Todas essas contas usam a senha literal `qwerty`, sempre armazenada somente como hash scrypt adaptativo com salt. O esquema e exclusivo do dataset publico UCI, documentado em `app/core/CRYPTO_CONFIGURATION.md`; o indice cego HMAC, SHORTIDs, vinculos, eventos, idempotencia e protecao contra colisao com contas nao-demo foram mantidos.
- Arquivos alterados: `app/services/uci_importer.py`, `scripts/validate_uci_demo_provisioning.py`, `app/core/CRYPTO_CONFIGURATION.md` e este `BACKLOG.md`.
- Validacao: `python -m compileall -q app/services/uci_importer.py scripts/validate_uci_demo_provisioning.py` - PASSOU; `python scripts/validate_uci_demo_provisioning.py` - PASSOU em SQLite temporario com dois pacientes; confirmou `patient1@email.com`/`patient2@email.com`, `doctor@email.com`, login HTTP dos tres com `qwerty`, emails/hashes/IDs/SHORTIDs estaveis na segunda execucao, ausencia de provisionamento sem flag e preservacao de vinculo revogado; `git diff --check` nos arquivos da correcao - PASSOU. `git status --short` foi executado; backend mostra `M app/services/uci_importer.py`, `M app/core/CRYPTO_CONFIGURATION.md`, `?? scripts/validate_uci_demo_provisioning.py` e `?? features/` (a pasta ja contem o backlog/documentos nao rastreados do trabalho B1-B5). Nenhum arquivo frontend/E2E foi editado.
  Os arquivos `frontend-react/`, `tests/integration/`, `pyproject.toml` e scripts `patch_*.js`/`update_locales.js` sao alteracoes concorrentes observadas no worktree e nao foram tocadas pelo B4.
- 2026-10-06 20:00 - F1 - antigravity implementou a UI completa (features 01 e 02) com AuthContext, LandingPage, LoginPage, RegisterPage, OverviewPage autenticada e PatientDetailPage com AtypicalDaysPopup. Build de frontend-react ok, sem erros de compilação. Próximo passo é validar contra a API real assim que codex terminar B5.
- 2026-10-06 20:05 (coordenador) — Corrigido encoding desta entrada acima (o
  antigravity gravou em UTF-16LE sobre um arquivo UTF-8, corrompendo os
  acentos); conteúdo preservado, apenas a codificação foi normalizada. B4
  (CSCW/investigações + convite de dia atípico) em andamento no codex —
  `alembic/versions/20261006_0006_investigations_prompts.py` e `Investigation`
  em `entities.py` já criados. F1 segue editando (componentes
  AtypicalDaysPopup/DoctorLinksManager/InvestigationsList/NotificationCenter/
  InvestigationPage/LandingPage/LoginPage/RegisterPage já no disco); ainda não
  enviou `worker_done`. Nota: há um `patch_app.js` solto na raiz do repo —
  provável script temporário do antigravity; verificar/remover antes da
  entrega final se não fizer parte da suíte.
- 2026-10-06 23:02 (coordenador) — **F1 concluída** (worker_done recebido via
  canal orca; antigravity retido para validação final pós-B5). **TODO de
  limpeza para a fase de integração**: `patch_app.js`, `patch_detail.js`,
  `patch_detail2.js`, `patch_detail3.js`, `patch_overview.js` e
  `update_locales.js` na raiz do repo são scripts descartáveis que o
  antigravity usou para aplicar edições pontuais — não fazem parte da
  aplicação e devem ser removidos (ou verificados como inofensivos) antes do
  diff final. B4 segue em andamento no codex.
- 2026-10-06 20:44 (coordenador) — **Backend completo (B1–B5)**. Codex entregou
  os cinco passos sequenciais com validadores próprios cobrindo AUT-CA-02,03,
  04,06,07,08,10–18 e CSCW-CA-01–23,26,28–30,34,36–38. Pendentes explicitamente
  para integração/E2E/revisor: AUT-CA-01,05,09,19,21–23, cache de frontend de
  CA-20; CSCW-CA-24,25,27,31–33,35,39–45. Despachadas duas continuações nos
  workers já retidos (via `worker-start --terminal`, reaproveitando-os de
  verdade pela orquestração): **F1b** (antigravity, terminal
  `term_a058bf02...`) — reconciliar o frontend contra a API real, subir
  backend+frontend reais contra SQLite de teste isolado e navegar os fluxos de
  verdade; **E1b** (opencode, terminal `term_97662e32...`) — preencher e
  RODAR de verdade a suíte Playwright/pytest, habilitando os `test.fixme`/
  (nota adicionada depois: F1b foi reatribuída ao codex como **F1C**, ver
  entrada abaixo — antigravity travou duas vezes)
  `skip` e preenchendo a MATRIZ-ACEITE.md com evidência real. Ambos avisados
  para não usar `data/myglico.db` de produção. Próximo passo após os dois:
  acionar o revisor independente (worker `claude` novo, só leitura).

### B5 - provisionamento explicito de contas demonstrativas UCI

- 2026-10-06 - B5 concluida. O ponto de entrada real e `scripts/import_uci_diabetes.py`, que chama `app/services/uci_importer.py`. O provisionamento ficou separado sob `--provision-demo-accounts` e nao e executado por padrao. Usa `PatientSourceLink.external_patient_code` como identidade estavel e emails reservados `doctor-uci@demo.myglico.invalid` / `patient-<external_patient_code>@demo.myglico.invalid` apenas como chaves protegidas pelo indice HMAC; senhas aleatorias sao descartadas depois do hash, sem log ou stdout. Doctor e contas demo sao localizados sem substituir contas reais; ids, SHORTIDs, hashes, ciphertexts, vinculos terminais e eventos existentes sao preservados. O vinculo ativo novo recebe somente `DemoAssociationProvisioned` com `source_type=software-agent` e `actor_kind=SoftwareImporter`, nunca aceite humano simulado.
- Arquivos deste passo: `app/services/uci_importer.py`, `scripts/import_uci_diabetes.py` e `scripts/validate_uci_demo_provisioning.py`.
- Validacao: `python scripts/validate_uci_demo_provisioning.py` - PASSOU em SQLite temporario migrado ate head; a execucao normal sem flag nao criou contas/vinculos; duas execucoes seguidas com `--provision-demo-accounts` mantiveram contagens, IDs, SHORTIDs, ciphertexts, hashes de senha, eventos, `glucose_record_sources`, `analysis_runs`, `daily_indicators` e `daily_metrics_current`; apos revogar manualmente o vinculo e repetir, o estado continuou `REVOKED`. O dataset UCI foi fixture local para nao depender de rede. `python scripts/validate_account_migration.py` - PASSOU; `python scripts/validate_auth_flows.py` - PASSOU; `python scripts/validate_doctor_links.py` - PASSOU; `python scripts/validate_investigations.py` - PASSOU; `python scripts/validate_foundational_security.py` - PASSOU usando chaves aleatorias temporarias no ambiente; `python -m compileall -q app alembic/versions scripts` - PASSOU; `git diff --check -- app/services/uci_importer.py scripts/import_uci_diabetes.py` - PASSOU. Nenhum banco dev/producao foi usado. Nota: a segunda invocacao padrao segue o comportamento existente `skip_if_loaded`; `--force` continua sendo o modo explicito preexistente para reimportacao forçada do dataset.
- Cobertura de validadores registrada ao fim de B1-B5: AUT-CA-02, 03, 04, 06, 07, 08, 10, 11, 12, 13, 14, 15, 16, 17 e 18; CSCW-CA-01..23, CA-26, CA-28..30, CA-34 e CA-36..38. AUT-CA-20 cobre sessao/logout no servidor; a limpeza de cache do frontend ainda precisa de E2E. Os casos CSCW-CA-28..30 sao exercitados nos fluxos backend descritos pelos validadores. Pendentes de validacao integrada/UX: AUT-CA-01, 05, 09, 19, 21, 22 e 23, alem do comportamento de cache de frontend de CA-20; CSCW-CA-24, 25, 27, 31..33, 35 e 39..45. Os cenarios de interface dependem de validacao frontend/E2E.
- `git status --short` executado apos as mudancas B5 (inclui alteracoes concorrentes observadas em frontend e artefatos auxiliares; nao foram editadas por B5):

  ```text
   M app/api/routes.py
   M app/core/config.py
   M app/main.py
   M app/models/__init__.py
   M app/models/entities.py
   M app/services/analytics.py
   M app/services/reports.py
   M app/services/uci_importer.py
   M frontend-react/package-lock.json
   M frontend-react/package.json
   M frontend-react/src/App.jsx
   M frontend-react/src/api.js
   M frontend-react/src/components/AppShell.jsx
   M frontend-react/src/locales/en-US.json
   M frontend-react/src/locales/es.json
   M frontend-react/src/locales/pt-BR.json
   M frontend-react/src/pages/OverviewPage.jsx
   M frontend-react/src/pages/PatientDetailPage.jsx
   M pyproject.toml
   M scripts/import_uci_diabetes.py
  ?? alembic/versions/20261006_0003_accounts_encryption.py
  ?? alembic/versions/20261006_0004_user_sessions.py
  ?? alembic/versions/20261006_0005_patient_doctor_links_notifications.py
  ?? alembic/versions/20261006_0006_investigations_prompts.py
  ?? app/core/CRYPTO_CONFIGURATION.md
  ?? app/core/crypto.py
  ?? app/core/security.py
  ?? app/services/auth_service.py
  ?? app/services/doctor_links.py
  ?? app/services/investigations.py
  ?? features/
  ?? frontend-react/e2e/
  ?? frontend-react/playwright.config.mjs
  ?? frontend-react/src/components/AtypicalDaysPopup.jsx
  ?? frontend-react/src/components/DoctorLinksManager.jsx
  ?? frontend-react/src/components/InvestigationsList.jsx
  ?? frontend-react/src/components/NotificationCenter.jsx
  ?? frontend-react/src/components/ProactivePrompt.jsx
  ?? frontend-react/src/contexts/
  ?? frontend-react/src/pages/InvestigationPage.jsx
  ?? frontend-react/src/pages/LandingPage.jsx
  ?? frontend-react/src/pages/LoginPage.jsx
  ?? frontend-react/src/pages/RegisterPage.jsx
  ?? patch_app.js
  ?? patch_detail.js
  ?? patch_detail2.js
  ?? patch_detail3.js
  ?? patch_overview.js
  ?? scripts/validate_account_migration.py
  ?? scripts/validate_auth_flows.py
  ?? scripts/validate_doctor_links.py
  ?? scripts/validate_foundational_security.py
  ?? scripts/validate_investigations.py
  ?? scripts/validate_uci_demo_provisioning.py
  ?? tests/integration/
  ?? update_locales.js
  ```

- 2026-10-07 00:20 (coordenador) — **Antigravity (F1b) travou duas vezes**
  (`CLI error: program was killed: program was interrupted`), em ambos os
  casos no meio de scripts Python/Node auxiliares complexos para editar JSON
  de locale. Nas duas vezes foi recuperável via `agy --conversation=<id>`
  (retoma a mesma conversa) + reenvio de Shift+Tab (`\x1b[Z`, ativa o modo
  `accept-edits` nativo do antigravity para prompts de criação/edição de
  arquivo). Suspeita: dois loops de supervisão rodando em paralelo mandando
  teclas ao mesmo terminal pode ter contribuído para o primeiro crash
  (corrigido, só um loop ativo agora); o segundo crash ocorreu de novo
  durante um script Python complexo mesmo com um único loop. Decisão do dono
  do produto: **reatribuir o restante da reconciliação frontend/API real
  para o codex** (0 crashes em 6 tarefas grandes B1–B5+B5-FIX), que já
  conhece a API por tê-la implementado. Antigravity foi instruído a parar
  com segurança (sem `worker_done`, dispatch `ctx_fccddc5ae2a2` deixado em
  aberto/retido, não liberado). Nova tarefa **F1C** despachada ao codex no
  mesmo terminal (`term_0473947c...`): corrigir divergências reais
  frontend/API, subir backend+frontend de teste, validar fluxos ponta a
  ponta via HTTP real, `npm run build`, conferir landing pública e os 3
  idiomas.

- 2026-10-07 00:40 (coordenador) — **Gap identificado pelo dono do produto**:
  o backend já suporta registro manual de glicemia pelo paciente
  (`POST /api/patients/{patient_id}/glucose-records`, protegido por sessão em
  `app/api/routes.py:782`, exige `principal.patient.id == patient_id`), mas
  NENHUMA tela do frontend (nem a antiga OverviewPage/PatientDetailPage nem a
  nova UI) expõe um formulário para o paciente registrar uma leitura avulsa.
  Isso não está em nenhum dos dois SDDs explicitamente (é uma funcionalidade
  pré-existente da base, não parte das features 01/02), mas o dono do produto
  pediu para completá-la agora. Fila: despachar ao codex como tarefa F1D assim
  que F1C concluir — formulário simples em PatientDetailPage (ou componente
  dedicado) chamando esse endpoint, com validação de campos, feedback de
  sucesso/erro, e string i18n nos 3 idiomas.

- 2026-10-07 — **F1C concluída (reconciliação frontend/API).** Divergências
  corrigidas: AuthContext normaliza papéis a partir de `patient`/`doctor` porque
  login/sessão não retornam `account.roles`; painel só consulta `/api/dashboard`
  e `/api/patients` para sessão de paciente; componentes usam os formatos reais
  (`{doctor}`, `{links}`, `{investigation,messages}`, estados minúsculos,
  `notification_type`, `up_to_sequence`); busca omite critérios vazios; criação
  de investigação envia somente `doctor_id` ou `patient_id` e pode referenciar o
  indicador atípico; popup agora está montado no detalhe do paciente e filtra
  datas/abre questionamento. A resposta autorizada de vínculo inclui
  `patient_id`/`doctor_id` para a seleção de investigação (mudança em
  `app/api/routes.py`). Arquivos desta reconciliação: `app/api/routes.py`,
  `frontend-react/src/api.js`, `frontend-react/src/contexts/AuthContext.jsx`,
  `frontend-react/src/components/DoctorLinksManager.jsx`,
  `frontend-react/src/components/InvestigationsList.jsx`,
  `frontend-react/src/pages/InvestigationPage.jsx`,
  `frontend-react/src/components/AtypicalDaysPopup.jsx`,
  `frontend-react/src/components/ProactivePrompt.jsx`,
  `frontend-react/src/components/NotificationCenter.jsx`,
  `frontend-react/src/pages/RegisterPage.jsx`,
  `frontend-react/src/pages/OverviewPage.jsx`,
  `frontend-react/src/pages/PatientDetailPage.jsx` e os três arquivos de
  `frontend-react/src/locales/`.

  Validação: `alembic upgrade head` passou em SQLite novo e isolado; backend
  Uvicorn e Vite foram exercitados por HTTP real em `8002` e `8000`. A porta
  `8001` já estava ocupada por um processo Python preexistente; mantive-o
  intocado e direcionei temporariamente o proxy Vite ao backend isolado em
  `8002`. Evidências: registro paciente/médico `201`; login e sessão `200`;
  logout `204`; busca SHORTID `200` (link `none` e depois `active`); solicitação
  `201`; confirmação `200`; indicador atípico consultado `200` e encontrado;
  abertura de investigação `201`; envio de mensagem `201`; detalhe com as duas
  mensagens `200`; revogação `200`; próxima leitura pelo médico da investigação
  revogada `409`; chamada sem sessão `401`. Fixture analítica isolada populou
  `analysis_runs`, `daily_indicators` e `daily_metrics_current`. Playwright
  validou cadastro/logout pela UI para os dois papéis (register `201`, logout
  `204`); no dashboard médico não houve chamadas a `/api/patients` nem
  `/api/dashboard`; landing pública carregou `200` e chamou somente
  `/api/auth/session`. Os 21 textos de integração foram encontrados e os três
  JSONs parsearam: `pt-BR`, `en-US`, `es`. `git diff --check` passou.
  `npm run build` passou (887 módulos,
  bundle JS ~737 kB; Vite reportou apenas o aviso de chunk >500 kB). Bancos
  SQLite temporários removidos; nenhum banco dev/prod foi usado. O smoke HTTP
  completo foi retomado após ajustar o script auxiliar para usar o campo
  correto `DailyIndicator.indicator_date`.

  `git status --short` ao concluir:
  ```text
   M app/api/routes.py
   M app/core/config.py
   M app/main.py
   M app/models/__init__.py
   M app/models/entities.py
   M app/services/analytics.py
   M app/services/reports.py
   M app/services/uci_importer.py
   M frontend-react/package-lock.json
   M frontend-react/package.json
   M frontend-react/src/App.jsx
   M frontend-react/src/api.js
   M frontend-react/src/components/AppShell.jsx
   M frontend-react/src/locales/en-US.json
   M frontend-react/src/locales/es.json
   M frontend-react/src/locales/pt-BR.json
   M frontend-react/src/pages/OverviewPage.jsx
   M frontend-react/src/pages/PatientDetailPage.jsx
   M pyproject.toml
   M scripts/import_uci_diabetes.py
  ?? alembic/versions/20261006_0003_accounts_encryption.py
  ?? alembic/versions/20261006_0004_user_sessions.py
  ?? alembic/versions/20261006_0005_patient_doctor_links_notifications.py
  ?? alembic/versions/20261006_0006_investigations_prompts.py
  ?? app/core/CRYPTO_CONFIGURATION.md
  ?? app/core/crypto.py
  ?? app/core/security.py
  ?? app/services/auth_service.py
  ?? app/services/doctor_links.py
  ?? app/services/investigations.py
  ?? features/
  ?? frontend-react/e2e/
  ?? frontend-react/patch_en.js
  ?? frontend-react/patch_locales.cjs
  ?? frontend-react/playwright.config.mjs
  ?? frontend-react/src/components/AtypicalDaysPopup.jsx
  ?? frontend-react/src/components/DoctorLinksManager.jsx
  ?? frontend-react/src/components/InvestigationsList.jsx
  ?? frontend-react/src/components/NotificationCenter.jsx
  ?? frontend-react/src/components/ProactivePrompt.jsx
  ?? frontend-react/src/contexts/
  ?? frontend-react/src/pages/InvestigationPage.jsx
  ?? frontend-react/src/pages/LandingPage.jsx
  ?? frontend-react/src/pages/LoginPage.jsx
  ?? frontend-react/src/pages/RegisterPage.jsx
  ?? patch_app.js
  ?? patch_detail.js
  ?? patch_detail2.js
  ?? patch_detail3.js
  ?? patch_locales.py
  ?? patch_overview.js
  ?? scripts/validate_account_migration.py
  ?? scripts/validate_auth_flows.py
  ?? scripts/validate_doctor_links.py
  ?? scripts/validate_foundational_security.py
  ?? scripts/validate_investigations.py
  ?? scripts/validate_uci_demo_provisioning.py
  ?? test_validation.db
  ?? tests/integration/
  ?? update_locales.js
  ```

- 2026-10-07 — **F1D concluída (registro manual de glicemia pelo paciente).**
  Novo componente `frontend-react/src/components/ManualGlucoseEntryForm.jsx`
  (data/hora `datetime-local` com valor padrão "agora", glicemia validada
  `> 0` e `<= 1000` mg/dL como no `Field(gt=0, le=1000)` do backend, contexto
  opcional via select com os códigos já existentes em `enums.context` +
  "Outro (descrever)" com texto livre até 80 caracteres, observações
  opcionais, feedback de sucesso/erro com `role=status/alert`). Nova função
  `createManualGlucoseRecord(patientId, payload)` em `frontend-react/src/api.js`
  chamando `POST /api/patients/{patient_id}/glucose-records`. Em
  `PatientDetailPage.jsx` o formulário só é montado quando
  `session.patient.id === patient.id` (médico vinculado não vê). Após sucesso
  a página reaproveita o fetch existente (`reloadToken` no `requestKey` +
  recarga silenciosa, sem trocar a página pelo estado de carregamento); se a
  leitura cair fora do período exibido, a janela passa a terminar na data da
  leitura (30 dias). Estilos mínimos em `frontend-react/src/styles.css`
  reutilizando `react-panel--filter`/`react-filter-form`. 20 strings novas em
  `manualEntry.*` nos três locales (chaves idênticas conferidas por script).
  Algoritmo de dias atípicos e gráficos/cards não foram alterados.

  Correção necessária encontrada na validação: o detalhamento de um paciente
  **sem nenhuma leitura** ficava em branco (`formatDate(null)` →
  `RangeError: Invalid time value`), impedindo o paciente novo de registrar a
  primeira leitura. `formatDateBase`/`formatShortDateBase` agora retornam "-"
  para data ausente.

  Validação: `npm run build` passou (888 módulos; só o aviso pré-existente de
  chunk >500 kB). Playwright ad hoc (spec temporário em `e2e/.artifacts/`,
  removido ao final) contra backend Uvicorn real em `:8012` com SQLite
  descartável + `alembic upgrade head` e Vite em `:8010` (portas `8000`/`8001`
  ocupadas por processos preexistentes, mantidos intocados): registro
  paciente/médico `201`; detalhamento do paciente sem leituras `200` e
  formulário visível; validação client-side de 1500 mg/dL exibiu erro; submit
  real `POST glucose-records` `201` (`187.5`, contexto "jejum"); refetch do
  detalhamento `200` e leitura exibida em "Últimos registros do período";
  numa execução anterior com leitura semeada em 05/10 e nova em 06/10, a
  janela avançou e a leitura apareceu. Vínculo solicitado `201` e confirmado
  `200`; médico abriu o detalhamento `200`, viu a leitura e **não** viu o
  formulário; `POST` do médico no mesmo endpoint `403`. Observações: (1) a
  média diária do novo dia fica "-" até o worker de análise processar o
  outbox (`analytics_status: stale`), comportamento do backend; (2)
  `playwright.config.mjs` gera `MYGLICO_*_KEY` em base64, mas
  `app/core/crypto.py` exige 64 caracteres hex — o registro retorna 500 com a
  config oficial (usei hex no spec ad hoc); vale corrigir a config E2E.

  `git status --short` ao concluir:
  ```text
   M app/api/routes.py
   M app/core/config.py
   M app/main.py
   M app/models/__init__.py
   M app/models/entities.py
   M app/services/analytics.py
   M app/services/reports.py
   M app/services/uci_importer.py
   M frontend-react/package-lock.json
   M frontend-react/package.json
   M frontend-react/src/App.jsx
   M frontend-react/src/api.js
   M frontend-react/src/components/AppShell.jsx
   M frontend-react/src/locales/en-US.json
   M frontend-react/src/locales/es.json
   M frontend-react/src/locales/pt-BR.json
   M frontend-react/src/pages/OverviewPage.jsx
   M frontend-react/src/pages/PatientDetailPage.jsx
   M frontend-react/src/styles.css
   M pyproject.toml
   M scripts/import_uci_diabetes.py
  ?? alembic/versions/20261006_0003_accounts_encryption.py
  ?? alembic/versions/20261006_0004_user_sessions.py
  ?? alembic/versions/20261006_0005_patient_doctor_links_notifications.py
  ?? alembic/versions/20261006_0006_investigations_prompts.py
  ?? app/core/CRYPTO_CONFIGURATION.md
  ?? app/core/crypto.py
  ?? app/core/security.py
  ?? app/services/auth_service.py
  ?? app/services/doctor_links.py
  ?? app/services/investigations.py
  ?? features/
  ?? frontend-react/e2e/
  ?? frontend-react/patch_en.js
  ?? frontend-react/patch_locales.cjs
  ?? frontend-react/playwright.config.mjs
  ?? frontend-react/src/components/AtypicalDaysPopup.jsx
  ?? frontend-react/src/components/DoctorLinksManager.jsx
  ?? frontend-react/src/components/InvestigationsList.jsx
  ?? frontend-react/src/components/ManualGlucoseEntryForm.jsx
  ?? frontend-react/src/components/NotificationCenter.jsx
  ?? frontend-react/src/components/ProactivePrompt.jsx
  ?? frontend-react/src/contexts/
  ?? frontend-react/src/pages/InvestigationPage.jsx
  ?? frontend-react/src/pages/LandingPage.jsx
  ?? frontend-react/src/pages/LoginPage.jsx
  ?? frontend-react/src/pages/RegisterPage.jsx
  ?? patch_app.js
  ?? patch_detail.js
  ?? patch_detail2.js
  ?? patch_detail3.js
  ?? patch_locales.py
  ?? patch_overview.js
  ?? scripts/validate_account_migration.py
  ?? scripts/validate_auth_flows.py
  ?? scripts/validate_doctor_links.py
  ?? scripts/validate_foundational_security.py
  ?? scripts/validate_investigations.py
  ?? scripts/validate_uci_demo_provisioning.py
  ?? test_validation.db
  ?? tests/integration/
  ?? update_locales.js
  ```

- 2026-10-07 01:15 (coordenador) — **F1D concluída** (worker_done recebido):
  `ManualGlucoseEntryForm` adicionado a `PatientDetailPage.jsx`, visível só
  para o próprio paciente (`session.patient.id === patient.id`), validado com
  Playwright real (POST 201, 403 quando médico tenta, leitura exibida,
  formulário ausente para médico). Corrigiu de quebra um bug pré-existente
  (página em branco para paciente sem leituras, `formatDate(null)`). Worker
  retido para possíveis ajustes finais. **Achado cross-cutting**: confirmado
  que `app/core/crypto.py` exige chaves em HEX (`bytes.fromhex`), mas o
  `playwright.config.mjs`/`start-backend.mjs` oficial do E1 gera em base64 —
  repassado ao opencode (E1c) corrigir antes de rodar os grupos que dependem
  de criptografia (cadastro/login).

- 2026-10-07 01:29 (coordenador) — **E1c parcial**: opencode corrigiu o
  formato de chave (hex, conforme achado do F1D) em `playwright.config.mjs`,
  investigou as 4 falhas do Grupo 1 (conclusão: provável expectativa de teste
  sobre timing/URL do redirect, não bug de app confirmado - não corrigiu a
  spec em si) e rodou os grupos 2-10, mas **não preencheu os cenários reais**
  (continuam `test.fixme`, 0 passes além do 1 já existente do Grupo 1).
  Estado real da suíte E2E: apenas 1 de ~71 cenários tem execução real
  passando; os demais são esqueleto validado (infraestrutura OK, sem
  asserções reais ainda). Decisão: despachar os grupos restantes em lotes
  menores e mais diretivos (exigindo pass/fail real por cenário antes de
  aceitar `worker_done`), em vez de pedir "grupos 2-10" de uma vez.

- 2026-10-07 02:19 (coordenador) — **E2E Grupo 2 com resultado real**: 1
  passou / 8 falharam (AUT-CA-03 passa isoladamente; demais falham por
  timeout em cenários multi-sessão). Worker retido. Padrão observado: tanto
  Grupo 1 (1/5) quanto Grupo 2 (1/9) têm taxa de aprovação baixa na suíte
  E2E automatizada, apesar do backend estar extensivamente validado por
  scripts de integração (B1-B5, todos PASS) e por validação manual via
  Playwright do próprio codex na F1C (fluxos completos funcionando de
  ponta a ponta, incluindo multi-sessão/revogação com 409 real). Hipótese:
  problema na infraestrutura/config da suíte oficial (timing de
  múltiplas sessões Playwright, não bug de produto) — a ser investigado.

- 2026-10-07 02:25 (coordenador) — **Decisão do dono do produto: pausar E2E
  (cobertura parcial real: Grupo 1 1/5, Grupo 2 1/9, achados documentados) e
  acionar o revisor independente agora.** Limpeza antes da revisão: removidos
  scripts de patch descartáveis da raiz (`patch_app.js`, `patch_detail*.js`,
  `patch_overview.js`, `patch_locales.py`, `update_locales.js`) e de
  `frontend-react/` (`patch_en.js`, `patch_locales.cjs`), além de
  `test_validation.db` e `frontend-react/playwright-report/` (artefatos de
  execução, não código). Nenhum desses era referenciado por package.json ou
  outro arquivo. Despachando agora um worker **claude** novo e independente
  (sem contexto desta implementação) para revisão final contra os dois SDDs
  e a MATRIZ-ACEITE.md.

- 2026-10-07 02:27 (coordenador) — **Discrepância encontrada**: o opencode
  afirmou no worker_done do Grupo 2 que atualizaria `MATRIZ-ACEITE.md`, mas o
  arquivo continua com os 68 critérios como "Não executado" — a atualização
  não foi de fato feita. Isso é exatamente o tipo de afirmação não verificada
  que o revisor independente deve conferir sistematicamente (relatório do
  agente vs. estado real do arquivo).

## Rodada de correção pós-revisão (REVISAO-FINAL.md: REPROVADO)

- 2026-10-07 09:30 (coordenador) — Escrito adendo em CONTRATOS-API.md
  (contexto X-Context patient|doctor, filtro `dates=`, filtro de convites
  `created` vs `deferred`). Despachadas três frentes em paralelo (só
  codex/claude, por decisão do dono do produto — antigravity/opencode fora
  desta rodada de ajuste fino):
  - **BACKEND-FIX** (codex, `term_0473947c...`): A1, A2(backend), A3(backend),
    A4, A5, A6, A9, B5, B2, A12/A14/A15 se houver tempo.
  - **FIX-FRONTEND** (claude novo, `term_354390d4...`): A2(frontend),
    A3(frontend), A7, A8, A10, A11, A13(frontend), B6.
  - **FIX-E2E** (claude novo, `term_da638f86...`): corrigir infraestrutura da
    suíte (fixture `apiSession.registerAccount`, locale/regex, healthcheck do
    backend), preencher grupos 3-10 de verdade, habilitar testes de
    integração relevantes, e **preencher a MATRIZ-ACEITE.md de verdade** para
    os 68 critérios (pode reaproveitar os veredictos do revisor como base,
    conferindo o que conseguir executar).
  Revisor independente retido (`ctx_fd0ea3f8ff59`) para nova rodada de
  revisão após as três frentes concluírem.

- 2026-10-07 10:32 (coordenador) — **Decisão de simplificação do dono do
  produto**: remove suporte a UserAccount com os dois papéis simultâneos.
  Cada UserAccount se relaciona com no máximo Patient OU Doctor, nunca
  ambos; quem quiser os dois papéis usa contas/e-mails separados. Isso torna
  o achado A3 (REVISAO-FINAL.md) e os critérios AUT-CA-19/CSCW-CA-33
  **Não aplicáveis por decisão de produto** em vez de bug a corrigir — a
  implementação do seletor de contexto `X-Context` foi cancelada. Decisão
  repassada às três frentes em andamento (backend-fix, fix-frontend, fix-e2e)
  antes de prosseguirem com esse item específico.

- 2026-10-07 07:52 (worker claude, frontend pós-revisão, task_247889b65759) —
  **Correções de frontend dos achados da REVISAO-FINAL.md** (só em
  `frontend-react/src/`):
  - **A2**: o popup envia a lista exata de dias (`dates=YYYY-MM-DD,...`) em vez
    de converter a seleção em intervalo. A lista também é usada para seleção
    contínua, para que "Limpar seleção de dias" remova só `dates` e preserve
    `start_date`/`end_date`. O detalhamento mostra chips removíveis dos dias
    selecionados e reenvia `dates` ao backend.
  - **A3**: **não implementado** por decisão do dono do produto (uma conta
    tem um único papel). O seletor de contexto e o header `X-Context`
    chegaram a ser escritos e foram removidos.
  - **A7/A9 (UI)**: o banner mostra só convites `status === "created"`, com a
    data (ou o intervalo, quando o backend consolida o lote com
    `dates`/`count`). "Ver os dias" abre o detalhamento com `dates=` exatos.
  - **A8**: no papel Médico, o `DoctorLinksManager` mostra "Meus pacientes"
    (vínculos ACTIVE) com "Ver detalhamento" (`/patients/:id`) e "Revogar".
    Pendentes e histórico ficam em uma lista separada. O "Questionar" do
    popup pré-seleciona o vínculo do paciente para o médico.
  - **A10**: popup com `role="dialog"`, `aria-modal`, foco inicial no título,
    Tab preso no diálogo, Esc fecha e devolve o foco ao botão, rótulo
    acessível no "×", estados reais de carregamento/erro (com "Tentar
    novamente"), filtro de período, "Ver no detalhamento" por dia e chips dos
    dias selecionados.
  - **A11**: a lista de questionamentos mostra contraparte, data de abertura,
    origem (dia atípico ou não) e não lidas por conversa (usa `unread_count`
    do item ou do detalhe com `page_size=1`). Há também o link global
    "Questionamentos" com o total `messages_unread` no topo. Na conversa:
    motivo de encerramento traduzido (`PARTICIPANT_CLOSED`,
    `ASSOCIATION_REVOKED`), referência ao dia atípico, destaque "Nova" nas
    mensagens não lidas, observação final opcional ao encerrar e
    `author_role`/`awaiting_role` traduzidos. Sem vínculo ativo, orienta a
    "Buscar médico".
  - **A13**: CRM e UF obrigatórios no cadastro de médico. Checkbox obrigatório
    de ciência de um aviso de privacidade simples; o aceite **não** é enviado
    ao backend, porque o payload tem `extra="forbid"`.
  - **B6**: "Carregando..." e CRM/UF passaram para i18n. Erros de
    login/cadastro têm `role="alert"`. A busca e a lista de médicos mostram
    "Demonstração" (`is_demo`) e "Declarado (não verificado)"
    (`!declared_verified`).
  - i18n: 49 chaves novas em pt-BR/en-US/es, com paridade conferida (369
    chaves em cada) e todas as chaves literais usadas no JSX resolvidas.
    Efeito colateral: os três JSON foram regravados por `json.dump`, e os
    objetos que estavam em uma linha passaram para várias linhas, sem mudança
    de conteúdo.
  - **Build**: `npm run build` OK (Vite, só o aviso de chunk > 500 kB que já
    existia).
  - **Validação**:
    - Banco UCI isolado no scratchpad (`alembic upgrade head` + importação com
      `--provision-demo-accounts`), exercitado via `TestClient`:
      - `atypical-days?dates=` filtra exatamente;
      - o médico demo vê 70 vínculos ACTIVE com `patient_id` e acessa o
        detalhe (200);
      - `unread_count` vem por conversa;
      - o encerramento com observação vira mensagem e grava
        `closed_reason=PARTICIPANT_CLOSED`.
    - Navegador: só o cadastro foi exercitado (submit desabilitado sem o
      aceite). O resto não foi validado no navegador, porque reiniciar o Vite
      apontando para o backend isolado foi bloqueado pela política de
      permissões.
  - **Pendência para o backend**: `GET /api/patients/{id}?dates=...` sem
    `start_date`/`end_date` ainda cruza os dias com o período padrão (últimos
    30 dias). Dias fora dessa janela voltam com `daily_indicators: []`. Pelo
    contrato, `dates` deveria prevalecer sobre o período, como já acontece em
    `/atypical-days`.

## Backend post-review corrections (2026-10-07)

- Product decision A3: each `UserAccount` has at most one domain profile (`Patient` or `Doctor`). Registration rejects a globally existing email with HTTP 409 before creating the second profile; using separate accounts/emails avoids ambiguous authorization. `X-Context` is deprecated in `CONTRATOS-API.md`; sessions with both profiles inserted outside the supported registration flow are invalidated.
- Fixed A1/A2: atypical indicators are selected by patient even when their `AnalysisRun.patient_id` is NULL; `dates=` is exact and authoritative over intervals/default windows, including patient details. Integration validator covers nonconsecutive days and the global run case.
- Fixed A4/A5/A6/A7/A9/B5/B2/A12: existing UCI demo credentials are not rewritten and new synthetic emails use the reserved domain; in-memory fixed-window limiting is keyed independently by IP and account/email on login, doctor search, and link request; unknown-email login runs a dummy password hash; `glucose_records.notes` is encrypted and migrated; prompts include their own dates/status while per-patient/batch notifications are consolidated; revoked doctors receive 404; added authorized provenance events/history.
- Documentation: README covers auth, role invariant, keys, demo import flag, current plaintext analytics fields, per-worker limiter limitation, migrations, and SQLite `VACUUM`. Docker Compose declares both key environment variables. A15 DDL freezing remains pending: migrations 0003-0006 still invoke `Model.__table__.create`; the VACUUM procedure is documented.
- Files changed/created by this correction: `README.md`, `docker-compose.yml`, `app/api/routes.py`, `app/core/rate_limit.py`, `app/core/security.py`, `app/services/auth_service.py`, `app/services/investigations.py`, `app/services/reports.py`, `app/services/uci_importer.py`, `app/models/entities.py`, `alembic/versions/20261007_0007_glucose_notes_encrypted.py`, `app/core/CRYPTO_CONFIGURATION.md`, `features/a-desenvolver/CONTRATOS-API.md`, `scripts/validate_auth_flows.py`, `scripts/validate_investigations.py`, `scripts/validate_account_migration.py`, `scripts/validate_foundational_security.py`, `scripts/validate_uci_demo_provisioning.py`, and this log.
- Isolated SQLite results: `python -m compileall -q app scripts` PASS; `python scripts/validate_auth_flows.py` PASS (one-role invariant, dummy hash, 401/429, exact detail dates); `python scripts/validate_investigations.py` PASS (global run, exact filters, provenance, batched prompt notice, revoked doctor 404); `python scripts/validate_uci_demo_provisioning.py` PASS (repeat import preserves credentials/IDs/links/events/readings/analytics and revoked link); `python scripts/validate_account_migration.py` PASS (patient fields and glucose notes encrypted, plaintext removed, IDs/FKs preserved); `python scripts/validate_foundational_security.py` PASS; `python scripts/validate_doctor_links.py` PASS. YAML parse of `docker-compose.yml` PASS. `docker compose config --quiet` was blocked because the restricted environment cannot read `C:\Users\felip\.docker\config.json`.
- `git status --short` (includes concurrent frontend/e2e edits; this backend correction did not modify those files):
  ```text
   M README.md
   M app/api/routes.py
   M app/core/config.py
   M app/main.py
   M app/models/__init__.py
   M app/models/entities.py
   M app/services/analytics.py
   M app/services/reports.py
   M app/services/uci_importer.py
   M docker-compose.yml
   M frontend-react/package-lock.json
   M frontend-react/package.json
   M frontend-react/src/App.jsx
   M frontend-react/src/api.js
   M frontend-react/src/components/AppShell.jsx
   M frontend-react/src/locales/en-US.json
   M frontend-react/src/locales/es.json
   M frontend-react/src/locales/pt-BR.json
   M frontend-react/src/pages/OverviewPage.jsx
   M frontend-react/src/pages/PatientDetailPage.jsx
   M frontend-react/src/styles.css
   M pyproject.toml
   M scripts/import_uci_diabetes.py
  ?? alembic/versions/20261006_0003_accounts_encryption.py
  ?? alembic/versions/20261006_0004_user_sessions.py
  ?? alembic/versions/20261006_0005_patient_doctor_links_notifications.py
  ?? alembic/versions/20261006_0006_investigations_prompts.py
  ?? alembic/versions/20261007_0007_glucose_notes_encrypted.py
  ?? app/core/CRYPTO_CONFIGURATION.md
  ?? app/core/crypto.py
  ?? app/core/rate_limit.py
  ?? app/core/security.py
  ?? app/services/auth_service.py
  ?? app/services/doctor_links.py
  ?? app/services/investigations.py
  ?? features/
  ?? frontend-react/e2e/
  ?? frontend-react/playwright.config.mjs
  ?? frontend-react/src/components/AtypicalDaysPopup.jsx
  ?? frontend-react/src/components/DoctorLinksManager.jsx
  ?? frontend-react/src/components/InvestigationsList.jsx
  ?? frontend-react/src/components/ManualGlucoseEntryForm.jsx
  ?? frontend-react/src/components/NotificationCenter.jsx
  ?? frontend-react/src/components/ProactivePrompt.jsx
  ?? frontend-react/src/contexts/
  ?? frontend-react/src/pages/InvestigationPage.jsx
  ?? frontend-react/src/pages/LandingPage.jsx
  ?? frontend-react/src/pages/LoginPage.jsx
  ?? frontend-react/src/pages/RegisterPage.jsx
  ?? scripts/validate_account_migration.py
  ?? scripts/validate_auth_flows.py
  ?? scripts/validate_doctor_links.py
  ?? scripts/validate_foundational_security.py
  ?? scripts/validate_investigations.py
  ?? scripts/validate_uci_demo_provisioning.py
  ?? tests/integration/
  ```

- 2026-10-07 10:53 (coordenador) — **BACKEND-FIX e FIX-FRONTEND concluídas**
  (worker_done real de ambos, retidos). Codex corrigiu A1, A2(backend), A4,
  A5, A6, A7(backend), A9, B2, B5, acrescentou A12, documentou A14; A3
  marcado "não aplicável" (decisão de produto). Claude-frontend corrigiu
  A2(frontend), A7(frontend), A8, A10, A11, A13, B6; build passa. A pendência
  de cruzamento `dates=`/período padrão que o frontend relatou já estava
  resolvida pelo backend-fix (reports.py). Pendente: validação visual no
  navegador (bloqueada por política de permissão ao tentar reiniciar o Vite).
  Falta apenas **FIX-E2E** concluir (em andamento: corrigindo bug real de
  arranque do webServer do Playwright — parsing de argumentos — e política de
  proxy confiável).

- 2026-10-07 (FIX-E2E, claude `term_da638f86...`, task_9e2cb1d45d99) — **Suíte
  E2E/integração corrigida e MATRIZ-ACEITE.md preenchida com execução real.**
  Só foram alterados `frontend-react/e2e/`, `frontend-react/playwright.config.mjs`,
  `tests/integration/` e `features/a-desenvolver/MATRIZ-ACEITE.md` (nada em
  `app/` nem `frontend-react/src`).
  - Infraestrutura (A16), causas confirmadas: (1) proxy Vite para
    `localhost` resolvia em ::1 e uvicorn escuta só IPv4 → 500 em todo `/api`;
    backend agora em `127.0.0.1`, e o webServer do Vite é checado em `/health`
    *através do proxy*; (2) cookie de sessão é `Secure`: frontend precisa ficar
    em host `localhost`; (3) locale do navegador fixado em `pt-BR` e textos
    lidos de `src/locales` (`fixtures/i18n.mjs`); (4)
    `apiSession.registerAccount/login/logout` adicionados; (5)
    `authenticateWithApi` chamava `apiContext.cookies()` inexistente → usa
    `storageState()`; (6) perfis fixos por execução colidiam entre testes →
    perfis únicos por teste; (7) chaves geradas na config eram diferentes no
    processo dos workers → gravadas em `process.env`; (8) portas dedicadas
    8100/8101; (9) o limite por IP do A5 (que entrou durante a rodada)
    estrangulava a suíte inteira → uvicorn E2E com `--proxy-headers`
    (confiando só em 127.0.0.1) e `X-Forwarded-For` sintético por sessão,
    com cenário próprio que prova o 429 num mesmo IP; (10) `start-backend.mjs`
    sem `shell: true` para não deixar uvicorn órfão. Novo
    `e2e/scripts/seed_atypical_days.py` roda `compute_analytics` real.
  - Decisão do dono do produto aplicada: conta com papel único; perfil
    dual-role removido; AUT-CA-19 e CSCW-CA-33 = Não aplicável (A3 deixa de
    ser achado).
  - **E2E real, execução completa final** (`npx playwright test`, 7,2 min):
    75 cenários, 0 `test.fixme` — **72 passaram, 2 falhas esperadas
    documentadas (`test.fail`), 1 skip**. Por grupo: 01 5/5 · 02 11/11 ·
    03 5/5 · 04 6/6 · 05 8/8 · 06 9/9 · 07 4/4 · 08 8 + 1 skip (CSCW-CA-29,
    B4) · 09 7 + 2 falhas esperadas (N1; A10 residual) · 10 9/9. Antes:
    61/75 fixme e 2/14 passando.
  - **pytest real** (`python -m pytest tests -q -rxXs`, rodado por mim após o
    subagente): **51 passed, 1 skipped (B4), 1 xfailed (NEW-1)** — os 41
    esqueletos viraram testes reais (+4 novos, 45 em `tests/integration/`),
    incluindo corridas reais com threads, triggers SQLite para falha
    injetada e o script de importação real com fixture UCI offline.
    `conftest.py` corrigido (chaves em hex).
  - Achados novos: **N1** (detalhamento usa a última `AnalysisRun` global →
    card zera depois da análise de outro paciente; popup diverge);
    **NEW-1** (`analytics.py` quebra com `context_label` misto None/texto em
    pandas ≥ 3); **A10 residual** (`dates=` apaga o período da URL; limpar
    dias não restaura o período). Confirmados corrigidos em execução: A1, A2,
    A4, A5, A6 (`notes` cifrado + inventário em CRYPTO_CONFIGURATION.md), A7,
    A9, A10 (dialog/foco/Esc/estados), A11 (não lidas por conversa, menu), A12
    (endpoint de proveniência), B2. Ainda abertos: B1 (no-store fora de
    `/api/investigations*`/`notifications*`/`doctor-links`), B4 (outbox sem
    consumidor), A13.
  - **MATRIZ-ACEITE.md**: 68/68 preenchidos com teste/camada, status e
    evidência — **Aprovado 60 · Reprovado 2 (CSCW-CA-23 por N1, CSCW-CA-25
    por A10 residual) · Parcial 4 (AUT-CA-21, CSCW-CA-22, CSCW-CA-26,
    CSCW-CA-29) · Não aplicável 2 (AUT-CA-19, CSCW-CA-33)**; contagem
    conferida relendo o arquivo.

- 2026-10-07 12:04 (coordenador) — **FIX-E2E concluída (worker_done real)**.
  Suíte E2E: 75 cenários, 0 fixme, **72 pass**, 2 falhas esperadas
  documentadas (N1, A10-residual), 1 skip (B4). pytest: 51 passed, 1 skipped,
  1 xfailed. **MATRIZ-ACEITE.md 68/68 preenchida de verdade**: 60 Aprovado, 2
  Reprovado (N1, A10-residual — novos achados menores), 4 Parcial
  (AUT-CA-21, CSCW-CA-22/26/29), 2 Não aplicável (AUT-CA-19/CSCW-CA-33, dual
  role). Dois achados novos para corrigir: **N1** (card do detalhamento ainda
  usa a última AnalysisRun global em vez da mesma fonte do popup — resíduo do
  A1) e **NEW-1** (analytics quebra com context_label misto em pandas>=3).
  B1, B4, A13 seguem abertos (baixa prioridade). Todas as três frentes de
  correção concluídas. Despachando N1+NEW-1 ao codex antes da segunda
  revisão.

## N1 + NEW-1 regression fix (2026-10-07)

- **N1**: added `get_latest_patient_analytics_run()` in `app/services/reports.py`, using the same patient-indicator join as the atypical-days endpoint. The detail card, patient report, and per-patient anomaly count now select the newest completed run that actually contains that patient's indicators, including global runs whose header has `patient_id=NULL`.
- **NEW-1**: `_prepare_glucose_frame()` now keeps mixed `context_label` values as Python `str | None`, and context range helpers only call `.startswith()` on strings. Removed the strict xfail so the integration regression runs as a normal test. Removed the expected-failure annotation from E2E N1.
- **Validation**: `python -m pytest tests/integration/test_idempotency_recompute_import.py::test_aut_ca_21_recompute_handles_manual_readings_with_and_without_context -q` — **1 passed**; `npm run test:e2e -- e2e/specs/09-atypical-popup-filters.spec.mjs --grep N1` launched the full group 9 spec — **9 passed** (including N1; A10 remains an expected failure); `python scripts/validate_investigations.py` — **PASS** on isolated SQLite, including global AnalysisRun lookup; `python -m compileall -q app/services/analytics.py app/services/reports.py tests/integration/test_idempotency_recompute_import.py` — **PASS**; `git diff --check` — **PASS**. The complete pytest suite was not rerun.
- **`git status --short`** (pre-existing frontend/e2e work remains visible; N1 test metadata was updated, and no UI source was changed):
  ```text
   M README.md
   M app/api/routes.py
   M app/core/config.py
   M app/main.py
   M app/models/__init__.py
   M app/models/entities.py
   M app/services/analytics.py
   M app/services/reports.py
   M app/services/uci_importer.py
   M docker-compose.yml
   M frontend-react/package-lock.json
   M frontend-react/package.json
   M frontend-react/src/App.jsx
   M frontend-react/src/api.js
   M frontend-react/src/components/AppShell.jsx
   M frontend-react/src/locales/en-US.json
   M frontend-react/src/locales/es.json
   M frontend-react/src/locales/pt-BR.json
   M frontend-react/src/pages/OverviewPage.jsx
   M frontend-react/src/pages/PatientDetailPage.jsx
   M frontend-react/src/styles.css
   M pyproject.toml
   M scripts/import_uci_diabetes.py
  ?? alembic/versions/20261006_0003_accounts_encryption.py
  ?? alembic/versions/20261006_0004_user_sessions.py
  ?? alembic/versions/20261006_0005_patient_doctor_links_notifications.py
  ?? alembic/versions/20261006_0006_investigations_prompts.py
  ?? alembic/versions/20261007_0007_glucose_notes_encrypted.py
  ?? app/core/CRYPTO_CONFIGURATION.md
  ?? app/core/crypto.py
  ?? app/core/rate_limit.py
  ?? app/core/security.py
  ?? app/services/auth_service.py
  ?? app/services/doctor_links.py
  ?? app/services/investigations.py
  ?? features/
  ?? frontend-react/e2e/
  ?? frontend-react/playwright.config.mjs
  ?? frontend-react/src/components/AtypicalDaysPopup.jsx
  ?? frontend-react/src/components/DoctorLinksManager.jsx
  ?? frontend-react/src/components/InvestigationsList.jsx
  ?? frontend-react/src/components/ManualGlucoseEntryForm.jsx
  ?? frontend-react/src/components/NotificationCenter.jsx
  ?? frontend-react/src/components/ProactivePrompt.jsx
  ?? frontend-react/src/contexts/
  ?? frontend-react/src/pages/InvestigationPage.jsx
  ?? frontend-react/src/pages/LandingPage.jsx
  ?? frontend-react/src/pages/LoginPage.jsx
  ?? frontend-react/src/pages/RegisterPage.jsx
  ?? scripts/validate_account_migration.py
  ?? scripts/validate_auth_flows.py
  ?? scripts/validate_doctor_links.py
  ?? scripts/validate_foundational_security.py
  ?? scripts/validate_investigations.py
  ?? scripts/validate_uci_demo_provisioning.py
  ?? tests/integration/
  ```

- 2026-10-07 09:14 (coordenador) — **N1 e NEW-1 corrigidos pelo codex**: N1
  (detalhamento/relatório agora usam a execução de análise mais recente que
  contém os indicadores do paciente, incluindo execuções globais — mesma
  lógica do A1); NEW-1 (context_label misto nulo/preenchido não quebra mais o
  recálculo com pandas≥3; teste de regressão deixou de ser xfail). Validado:
  validate_investigations.py, teste de integração do NEW-1, spec E2E de dias
  atípicos (9/9), compileall, git diff --check. Suíte pytest completa não
  rerodada (só os testes afetados). Todas as correções da rodada pós-revisão
  concluídas. Acionando segunda rodada de revisão com o revisor independente
  já retido.

- 2026-10-07 12:29 (coordenador) — **Revisão #2: REPROVADO, mas por apenas 1
  critério** (de 68!). 61 Aprovado, 4 Parcial, 2 N/A (decisão de papel
  único), **1 Reprovado: CSCW-CA-25 (R1)** — aplicar filtro de dias exatos
  apaga `start_date`/`end_date`, e "Limpar seleção" volta à janela padrão em
  vez de preservar os demais filtros. Confirmados corrigidos: A1, A2, A4-A9,
  A11, A14, B2, B5, B6, N1, NEW-1. R4 (pequeno): matriz desatualizada para
  CSCW-CA-23/AUT-CA-21. Recomendados (não bloqueantes): R2, R3, B1, B3, B4,
  B7, A15, O2 (risco de lockout por IP no rate-limit). Despachando R1+R4 ao
  worker de frontend retido antes da revisão #3 (deve ser rápida).

- 2026-10-07 (worker claude, R1FIX, continuação da task de frontend) —
  **R1 (CSCW-CA-25) corrigido e R4 atualizado.**
  - **R1**: com `dates=` ativo, `PatientDetailPage.jsx` mantém o
    `start_date`/`end_date` do usuário na URL, e o backend devolve
    `filters.start_date/end_date = null` nesse caso. O período anterior também
    fica guardado em `preservedRangeRef`, como reserva. A requisição de
    detalhe com dias exatos envia só `dates`, para o backend não cruzar os
    dias com o período. "Limpar seleção de dias" remove só `dates` e restaura
    o período preservado, ou a janela padrão se não havia período
    customizado.
  - **Teste real**: removido o `test.fail` de CSCW-CA-25 em
    `e2e/specs/09-atypical-popup-filters.spec.mjs`. Na primeira execução sem
    o `test.fail`, o teste falhou só pela expectativa: o backend já normaliza
    `end_date=2026-07-31` para `2026-07-10` (fim dos dados) no primeiro
    carregamento, antes de qualquer `dates=`. O teste passou a comparar com o
    período ativo antes de aplicar os dias, e também confere o campo de data.
    Resultado de `npx playwright test e2e/specs/09-atypical-popup-filters.spec.mjs`:
    **9 passed** (2,5 min), sem `test.fail`. `npm run build` OK.
  - **R4**: `MATRIZ-ACEITE.md` atualizada:
    - CSCW-CA-23 → Aprovado (N1 corrigido);
    - AUT-CA-21 sem a menção ao xfail (NEW-1 corrigido);
    - CSCW-CA-25 → Aprovado;
    - cabeçalho e totais: **62 Aprovado · 0 Reprovado · 4 Parcial · 2 Não
      aplicável** (68, recontado pela coluna Status).
    A suíte E2E completa não foi reexecutada; só o grupo 09.

- 2026-10-07 09:38 (coordenador) — **R1 e R4 concluídos** (confirmado por
  leitura direta do terminal, canal de worker_done falhou por bookkeeping —
  dispatch não era formal). R1: ao aplicar `dates=`, o período ativo
  (`start_date`/`end_date` já ajustado pelo backend ao último dia com dados)
  é preservado à parte; "Limpar seleção de dias" restaura esse período em vez
  de resetar para a janela padrão. Também corrigido um erro na própria
  expectativa do teste (comparava com valor digitado na URL, não com o
  período ativo real). `npx playwright test` do spec 09: **9/9 passando**.
  R4: MATRIZ-ACEITE.md atualizada — CSCW-CA-23 e CSCW-CA-25 → Aprovado,
  AUT-CA-21 sem menção a xfail. **Totais finais: 62 Aprovado, 0 Reprovado, 4
  Parcial, 2 Não aplicável (68 critérios).** Acionando revisão #3 (final)
  com o revisor independente retido.

- 2026-10-07 12:54 (coordenador) — **Revisão #3: REPROVADO por 2 achados
  novos de UX (N2, N3)**, mas R1 e R4 confirmados de verdade (suíte completa
  reexecutada pelo revisor: 74 passed/1 skip/0 falhas; matriz confere 62/0/4/2;
  checagem manual no navegador). **N2** (CSCW-CA-23): popup de dias atípicos
  não recebe o período ativo do detalhamento — mostra todos os 7 dias do
  histórico mesmo quando o card mostra só 1 (período padrão), sem explicar o
  escopo (AtypicalDaysPopup.jsx:22-35). **N3**: selecionar um dia fora do
  período deixa o resumo em "- - -"/janela padrão sem avisar que houve
  ajuste. Despachando ao worker de frontend retido.

- 2026-10-07 (worker claude, N2N3FIX, achados da revisão #3) —
  **N2 e N3 corrigidos no frontend.**
  - **N2** (`AtypicalDaysPopup.jsx`, `PatientDetailPage.jsx`):
    - o popup recebe o período ativo do detalhamento (`activeStart`/`activeEnd`)
      e abre com ele como filtro, o mesmo escopo do card;
    - uma linha de escopo diz a contagem e se a lista é do período exibido, de
      um período escolhido no popup ou de todo o histórico;
    - os botões "Ver todo o histórico" e "Usar o período exibido" alternam o
      escopo.
  - **N3**:
    - aplicar dias fora do período ativo amplia `start_date`/`end_date` só o
      necessário para cobrir a seleção e mostra o aviso "Período ajustado para
      incluir o(s) dia(s) selecionado(s) …: de X – Y para X' – Y'";
    - o período original fica preservado, e "Limpar seleção de dias" o
      restaura e remove o aviso;
    - com `dates` ativo, o resumo do topo mostra "Dias selecionados (N)" e o
      período de referência, em vez de "- -" e "Janela padrão";
    - mudar o período com dias ativos recalcula a cobertura.
  - 9 chaves novas de i18n nos 3 locales.
  - **E2E**: novo cenário "CSCW-CA-23/25 (N2, N3)" em
    `e2e/specs/09-atypical-popup-filters.spec.mjs`. O período ativo vai até a
    véspera do último dia atípico semeado, portanto é menor que o histórico.
    O cenário verifica:
    - contagem do popup = card < total;
    - texto de escopo;
    - "Ver todo o histórico" mostra o total;
    - selecionar o dia de fora amplia `end_date`, com aviso e resumo corretos;
    - limpar restaura o `end_date` original.
    Primeira execução: 1 falha no próprio teste (o popup ordena os dias de
    forma decrescente, então o localizador pegou o dia errado), corrigida
    localizando a linha pela data. Resultado final de
    `npx playwright test e2e/specs/09-atypical-popup-filters.spec.mjs`:
    **10 passed** (2,6 min). `npm run build` OK.
  - **MATRIZ-ACEITE.md**: CSCW-CA-23 e CSCW-CA-25 continuam Aprovado, com a
    evidência atualizada (spec 09 10/10). Os totais não mudam: 62 · 0 · 4 · 2.

- 2026-10-07 10:04 (coordenador) — **N2/N3 concluídos** (confirmado por
  leitura direta do terminal): popup agora respeita o período ativo do
  detalhamento, mostra texto de escopo, oferece "Ver todo o histórico", e
  avisa quando o período é ajustado para incluir um dia selecionado fora da
  janela — com volta ao período original ao limpar. Teste novo
  "CSCW-CA-23/25 (N2, N3)" cobrindo tudo isso: grupo 09 agora 10/10. Matriz
  mantém 62 Aprovado / 0 Reprovado / 4 Parcial / 2 N/A, evidência atualizada.
  9 strings novas nos 3 idiomas. Acionando revisão #4 (espera-se final) com
  o revisor independente retido.

## ENTREGA FINAL

- 2026-10-07 13:21 (coordenador) — **VEREDITO FINAL: APROVADO (revisão #4)**.
  Jornada completa: revisão #1 REPROVADO (16 achados A1-A16 + B1-B10) →
  rodada de correção (codex backend + 2 workers claude frontend/E2E, só
  claude/codex por decisão do produto) → revisão #2 REPROVADO (1 critério,
  R1) → correção R1/R4 → revisão #3 REPROVADO (2 achados novos, N2/N3) →
  correção N2/N3 → **revisão #4 APROVADO**.
  Estado final verificado pelo revisor independente: suíte E2E 75/76
  cenários passando (1 skip documentado), pytest 52 passed/1 skip, matriz de
  aceite 62 Aprovado / 0 Reprovado / 4 Parcial / 2 Não aplicável (68
  critérios). Pendências não bloqueantes documentadas em REVISAO-FINAL.md
  para backlog futuro (AUT-CA-21, CSCW-CA-22/26/29 parciais; A15, B1, B3,
  B4, B7, R2, R3, O2-O5 recomendados).
  Decisões de produto registradas: UserAccount com papel único (patient OU
  doctor, nunca ambos); credenciais demo públicas (patientN@email.com /
  qwerty) documentadas como exceção deliberada do dataset público UCI.
