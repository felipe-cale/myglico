# Auditoria integral final do MyGlico

**Data/hora:** 2026-10-09 21:41:07 -03:00 (2026-10-10 00:41:07 UTC)  
**Auditor:** revisão independente do código final em `0920365`, commit `6a70133` e diff não commitado do worktree.  
**Veredito:** **APROVADO**, consideradas as divergências aceitas pelo dono do produto registradas abaixo.

## 1. Objeto e execuções

A revisão abrangeu a árvore final inteira em relação a `0920365`, não só o último lote. Li o README, `AGENTS.md`, `PROMPT-ORCA.md`, os dois SDDs completos, `MATRIZ-ACEITE.md`, `CONTRATOS-API.md` e as decisões pertinentes do `BACKLOG.md`. Não consultei os pareceres anteriores vetados pelo escopo. Não alterei código, testes, migrações, configuração ou documentos existentes. O único arquivo criado nesta auditoria é este parecer.

`git diff 0920365 --stat`:

```text
97 files changed, 17890 insertions(+), 337 deletions(-)
```

SHA-256 de `git diff 0920365 -- . ':(exclude)features/a-desenvolver/AUDITORIA-INTEGRAL-FINAL.md'` (1.111.526 bytes):

```text
1c22f26814521ca03ce9a643f2bc3820c387151487253da41eed21162fc1298b
```

Arquivos não rastreados observados antes da criação deste relatório:

```text
alembic/versions/20261007_0008_notification_delivery_and_system_closer.py
alembic/versions/20261008_0009_patient_timezone_privacy_acceptance.py
alembic/versions/20261008_0010_patient_identity_not_null.py
alembic/versions/20261008_0011_normalize_measurement_timestamps_to_utc.py
app/core/patient_time.py
app/services/cscw_provenance.py
app/services/notification_outbox.py
features/a-desenvolver/AUDITORIA-FINAL-ESCOPO.md
features/a-desenvolver/AUDITORIA-INTEGRAL-ESCOPO.md
features/a-desenvolver/AUDITORIA-INTEGRAL.md
features/a-desenvolver/O8-DEBATE.md
features/a-desenvolver/O8-ESCOPO-PARECER.md
features/a-desenvolver/O8-PARECER-CODEX.md
features/a-desenvolver/O8-PROPOSTA.md
features/a-desenvolver/REVISAO7-ESCOPO.md
frontend-react/src/components/InvestigationOrigin.jsx
scripts/export_cscw_provenance.py
scripts/notification_outbox.py
tests/integration/test_cscw_prov_projection.py
tests/integration/test_lote2_patient_time_provenance_registration.py
tests/integration/test_lote3_fixes.py
tests/integration/test_lote4_timezone_and_provenance.py
```

O relatório em si também passa a ser não rastreado; foi criado depois dessa captura e fica excluído do diff/hash conforme solicitado.

### Comandos e resultados

- `python -m pytest tests -q -rxXs` — **74 passed**, 1 warning de detecção de núcleos físicos pelo `joblib` no Windows.
- Os seis `scripts/validate_*.py`, com `MYGLICO_ENCRYPTION_KEY_V1` e `MYGLICO_LOOKUP_HMAC_KEY` aleatórios de 32 bytes gerados somente no processo — **6/6 passaram**. Os scripts usaram SQLite descartável; nenhuma chave foi impressa ou persistida.
- `cd frontend-react; MYGLICO_E2E_BACKEND_PORT=8271 MYGLICO_E2E_FRONTEND_PORT=8270 npx playwright test` — **79 passed, 1 skipped**, 8,6 min. Execução final fora do sandbox após a primeira tentativa ser impedida pelo Vite de ler o diretório de configuração no sandbox. O caso ignorado é só a falha forçada de publicação do outbox no navegador; a simulação correspondente passou em `tests/integration/test_outbox_and_delivery.py::test_cscw_ca_29_failed_publication_is_retried_from_a_durable_row_without_duplicate_effects`.
- Sonda temporária própria, executada sobre SQLite migrado em `%TEMP%`: paciente A→paciente B, médico sem vínculo→paciente B e paciente A→PDF de B deram 404; cifra AES-GCM decifrou no contexto correto, recusou AAD de outro registro e ciphertext adulterado; inspeção SQLite não encontrou nome/e-mail em colunas plaintext; conversão de 23:59 America/Sao_Paulo para UTC e leitura de volta preservou a data/hora. **PASS**. O script e o banco temporário foram removidos.
- `python -m alembic heads` — único head `20261008_0011`; `git diff --check 0920365` — apenas avisos de trailing whitespace em quebras Markdown dos SDDs adicionados; não encontrei whitespace problemático em código executável.
- Checagem automática de catálogos frontend — `pt-BR`, `en-US`, `es`: mesmas 15 chaves-raiz; fluxos de interface e PDF nos três idiomas também passaram no Playwright.

Não acessei `data/myglico.db`, não usei as portas proibidas, não instalei ferramentas e não iniciei serviços fora das portas E2E determinadas.

## 2. Requisitos textuais dos SDDs, seção por seção

Nesta tabela, “Atende” considera inspeção do código final junto às execuções listadas. Desvios aceitos são identificados explicitamente e detalhados na seção 3.

| SDD/seção | Requisitos textuais avaliados | Status | Evidência independente |
|---|---|---|---|
| SDD1 §1 | Ler a arquitetura existente, manter entidades e identidade; landing pública sem dados clínicos, login/cadastro e papéis | Atende | `frontend-react/e2e/specs/01-public-landing.spec.mjs`; `02-auth-registration-session.spec.mjs` |
| SDD1 §2 | Contas de demonstração UCI preservam origem; não insinuar contato às pessoas do dataset | Atende | `scripts/validate_uci_demo_provisioning.py`; `tests/integration/test_idempotency_recompute_import.py` |
| SDD1 §3.1 | Funcionalidades incluídas: conta, sessão, busca, proteção, vínculos, importador e fronteiras | Atende com divergências aceitas | Execuções dos 6 validadores e 79 E2E; papel duplo é a exceção aceita em §3.1/§4 RF-06 |
| SDD1 §3.2 | Sem entidade de pesquisa/perfis novos, sem verificação CFM inventada, sem novo algoritmo; não tomar conta por e-mail não verificado | Atende | `app/models/entities.py`; E2E-02, E2E-03; `scripts/validate_auth_flows.py` |
| SDD1 §4 RF-01..17 | Requisitos funcionais da tabela, inclusive criação transacional, busca restrita, sessão e importação idempotente | Atende com divergência aceita em RF-06 | E2E-01..05; `tests/integration/test_atomicity_rollback.py`; `test_idempotency_recompute_import.py`; `scripts/validate_uci_demo_provisioning.py` |
| SDD1 §5.1 | Conta mantém credenciais protegidas, hash autocontido, status e metadados, sem duplicar dados de domínio | Atende | `app/core/crypto.py`; `app/models/entities.py`; `tests/integration/test_crypto_and_secrets.py` |
| SDD1 §5.2 | Patient preserva IDs, origem e relação com leituras; identidade protegida e conta UCI provisionada | Atende | `scripts/validate_account_migration.py`; `scripts/validate_uci_demo_provisioning.py`; sondagem SQLite |
| SDD1 §5.3 | Doctor tem SHORTID, identidade/CRM/UF protegidos, busca cega, perfil declarado distinto de verificado | Atende | `scripts/validate_foundational_security.py`; `scripts/validate_auth_flows.py`; E2E-03 |
| SDD1 §5.4 | Cardinalidades, IDs, unicidade, associações e preservação de entidades clínicas | Divergência aceita apenas para papel único; restante atende | BACKLOG decisão de papel único; `app/models/entities.py`; migrations 0003–0011; validação de migração |
| SDD1 §6.1 | SELECT/cópia do banco sem chaves não expõe PII; metadados legíveis não são chamados de anonimização; proteção no campo | Atende | Sonda própria SQLite; `tests/integration/test_crypto_and_secrets.py`; `app/core/crypto.py` |
| SDD1 §6.2 | AES-GCM, nonce, AAD por campo/linha, chaves fora do banco/log/código, rotação versionada e leitura autorizada | Atende | Sonda própria de AAD/adulteração; `tests/integration/test_crypto_and_secrets.py`; `app/core/CRYPTO_CONFIGURATION.md` |
| SDD1 §6.3 | Senhas somente com hash adaptativo e salt independente; sem segredo em log/resposta | Atende | `app/core/crypto.py`; `tests/integration/test_crypto_and_secrets.py`; E2E-02 |
| SDD1 §6.4 | HMAC cego, normalização coerente, unicidade, busca exata e limitação | Atende | `app/core/crypto.py`; `app/core/rate_limit.py`; validadores de segurança e busca |
| SDD1 §6.5 | Compatibilidade do algoritmo e das leituras sem réplica permanente plaintext | Atende | `tests/integration/test_idempotency_recompute_import.py`; `test_crypto_and_secrets.py`; execução do importador demo |
| SDD1 §7 | SHORTID CSPRNG de 6 caracteres, restrição UNIQUE e retry, sem tratar como segredo | Atende | `scripts/validate_foundational_security.py`; `app/core/crypto.py` |
| SDD1 §8.1 | Landing explicativa sem pacientes/endpoints clínicos; sem credenciais demo nela | Atende na interface; credenciais documentadas externamente são divergência aceita | E2E-01 e E2E-10; README e decisão no BACKLOG |
| SDD1 §8.2 | Cadastro seleciona papel, exige aviso, campos específicos e transação sem apropriação de IDs | Atende | E2E-02; `tests/integration/test_atomicity_rollback.py` |
| SDD1 §8.3 | Login, logout, cookies seguros, sessão revogável, erros genéricos e limitação | Atende | E2E-02 (sessão, logout, rate limit); `scripts/validate_auth_flows.py` |
| SDD1 §8.4 | Área privada filtra dados conforme identidade e vínculo; navegação protegida | Atende, com divergência aceita para alternância de contexto dual-role | E2E-03..10; `tests/integration/test_authorization_boundaries.py` |
| SDD1 §9 | Busca/vínculo não concede acesso antes de aceitar; autorização por objeto e papel | Atende | E2E-03..05; `scripts/validate_doctor_links.py` |
| SDD1 §10.1–10.2 | Importação explícita, idempotente, sem redefinir IDs/SHORTIDs/credenciais ou reativar revogação | Atende | `scripts/validate_uci_demo_provisioning.py`; `tests/integration/test_idempotency_recompute_import.py` |
| SDD1 §11 | Migrações preservam referências e declaram DDL; evolução aceita para produção recriada do zero | Divergência aceita quanto a bancos persistentes antigos; cadeia do zero atende | `scripts/validate_account_migration.py`; `alembic heads`; cadeia 0001–0011; BACKLOG decisão de recriar produção |
| SDD1 §12 | Contratos conceituais adaptados sem perder comportamentos obrigatórios | Atende | `CONTRATOS-API.md`; E2E-01..10; testes de integração |
| SDD1 §13–14 | Plano de execução e validação dos fluxos principais | Atende | `python -m pytest tests -q -rxXs`; seis validadores; Playwright completo |
| SDD1 §15 | Definição de pronto aplicada | Atende | Resultado consolidado desta auditoria |
| SDD1 §16 | Referências técnicas, informativas | Não aplicável como requisito de produto | Bibliografia não define comportamento executável |
| SDD2 §1 | Preservar arquitetura, ontologia, autenticação, proveniência e algoritmo; nove regras obrigatórias | Atende | E2E-01..10; `tests/integration/test_cscw_prov_projection.py`; revisão de `app/services/cscw_provenance.py` |
| SDD2 §2, §2.1 | Colaboração 3Cs, busca, ciclo de vínculo, mensagens, convite, notificações, filtros e auditoria | Atende | E2E-03..10; validadores `doctor_links` e `investigations` |
| SDD2 §2.2 | Não compartilhar com vários médicos, reabrir, editar/remover, canais externos ou publicar grafo clínico | Atende | Revisão de `routes.py`, `investigations.py`, `cscw_provenance.py`; E2E-05/06; `test_cscw_prov_projection.py` |
| SDD2 §3 | Servidor resolve identidade; associação N:N; conversa por médico; revogação corta acesso; proveniência atômica | Atende com divergência aceita para conta de papel único | E2E-03..06; `test_authorization_boundaries.py`; `test_atomicity_rollback.py` |
| SDD2 §4.1–4.3 | Busca exata, perfil mínimo, estados acessíveis, solicitação explícita e rate limit | Atende | E2E-03; `scripts/validate_doctor_links.py`; `app/core/rate_limit.py` |
| SDD2 §5.1–5.3 | Estados/transições, autoria e revogação unilateral imediata | Atende | E2E-03/04; `scripts/validate_doctor_links.py`; `test_concurrency.py` |
| SDD2 §5.4 | Ao revogar, fecha investigações daquele ciclo com sistema como autor, preserva história e corta acesso médico | Atende | E2E-04; `tests/integration/test_authorization_boundaries.py`; provenance events |
| SDD2 §5.5 | Vínculo UCI é de software, sem aceite humano fictício; reimportação não reativa revogado | Atende | `scripts/validate_uci_demo_provisioning.py`; `test_idempotency_recompute_import.py` |
| SDD2 §6.1–6.2 | Investigação opcionalmente ligada a evento real; título/mensagem protegidos, ordem, autoria e idempotência | Atende | E2E-05/06; `scripts/validate_investigations.py`; testes crypto e idempotência |
| SDD2 §6.3 | Marcador de leitura por sequência persistida, sem marcar listagem como lida | Atende | E2E-08; `tests/integration/test_outbox_and_delivery.py` |
| SDD2 §7.1–7.6 | Aberturas com/sem evento, vínculo e origem verdadeiros, preservação histórica após recálculo | Atende | E2E-05..07; `scripts/validate_investigations.py`; `test_idempotency_recompute_import.py` |
| SDD2 §8.1–8.3 | Estado aberto/fechado, resposta, autoria, cooperação e limites de escopo | Atende | E2E-06; `tests/integration/test_concurrency.py` |
| SDD2 §9.1–9.4 | Popup conta/lista coerente, seleção de datas exatas, filtros, estados vazios e acessibilidade | Atende | E2E-09; `frontend-react/e2e/specs/09-atypical-popup-filters.spec.mjs` |
| SDD2 §10.1–10.6 | Eventos transacionais, tipos obrigatórios, projeção PROV-O pseudonimizada e exportação restrita | Atende | `tests/integration/test_provenance_events.py`; `test_cscw_prov_projection.py`; revisão de `scripts/export_cscw_provenance.py` |
| SDD2 §11.1–11.5 | Inbox e contadores separados; leitura real; persistência/retry e autorização após revogação | Atende | E2E-08 (retry coberto no backend); `tests/integration/test_outbox_and_delivery.py` |
| SDD2 §12 | Concorrência, repetição, segurança e erros sem vazamento | Atende | `tests/integration/test_concurrency.py`; `test_atomicity_rollback.py`; E2E-02/06 |
| SDD2 §13 | Contratos conceituais coerentes com os endpoints e estados | Atende | `features/a-desenvolver/CONTRATOS-API.md`; E2E-01..10 |
| SDD2 §14 | Plano de execução e validação | Atende | Seis validadores; pytest integral; Playwright integral |
| SDD2 §15 | Critérios de aceite aplicados | Atende com CSCW-CA-33 N/A por decisão aceita | Tabela de critérios abaixo; testes correspondentes |
| SDD2 §16 | Definição de pronto aplicada | Atende | Resultado consolidado desta auditoria |
| SDD2 §17–18 | Histórico e referências, informativos | Não aplicável como comportamento executável | Conteúdo documental, sem regra funcional adicional |

## 3. Critérios de aceite (68)

### SDD1 — AUT-CA-01..23

| Critério | Status | Evidência executada |
|---|---|---|
| AUT-CA-01 | Atende | E2E `01-public-landing`: visitante vê explicação, Entrar/Criar conta e nenhum dado clínico |
| AUT-CA-02 | Atende | E2E `01-public-landing`: API, JSON e PDF legados recusam acesso anônimo |
| AUT-CA-03 | Atende | E2E `02-auth-registration-session`: conta Patient e SHORTID válido |
| AUT-CA-04 | Atende | E2E `02-auth-registration-session`: conta Doctor; E2E i18n confirma formulários |
| AUT-CA-05 | Atende | `tests/integration/test_atomicity_rollback.py`; falha de entidade não deixa conta órfã |
| AUT-CA-06 | Atende | E2E `02-auth-registration-session`: cadastro/login sem confirmação de e-mail |
| AUT-CA-07 | Atende | `tests/integration/test_crypto_and_secrets.py`; sonda própria consultou SQLite migrado |
| AUT-CA-08 | Atende | E2E `02-auth-registration-session`; hashes/salts independentes; `test_crypto_and_secrets.py` |
| AUT-CA-09 | Atende | E2E `02-auth-registration-session`: duplicidade rejeitada com erro genérico |
| AUT-CA-10 | Atende | E2E `03-search-and-link-lifecycle`: busca exata SHORTID e CRM+UF |
| AUT-CA-11 | Atende | E2E `02-auth-registration-session`; `test_authorization_boundaries.py` |
| AUT-CA-12 | Atende | E2E `05-investigation-opening` e `10-i18n-and-pdf`; sonda própria retornou 404 em API/PDF |
| AUT-CA-13 | Atende | E2E `05-investigation-opening`; sonda própria médico sem vínculo→404 |
| AUT-CA-14 | Atende | E2E `04-revocation`: sessão aberta perde acesso após revogação |
| AUT-CA-15 | Atende | E2E `05-investigation-opening`/`06-messaging-and-closure`: dois médicos isolados |
| AUT-CA-16 | Atende | `scripts/validate_uci_demo_provisioning.py`: cada paciente provisionado e vínculo ativo de demonstração |
| AUT-CA-17 | Atende | `scripts/validate_uci_demo_provisioning.py`; importações repetidas preservam contagens e credenciais |
| AUT-CA-18 | Atende | `scripts/validate_foundational_security.py`: colisão SHORTID gera nova tentativa |
| AUT-CA-19 | Divergência aceita | BACKLOG decisão de produto: conta tem papel único; `02-auth-registration-session` confirma segundo papel recusado |
| AUT-CA-20 | Atende | E2E `02-auth-registration-session`: logout, troca de conta e voltar do browser sem dados anteriores |
| AUT-CA-21 | Atende | `tests/integration/test_idempotency_recompute_import.py`; baseline clínico e reprocessamento preservados |
| AUT-CA-22 | Atende | `tests/integration/test_crypto_and_secrets.py`; sonda própria confirmou AAD/tamper falharem |
| AUT-CA-23 | Atende | E2E `01-public-landing`/`10-i18n-and-pdf`: bundle, respostas públicas e landing sem segredos/PII clínica |

### SDD2 — CSCW-CA-01..45

| Critério | Status | Evidência executada |
|---|---|---|
| CSCW-CA-01 | Atende | E2E `03-search-and-link-lifecycle`: busca exata e perfil mínimo |
| CSCW-CA-02 | Atende | E2E `03-search-and-link-lifecycle`: pedido PENDING, evento/notificação e sem acesso clínico |
| CSCW-CA-03 | Atende | E2E `03-search-and-link-lifecycle`: médico distinto não confirma |
| CSCW-CA-04 | Atende | E2E `03-search-and-link-lifecycle`: confirmação pelo destinatário, estado e versão |
| CSCW-CA-05 | Atende | E2E `03-search-and-link-lifecycle`: rejeição/cancelamento e novo pedido coerentes |
| CSCW-CA-06 | Atende | E2E `04-revocation`: Patient revoga sem aprovação do médico |
| CSCW-CA-07 | Atende | E2E `04-revocation`: Doctor revoga sem aprovação do paciente |
| CSCW-CA-08 | Atende | E2E `04-revocation`: sessão e notificações não restauram acesso |
| CSCW-CA-09 | Atende | E2E `04-revocation`: fechamento administrativo e histórico do Patient |
| CSCW-CA-10 | Atende | E2E `04-revocation`: nova associação não restaura conversas |
| CSCW-CA-11 | Atende | `scripts/validate_uci_demo_provisioning.py`; reimportação não duplica/reativa vínculo |
| CSCW-CA-12 | Atende | `scripts/validate_uci_demo_provisioning.py`; agente software e sem aceite humano simulado |
| CSCW-CA-13 | Atende | E2E `05-investigation-opening`: convite com origem real e primeira mensagem atômica |
| CSCW-CA-14 | Atende | E2E `05-investigation-opening`: abertura sem evento, sem evento artificial |
| CSCW-CA-15 | Atende | E2E `05-investigation-opening`: Doctor abre apenas com próprio contexto e vínculo ativo |
| CSCW-CA-16 | Atende | E2E `05-investigation-opening`: evento de outro paciente é negado sem vazamento |
| CSCW-CA-17 | Atende | E2E `05-investigation-opening`: destinatário explícito e isolamento entre médicos |
| CSCW-CA-18 | Atende | E2E `06-messaging-and-closure`: autoria do servidor, ordem e texto protegido |
| CSCW-CA-19 | Atende | E2E `08-notifications-and-unread`: marcador monotônico, leitura repetida sem regressão |
| CSCW-CA-20 | Atende | E2E `06-messaging-and-closure`: qualquer participante encerra com autoria correta |
| CSCW-CA-21 | Atende | E2E `06-messaging-and-closure`: enviar após CLOSED negado, histórico preservado |
| CSCW-CA-22 | Atende | E2E `06-messaging-and-closure`: origem preservada e indicada após recálculo |
| CSCW-CA-23 | Atende | E2E `09-atypical-popup-filters`: popup lista dias correspondentes à contagem/escopo |
| CSCW-CA-24 | Atende | E2E `09-atypical-popup-filters`: seleção não consecutiva filtra somente as datas marcadas |
| CSCW-CA-25 | Atende | E2E `09-atypical-popup-filters`: composição/limpeza mantém os outros filtros |
| CSCW-CA-26 | Atende | E2E `09-atypical-popup-filters`: formulário atravessa meia-noite no fuso local; sonda UTC/local |
| CSCW-CA-27 | Atende | E2E `09-atypical-popup-filters`: vazio/loading/erro acessíveis sem inventar resultados |
| CSCW-CA-28 | Atende | `tests/integration/test_atomicity_rollback.py`: falha de proveniência reverte mutação |
| CSCW-CA-29 | Atende | `tests/integration/test_outbox_and_delivery.py::test_cscw_ca_29_failed_publication_is_retried_from_a_durable_row_without_duplicate_effects` passou; caso de navegador ignorado por limitação de observabilidade |
| CSCW-CA-30 | Atende | E2E `06-messaging-and-closure`; `tests/integration/test_concurrency.py` |
| CSCW-CA-31 | Atende | `tests/integration/test_crypto_and_secrets.py`; inspeção direta SQLite temporário; logs sem conteúdo |
| CSCW-CA-32 | Atende | E2E `04-revocation`: endpoint de proveniência não contorna autorização |
| CSCW-CA-33 | Divergência aceita | BACKLOG decisão de papel único; E2E `06-messaging-and-closure` confirma autoria derivada do papel único |
| CSCW-CA-34 | Atende | `tests/integration/test_idempotency_recompute_import.py`; repetição de pedido/confirmação/mensagem |
| CSCW-CA-35 | Atende | E2E `01-public-landing` e `10-i18n-and-pdf`: landing informativa, 3 idiomas, sem lista pública |
| CSCW-CA-36 | Atende | E2E `07-atypical-day-invitation`: convite/notificação persistem sem abrir conversa |
| CSCW-CA-37 | Atende | E2E `07-atypical-day-invitation`: Agora não persiste, não reaparece e abertura manual funciona |
| CSCW-CA-38 | Atende | E2E `07-atypical-day-invitation`: escolhe explicitamente médico e notifica só o destinatário |
| CSCW-CA-39 | Atende | E2E `08-notifications-and-unread`: mensagem do médico aparece após login novo |
| CSCW-CA-40 | Atende | E2E `08-notifications-and-unread`: contagem simétrica para mensagem Patient→Doctor |
| CSCW-CA-41 | Atende | E2E `08-notifications-and-unread`: abrir listagem/ler aviso não zera mensagens |
| CSCW-CA-42 | Atende | E2E `08-notifications-and-unread`: mensagens não apresentadas permanecem não lidas |
| CSCW-CA-43 | Atende | E2E `08-notifications-and-unread`; `test_outbox_and_delivery.py`: avanço efetivo único |
| CSCW-CA-44 | Atende | E2E `08-notifications-and-unread`: canal indisponível recupera avisos e contadores persistidos |
| CSCW-CA-45 | Atende | E2E `07-atypical-day-invitation`; `test_idempotency_recompute_import.py`: convites históricos consolidados/deduplicados |

## 4. Achados e divergências

### Defeitos e omissões

Não encontrei defeito P1/P2 nem omissão obrigatória após inspeção e execução. Os 74 testes Python, os seis validadores, os fluxos E2E e a sonda temporária passaram nos comportamentos críticos avaliados.

O único caso Playwright ignorado (CSCW-CA-29) é uma limitação da camada de navegador: injetar falha no consumidor Python requer monkeypatch do serviço. O mesmo comportamento foi executado no teste de integração indicado na tabela e passou. Portanto, não há requisito obrigatório pendente por esse skip.

### Divergências aceitas por decisão do dono do produto

| Requisito/trecho | Gravidade | Decisão e aplicação observada |
|---|---|---|
| SDD1 §3.1, §4 RF-06, §5.4 e §7; AUT-CA-19; SDD2 §3 e CSCW-CA-33 | Divergência aceita | BACKLOG decide conta com papel único. Cadastro rejeita segundo papel, autoria/permissões vêm do papel associado à conta; IDs de Patient/Doctor continuam próprios. Os dois CAs estão corretamente como não aplicáveis, não como defeito. |
| SDD1 §8.1: não publicar credenciais demo | Divergência aceita | BACKLOG autoriza credenciais demo públicas exclusivamente para o dataset UCI e README documenta `patientN@demo.myglico.invalid`/`doctor@demo.myglico.invalid` com senha demo. A landing, bundles e respostas públicas não as expõem. A exceção está restrita ao fluxo de demonstração. |
| SDD1 §11: preservar bancos/revisões existentes | Divergência aceita | BACKLOG registra que produção será recriada do zero e autoriza reescrever a cadeia 0001–0011. O DDL é explícito; upgrade limpo até 0011 passou nos validadores. Não há banco persistente a preservar nesta decisão. |
| SDD2 §10.4 e §11.4 / O8: dispatcher de inbox | Divergência aceita | BACKLOG escolhe versão enxuta: notificação e contador são gravados atomicamente; outbox registra estado/retry; API não drena filas; loop é configurável e fica desligado no Vercel. A entrega local é a própria inbox persistida, portanto não há canal externo perdido. Testes de retry e ausência de efeitos duplicados passaram. |

A limitação de rate limit em memória por worker é documentada no README. É uma limitação externa/operacional já explicitada, não uma divergência funcional silenciosa nem falha no comportamento de um worker.

### Inspeção transversal do diff

- Não identifiquei segredo real, chave de cifra ou credencial além das credenciais demo explicitamente aceitas e documentadas.
- Os catálogos `pt-BR`, `en-US` e `es` mantêm as mesmas chaves; navegação e relatórios clínicos foram exercitados nos três idiomas.
- A cadeia Alembic termina num único head `20261008_0011`; os validadores migraram bases SQLite descartáveis até o head. Não foram encontrados `Model.__table__.create()` nem `Base.metadata.create_all()` nas migrações.
- Mudanças de ontologia/mapeamento preservam o núcleo clínico. `RawImportRecord` permanece ligado às medições por `GlucoseRecordSource`, e as medições continuam ligadas a `Patient`; as novas associações CSCW/proveniência não substituem essa cadeia.
- Exportação CSCW é por comando de operador, sem endpoint HTTP público; teste de projeção valida pseudônimos e ausência de conteúdo sensível como literais.
- Não encontrei alterações acidentais além dos arquivos descritos no objeto e dos artefatos temporários descartáveis de teste.

## 5. Veredito

**APROVADO.** Os 68 critérios têm evidência de execução ou inspeção correspondente. AUT-CA-19 e CSCW-CA-33 são não aplicáveis por decisão registrada de papel único. Os desvios de credenciais demo, estratégia O8 enxuta e recriação da produção foram aceitos pelo dono do produto e aplicados de forma coerente. Não restou pendência obrigatória rebaixada a observação.

AUDITORIA_FINAL_CONCLUIDA veredito=APROVADO