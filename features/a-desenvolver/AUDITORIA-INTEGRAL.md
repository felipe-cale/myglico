# Auditoria integral final — MyGlico

## 1. Identificação do objeto e execuções

**Auditor:** sessão independente, sem autoria de código desta branch nem participação nas revisões anteriores. **Data/hora do parecer:** 2026-10-09 20:31 UTC. **Objeto:** árvore resultante da base `0920365`, commit `6a701335718ec19464acfaff9770400e389bed98` e diff do worktree ainda não commitado. A revisão cobriu o diff completo, SDD1 e SDD2 integrais, `AGENTS.md`, `README.md`, `PROMPT-ORCA.md` e documentos de contexto indicados no escopo. As decisões em relatórios anteriores foram tratadas como pistas, não como prova.

```text
git diff 0920365 --stat
93 files changed, 17003 insertions(+), 310 deletions(-)

SHA-256 de git diff 0920365 -- . ':(exclude)features/a-desenvolver/AUDITORIA-INTEGRAL.md'
57174967bb34dfa1ef9e2dbe81e5a6d68e1e373a603d5d3d8e27e35c727d2947
```

Arquivos não rastreados observados antes da criação deste parecer:

```text
alembic/versions/20261007_0008_notification_delivery_and_system_closer.py
alembic/versions/20261008_0009_patient_timezone_privacy_acceptance.py
alembic/versions/20261008_0010_patient_identity_not_null.py
alembic/versions/20261008_0011_normalize_measurement_timestamps_to_utc.py
app/core/patient_time.py
app/services/notification_outbox.py
debug.log
features/a-desenvolver/AUDITORIA-INTEGRAL-ESCOPO.md
features/a-desenvolver/AUDITORIA-INTEGRAL.md
features/a-desenvolver/O8-DEBATE.md
features/a-desenvolver/O8-ESCOPO-PARECER.md
features/a-desenvolver/O8-PARECER-CODEX.md
features/a-desenvolver/O8-PROPOSTA.md
features/a-desenvolver/REVISAO7-ESCOPO.md
frontend-react/src/components/InvestigationOrigin.jsx
scripts/notification_outbox.py
tests/integration/test_lote2_patient_time_provenance_registration.py
tests/integration/test_lote3_fixes.py
tests/integration/test_lote4_timezone_and_provenance.py
```

`debug.log` contém apenas duas mensagens de erro do Crashpad (`CreateFile: Acesso negado`), sem credenciais ou texto clínico. É um artefato alheio ao produto. O `git diff --check 0920365` retornou código diferente de zero por whitespace final em documentos/JSX novos e linha vazia final em arquivos; não encontrei segredo literal no diff. O diff deixa ontologia e mapeamento R2RML sem alterações; a cadeia de importação de `RawImportRecord`/`GlucoseRecordSource` e referências a `Patient` permanece no modelo/validador de migração.

| Execução independente | Resultado observado |
|---|---|
| `python -m pytest tests -q -rxXs` | **68 passed**, 1 aviso do `joblib` sobre identificação de cores físicas; exit 0. |
| `python scripts/validate_account_migration.py` | PASS; upgrade de `20260504_0002` até `20261008_0011`, IDs preservados e campos legados cifrados. |
| `python scripts/validate_auth_flows.py` | PASS; registro, login/logout, papel único, 401 e limites cross-patient. |
| `python scripts/validate_doctor_links.py` | PASS; ciclo, autorização, proveniência, notificações e reimportação/revogação. |
| `python scripts/validate_foundational_security.py` | PASS; SQLite direto, ciphertext, hashes distintos e colisão de SHORTID. |
| `python scripts/validate_investigations.py` | PASS; escopo, origem, datas, médico revogado e estados CSCW. |
| `python scripts/validate_uci_demo_provisioning.py` | PASS; fixture offline, segunda importação, credenciais/IDs estáveis e vínculo revogado não reativado. |
| Sonda independente criada em `%TEMP%` (`myglico_audit_probe.py`) | PASS com chaves aleatórias efêmeras: AES-GCM round-trip, AAD por tabela/coluna/registro, rejeição de ciphertext adulterado, normalização HMAC, sal/hash e conversão/consulta local cruzando meia-noite em `America/Sao_Paulo`. O arquivo e as chaves não foram gravados no repositório nem impressos. |
| `cd frontend-react; MYGLICO_E2E_BACKEND_PORT=8251 MYGLICO_E2E_FRONTEND_PORT=8250 npx playwright test` | A primeira tentativa dentro do sandbox foi bloqueada ao carregar Vite. Após autorização, a suíte rodou no Chromium contra backend `8251`/frontend `8250`: **78 passed, 1 skipped, 1 failed**. Nenhuma porta proibida foi usada. |
| Repetição isolada de `CSCW-CA-25 - clearing the day selection keeps the period filter` | PASS, 1/1 em 43,4 s, mesmas portas/banco descartável. A falha da suíte integral não foi reproduzida, mas permanece intermitência não explicada. |

Não havia MCP de Playwright disponível nesta sessão; foi usado o runner Playwright versionado, conforme fallback permitido no `PROMPT-ORCA.md`. A suíte usa dados sintéticos e banco de teste. Os seis validadores receberam chaves hexadecimais aleatórias apenas no ambiente do processo; nenhum valor foi mostrado ou persistido.

### Resultado da navegação real

**Playwright integral: 78 passed, 1 skipped, 1 failed** (80 cenários). O skip é a falha injetada da publicação outbox (`CSCW-CA-29`, secundária no navegador), coberta por IT. A falha foi `CSCW-CA-25`: `openDetail` não encontrou o botão “Ver dias atípicos” durante a inicialização. A repetição isolada passou, portanto registro como não determinística, mas o resultado integral segue reprovado. A navegação cobriu landing, cadastro/sessão, busca/vínculos, revogação, autorização, isolamento de médicos, conversas, convites, notificações, filtros, fuso e PDF/idiomas; incluiu XSS, logout/volta/troca de conta e três idiomas.

## 2. Requisitos textuais por seção

Os CAs individuais estão rastreados na seção 3. Nesta tabela, cada seção e subseção textual dos SDDs é julgada como unidade; requisitos atômicos (RFs) foram desdobrados logo abaixo. Evidências `E2E` referem-se à execução real acima; `IT` ao pytest e validadores listados na seção 1.

### SDD1 — Cadastro, autenticação e proteção de dados

| Seção | Status | Evidência e julgamento |
|---|---|---|
| §1 instruções/adaptação | Atende | Arquitetura e entidades existentes preservadas; rotas/serviços adaptados. README, `app/models/entities.py`, testes de regressão. |
| §2 contexto e objetivo | Atende | UCI permanece demonstrativo e origem clínica continua referenciada a `Patient`; validação de migração preserva IDs/FKs. |
| §3.1 incluído | Divergência aceita | Conta com papel único foi escolha expressa do dono do produto em `BACKLOG.md` e `MATRIZ-ACEITE.md`; papéis Patient/Doctor, SHORTID, proteção, autenticação, vínculo e importação estão implementados. AUT-CA-19 e CSCW-CA-33 deixam de existir operacionalmente. |
| §3.2 fora de escopo | Atende | Não foram encontrados ResearchParticipation/novos algoritmos/alegações de CRM verificado; confirmação de e-mail não bloqueia cadastro. |
| §4 requisitos funcionais | Atende / divergências aceitas | RF-01..17 abaixo. Conta de papel único altera RF-06 por decisão aceita; credenciais públicas de demonstração alteram §8.1/§10 por decisão aceita. |
| §5.1 UserAccount | Atende | Campos e restrição de papel único, status, email verificado e aviso de privacidade; `app/models/entities.py:90-111`. Hash scrypt autocontido com salt é opção consolidada, não reversível. |
| §5.2 Patient | Atende | SHORTID, conta única, identidade cifrada e timezone; `app/models/entities.py:31-69`; `AUT-CA-07/16/17/21`. |
| §5.3 Doctor | Atende | Identidade e CRM/UF cifrados; índice cego CRM+UF; cadastro declarado sem selo verificado; `app/models/entities.py:119-147`; E2E-02/03. |
| §5.4 cardinalidade/associação | Divergência aceita | Relações individuais Patient ou Doctor por conta e ciclos de vínculo; papel único diverge da capacidade dual-role escrita, decisão do dono. E2E-02 e IT de auth. |
| §6.1 objetivo/alcance | Atende parcialmente | Campos textuais protegidos e exceções numéricas/documentadas; a própria documentação reconhece que pseudônimos, metadados e medidas consultáveis não equivalem a anonimização. Ver ressalva de retenção/backup no README. |
| §6.2 dados recuperáveis | Atende | AES-GCM versionado, nonce, AAD e chaves separadas; `app/core/crypto.py:31-79`; sonda temporária + IT. Não há alegação de anonimização. |
| §6.3 senhas | Atende | scrypt com salt aleatório por senha, validação genérica e sem senha reversível; E2E-02, validadores e sonda. |
| §6.4 busca protegida | Atende | HMAC com separação por finalidade e normalização consistente; lookup exato; `app/core/crypto.py:82-99`; E2E-03. |
| §6.5 leituras/dias atípicos | Atende | Algoritmo preservado; campos numéricos necessários permanecem consultáveis segundo exceção documentada; baseline de regressão e filtros/fuso no E2E-09. |
| §7 SHORTIDs | Atende | Gerador CSPRNG de seis caracteres e retry de colisão; validadores de segurança e `AUT-CA-18`. |
| §8.1 página pública | Divergência aceita | Landing sem conteúdo clínico e sem chamadas clínicas, ver E2E-01 nos três idiomas. SDD pede não mostrar credenciais demo, mas dono do produto aprovou credenciais públicas limitadas a dataset público e importação explícita; README §Authentication. |
| §8.2 cadastro | Atende | Campos por papel, aviso de privacidade para médico, transação e erro genérico; E2E-02 + `test_atomicity_rollback`. |
| §8.3 login/sessão | Atende | Cookie Secure/HttpOnly/SameSite, sessão revogável, limites e mensagem genérica; `app/core/security.py:45-64`, E2E-02. |
| §8.4 área autenticada | Divergência aceita | Isolamento, limpeza de cache e volta confirmados. Seletor dual-role é inaplicável pela decisão aceita de papel único. |
| §9 busca/vínculo/autorização | Atende | Propriedade, ciclo, revogação, PDF, proveniência e conversa verificados por E2E-03/04/05 e testes de fronteira. |
| §10.1 execução UCI | Divergência aceita | `--provision-demo-accounts` explícito e idempotente; usa credenciais públicas documentadas por decisão de produto, restritas ao namespace `.invalid` e dataset de demonstração. Validadores usam fixture offline. |
| §10.2 idempotência/isolamento | Atende | Nenhuma redefinição ou reativação de vínculo revogado; validator UCI e IT de idempotência. |
| §11 migração | Atende parcialmente | Cadeia parte de `20260504_0002`, preserva IDs e backfill; `validate_account_migration.py` passou. Porém 0003–0006 criam tabelas consultando os modelos ORM correntes em runtime, sem DDL congelado, achado P2-01. |
| §12 contratos | Atende | Operações aplicam identidade do servidor; E2E-01..08 e contratos API revisados. |
| §13 plano | Atende | Persistência, proteção, autenticação, UCI, landing, vínculos e regressão existem no diff. |
| §14 aceite/testes | Atende com divergências | 68 CAs percorridos abaixo; 66 atendidos e 2 N/A aceitos. E2E skip em CA-29 tem cobertura IT. |
| §15 concluído | Atende parcialmente | README documenta chaves, migração, importação, credenciais demo, dependências e limitações. O histórico não afirma conformidade integral LGPD. Pendências e limitações abaixo impedem aprovação final. |
| §16 referências | Atende | Referências técnicas não alteraram contrato nem introduziram dependência externa desnecessária. |

**RFs do SDD1:**

| ID | Requisito | Status | Evidência |
|---|---|---|---|
| RF-01 | Landing explica e oferece Entrar/Criar conta | Atende | E2E-01, pt-BR/en-US/es. |
| RF-02 | Sem paciente/leitura/histórico público | Atende | E2E-01 verifica chamadas e respostas, incluindo API/PDF anônimos. |
| RF-03 | Seleção Paciente/Médico com campos próprios | Atende | E2E-02. |
| RF-04 | Conta + Patient atômicos | Atende | E2E-02; `test_atomicity_rollback`. |
| RF-05 | Conta + Doctor atômicos | Atende | E2E-02; `test_atomicity_rollback`. |
| RF-06 | Uma conta pode ter dois perfis | Divergência aceita | Dono do produto definiu papel único; regra reforçada com 409 no segundo papel (`BACKLOG.md`, `MATRIZ-ACEITE.md`). |
| RF-07 | Papel/IDs não elevam privilégio | Atende | E2E-02 adulteração de papel/IDs; auth service resolve a sessão. |
| RF-08 | Login sem confirmação e-mail | Atende | E2E-02. |
| RF-09 | SHORTID único para cada tipo de domínio | Atende | Constraints em `entities.py:31-38,119-129`; validator de colisão. |
| RF-10 | Busca por SHORTID ou CRM+UF | Atende | E2E-03; lookup HMAC. |
| RF-11 | Busca retorna perfil mínimo | Atende | E2E-03 inspeciona payload mínimo. |
| RF-12 | Vínculo por ação e confirmação explícitas | Atende | E2E-03: pending não autoriza; destinatário confirma. |
| RF-13 | Médico lista pacientes ativos autorizados | Atende | E2E-03/04 e testes de autorização. |
| RF-14 | Paciente acessa somente seus registros | Atende | E2E-05 IDOR patient↔patient, API/PDF/proveniência. |
| RF-15 | Logout invalida sessão | Atende | E2E-02 logout/troca/voltar. |
| RF-16 | UCI provisiona contas e vínculo demo | Atende | Validator UCI em SQLite descartável, duas contas de fixture. |
| RF-17 | Reimport não duplica nem reseta credenciais | Atende | Validator UCI e `test_idempotency_recompute_import`. |

### SDD2 — Vínculos, CSCW e proveniência

| Seção | Status | Evidência e julgamento |
|---|---|---|
| §1 instruções/dependências | Atende | Um único núcleo de busca/vínculo; os invariantes aparecem nos testes. |
| §2 objetivo/escopo | Atende | Fluxo colaborativo de contexto, sem diagnóstico/IA ou canal externo; convites não abrem conversa sozinhos. |
| §2.1 incluído | Atende | Busca, ciclo, eventos, mensagens, popup, convite e notificações cobertos pela suíte. |
| §2.2 fora de escopo | Atende | Sem conversa multi-médico, reabertura, anexos ou notificações externas. |
| §3 invariantes | Atende | IDs resolvidos no servidor, ciclo associado, isolamento e revogação; E2E-04/05/06. |
| §4 busca | Atende | Perfil mínimo, limite, request explícito e ausência de acesso antes de ACTIVE; E2E-03. |
| §5 ciclo de associação | Atende | PENDING/ACTIVE/terminal, ator correto, ciclo histórico, revogação bilateral, encerramento administrativo e reaceite; E2E-03/04 + validators. UCI é agente software. |
| §6 investigações | Atende | Origem opcional, mensagem cifrada, autoria/ordem, marcador monotônico e leitura efetiva; E2E-05/06/08 + IT. |
| §7 abertura/dia atípico | Atende | Origem validada, destinatário explícito, convite adiável e deduplicado, origem histórica; E2E-05/06/07/09. |
| §8 acompanhamento/encerramento | Atende | AwaitingRole não bloqueia mensagens consecutivas; encerramento por qualquer parte e bloqueio após CLOSED; E2E-06. |
| §9 card/popup/filtros | Atende parcialmente | Cenários exatos, composição, limpeza, acessibilidade e estados passaram em E2E-09, mas o cenário de limpeza falhou uma vez na suíte completa ao não montar o botão inicial; passou isoladamente. A flakiness não foi explicada (achado P2-03). |
| §10 proveniência persistida | Atende parcialmente | Eventos transacionais e consulta autorizada persistem no banco (`routes.py:451,681,755+`; `services/doctor_links.py`, `investigations.py`), mas a exportação PROV existente não inclui esses eventos CSCW e o R2RML/ontologia ficaram sem projeção/relação nova; achado P2-02. |
| §10.4 outbox/notificações | Divergência aceita, com limite operacional | Decisão O8 do dono do produto: inbox transacional é fonte visível; consumidor em loop local/CLI e desligado em Vercel, sem canal externo. Retry idempotente comprovado em IT. Em instância Vercel, o estado de entrega pode permanecer PENDING até CLI/worker; isso não oculta o registro de inbox. |
| §10.5 PROV-O | Atende parcialmente | IDs semânticos existentes preservados, mas eventos de vínculo/CSCW não são projetados para PROV-O atualmente; achado P2-02. |
| §10.6 preservação/consulta | Atende | Append-only por credenciais da app, paciente mantém histórico, médico revogado recebe 404; E2E-04. |
| §11 notificações/não lidas | Atende | Contagem de notificações separada da contagem de mensagens; leitura de listagem não zera conversa; E2E-08 + IT. Limitação do dispatcher descrita acima. |
| §12 concorrência/segurança | Atende | Barreiras de concorrência, idempotência, revogação, XSS e autorização por recurso; IT e E2E-05/06. |
| §13 contratos | Atende | Rotas e payloads adaptados, papéis/IDs confiados ao servidor; `CONTRATOS-API.md`, E2E. |
| §14 plano | Atende | Entidades, eventos, UI e testes entregues. |
| §15 aceite | Atende com 2 N/A aceitos | 45 critérios discriminados abaixo. |
| §16 concluído | Atende parcialmente | Evidência e limitações registradas neste parecer; P2-01 e P2-02 deixam requisito de migração/projeção incompleto. |
| §17 histórico | Atende | Versão 1.1 coordenativa refletida no fluxo de convite e critérios CSCW-CA-36..45. |
| §18 referências | Atende | PROV-O e controles de autorização são compatíveis conceitualmente; falta a projeção de eventos CSCW, achado P2-02. |

## 3. Critérios de aceite — 68 linhas rastreadas

### AUT-CA-01 a AUT-CA-23

| ID | Cenário (resumo) | Status | Evidência independente |
|---|---|---|---|
| AUT-CA-01 | Visitante vê landing e nenhum dado clínico | Atende | E2E-01, incluindo rede/API. |
| AUT-CA-02 | APIs/rotas antigas de paciente negam anônimo | Atende | E2E-01: JSON, API e PDF. |
| AUT-CA-03 | Cadastro paciente + SHORTID | Atende | E2E-02; validator auth. |
| AUT-CA-04 | Cadastro médico e campos protegidos | Atende | E2E-02; validator crypto/migration. |
| AUT-CA-05 | Falha não deixa conta órfã | Atende | E2E-02; `test_atomicity_rollback`. |
| AUT-CA-06 | Cadastro/login sem e-mail confirmado | Atende | E2E-02. |
| AUT-CA-07 | Banco direto não revela PII protegida | Atende | Validator migration/security; inspeção SQLite de teste. |
| AUT-CA-08 | Mesma senha não reutiliza hash/salt | Atende | Validator security e sonda temporária. |
| AUT-CA-09 | E-mail duplicado/concorrente preserva unicidade | Atende | E2E-02 duplicado; constraints e IT concorrência. |
| AUT-CA-10 | Busca exata SHORTID/CRM+UF | Atende | E2E-03. |
| AUT-CA-11 | Adulteração de papel/IDs não eleva acesso | Atende | E2E-02. |
| AUT-CA-12 | Paciente A não acessa paciente B | Atende | E2E-05 em URLs/IDs e recursos. |
| AUT-CA-13 | Médico sem vínculo não acessa paciente | Atende | E2E-05. |
| AUT-CA-14 | Revogação tira acesso de sessão existente | Atende | E2E-04 com sessão aberta; API volta negar. |
| AUT-CA-15 | Dois médicos não compartilham conversa | Atende | E2E-05, teste com dois médicos associados. |
| AUT-CA-16 | Primeira importação cria contas/vínculos demo | Atende | `validate_uci_demo_provisioning.py` (fixture isolada). |
| AUT-CA-17 | Segunda importação preserva estado/contagens | Atende | Validator UCI + IT idempotência. |
| AUT-CA-18 | Colisão SHORTID gera novo valor | Atende | Validator security força colisão. |
| AUT-CA-19 | Conta com Patient e Doctor | Não aplicável | Divergência de produto aceita: conta tem papel único; E2E-02 valida rejeição HTTP 409 ao cadastrar segundo papel. |
| AUT-CA-20 | Logout/troca/cache/voltar | Atende | E2E-02 API e navegador. |
| AUT-CA-21 | Leituras/dias atípicos preservados após reprocessar | Atende | IT idempotência/baseline; E2E-09 fuso e dias. |
| AUT-CA-22 | AAD e adulteração de ciphertext falham fechados | Atende | Sonda temporária; `test_crypto_and_secrets`. |
| AUT-CA-23 | Logs/bundle/respostas sem segredo ou clínico público | Atende | E2E-01 varredura de bundle/respostas; validator security. |

### CSCW-CA-01 a CSCW-CA-45

| ID | Cenário (resumo) | Status | Evidência independente |
|---|---|---|---|
| CSCW-CA-01 | Busca paciente por SHORTID ou CRM+UF | Atende | E2E-03. |
| CSCW-CA-02 | Pedido cria PENDING sem acesso clínico | Atende | E2E-03. |
| CSCW-CA-03 | Outro médico não confirma pedido | Atende | E2E-03. |
| CSCW-CA-04 | Destinatário confirma com ator/versão | Atende | E2E-03 + `validate_doctor_links.py`. |
| CSCW-CA-05 | Rejeitar/cancelar registra terminal/evento | Atende | E2E-03. |
| CSCW-CA-06 | Paciente revoga unilateralmente | Atende | E2E-04. |
| CSCW-CA-07 | Médico revoga unilateralmente | Atende | E2E-04. |
| CSCW-CA-08 | Revogação corta sessão/avisos antigos | Atende | E2E-04: acesso seguinte negado. |
| CSCW-CA-09 | Revogação fecha investigação, preserva paciente | Atende | E2E-04. |
| CSCW-CA-10 | Reassociação exige ciclo e não traz conversa antiga | Atende | E2E-04. |
| CSCW-CA-11 | Reimport não duplica nem reativa revogado | Atende | Validator UCI + IT. |
| CSCW-CA-12 | Vínculo UCI atribuído a software | Atende | Validator UCI inspeciona ator/evento. |
| CSCW-CA-13 | Paciente abre com origem real | Atende | E2E-05, formulário/browser. |
| CSCW-CA-14 | Abertura sem origem não inventa evento | Atende | E2E-05. |
| CSCW-CA-15 | Médico abre no próprio contexto ativo | Atende | E2E-05. |
| CSCW-CA-16 | Evento de outro paciente é recusado | Atende | E2E-05 sem vazamento. |
| CSCW-CA-17 | Escolha explícita e isolamento multi-médico | Atende | E2E-05. |
| CSCW-CA-18 | Mensagem cifrada, autor/ordem/proveniência | Atende | E2E-06 + IT de criptografia/proveniência. |
| CSCW-CA-19 | Leitura efetiva monotônica e idempotente | Atende | E2E-08 + IT. |
| CSCW-CA-20 | Qualquer participante encerra corretamente | Atende | E2E-06. |
| CSCW-CA-21 | CLOSED rejeita envio e preserva histórico | Atende | E2E-06. |
| CSCW-CA-22 | Recalcular mantém origem histórica | Atende | E2E-06 com recálculo e badge de origem. |
| CSCW-CA-23 | Popup coerente com contagem/escopo | Atende | E2E-09. |
| CSCW-CA-24 | Dias não consecutivos filtram exatamente | Atende | E2E-09 e API `dates=`. |
| CSCW-CA-25 | Combinação/limpeza de filtros | Atende parcialmente | E2E integral falhou uma vez em `openDetail` antes da limpeza (botão de dias ausente); repetição isolada 1/1 passou; demais cenários de composição/limpeza E2E-09 passaram. |
| CSCW-CA-26 | Medição perto da meia-noite no fuso | Atende | E2E-09, IT Lote 4 e sonda independente. |
| CSCW-CA-27 | Loading/vazio/erro acessíveis | Atende | E2E-09, teclado/foco/ARIA. |
| CSCW-CA-28 | Falha de proveniência reverte domínio | Atende | `test_atomicity_rollback`, `test_provenance_events`. |
| CSCW-CA-29 | Falha/retry não duplica efeitos | Atende | `test_outbox_and_delivery`; E2E secundário skip apenas para injeção Python. |
| CSCW-CA-30 | Corridas confirmação/revogação/envio/fecho | Atende | IT concorrência + E2E-06. |
| CSCW-CA-31 | Banco/log sem mensagens ou PII em claro | Atende | Validator security + `test_crypto_and_secrets`. |
| CSCW-CA-32 | Médico revogado não lê proveniência clínica | Atende | E2E-04 e endpoint com 404 após revogar. |
| CSCW-CA-33 | Uma conta atua nos dois papéis | Não aplicável | Mesma decisão aceita de papel único; E2E-06 mostra papel do autor derivado do servidor. |
| CSCW-CA-34 | Repetição idempotente causa um efeito | Atende | IT idempotência + E2E-03. |
| CSCW-CA-35 | Landing continua pública sem pacientes | Atende | E2E-01 nos três idiomas. |
| CSCW-CA-36 | Novo dia cria convite, não conversa | Atende | E2E-07 + IT proveniência. |
| CSCW-CA-37 | “Agora não” persiste e não se repete | Atende | E2E-07, reload e abertura manual. |
| CSCW-CA-38 | Convite exige médico e notifica só escolhido | Atende | E2E-07 com vários médicos. |
| CSCW-CA-39 | Mensagem do médico gera contador do paciente | Atende | E2E-08 após logout/login. |
| CSCW-CA-40 | Mensagem do paciente gera contador do médico | Atende | E2E-08 simétrico. |
| CSCW-CA-41 | Ler notificação/listar não limpa mensagens | Atende | E2E-08 + IT. |
| CSCW-CA-42 | Página não exibida/falha não é marcada lida | Atende | E2E-08 com paginação e falha. |
| CSCW-CA-43 | Exibir mensagem avança marcador uma vez | Atende | E2E-08 + IT. |
| CSCW-CA-44 | Falha do canal recupera do persistido | Atende | E2E-08 intercepta polling e recupera após reload. |
| CSCW-CA-45 | UCI consolida/deduplica datas históricas | Atende | Validator UCI, IT importação/reprocessamento e E2E-07. |

## 4. Achados

### P2-01 — Revisões 0003–0006 não congelam o DDL

- **Tipo:** omissão de reprodutibilidade da migração.
- **Requisito:** SDD1 §11; instruções de migração do README/AGENTS; escopo desta auditoria, item E.
- **Evidência:** `alembic/versions/20261006_0003_accounts_encryption.py:32-33`; `20261006_0004_user_sessions.py:22`; `20261006_0005_patient_doctor_links_notifications.py:22-23`; `20261006_0006_investigations_prompts.py:22-26`. Cada revisão usa `Model.__table__.create()`/`.drop()` em vez de descrever integralmente as colunas/constraints da revisão.
- **Comportamento observado:** a cadeia passa em SQLite no estado atual; porém o schema instalado por uma revisão antiga depende da versão corrente de `app.models.entities`. Alterações futuras no ORM podem mudar o resultado de uma instalação nova que rode essas revisões, enquanto instalações já atualizadas mantêm outro schema. O README reconhece expressamente essa variação, mas documentação de risco não congela o contrato.
- **Impacto:** upgrades e instalações limpas podem divergir sem alteração no histórico Alembic; a migração de produção não é reproduzível somente pelo conjunto de revisões.
- **Correção esperada:** antes de declarar essas revisões como base imutável publicada, congelar o DDL no próprio histórico de modo que novas instalações reproduzam exatamente o schema validado; se já publicadas/aplicadas, não editar silenciosamente: adicionar uma estratégia de baseline/revisão explícita e validar upgrade a partir de `0920365` em SQLite e MySQL. O teste atual cobre SQLite, não MySQL.

### P2-02 — Eventos CSCW persistidos não têm projeção PROV-O correspondente

- **Tipo:** omissão de interoperabilidade/auditabilidade semântica.
- **Requisito:** SDD2 §§10.1, 10.5 e 16; preservação de ontologia/PROV.
- **Evidência:** `app/services/provenance.py:10-14` importa somente entidades da trilha de importação (`AnalysisRun`, `RawImportRecord`, `GlucoseRecordSource`, etc.), sem `ProvenanceEvent`; `mappings/myglico-core-r2rml-juma.ttl` mapeia o núcleo clínico `Patient → GlucoseMeasurement → RawRecord`, sem as novas atividades/entidades CSCW. `git diff 0920365` não altera `ontology/` nem `mappings/`.
- **Comportamento observado:** eventos de vínculo, investigação, leitura e filtros são gravados e consultáveis no banco transacional, com controles de acesso; porém a exportação PROV-JSON/TTL preexistente segue cobrindo a importação/analytics e não representa os eventos de colaboração como `prov:Activity`, `prov:Agent` e `prov:Entity`.
- **Impacto:** a trilha operacional é auditável dentro da API/banco, mas não pode ser consultada/reconstruída na projeção semântica do projeto conforme o modelo descrito pelo SDD. Ausência de mudança na ontologia preserva IDs existentes, mas não satisfaz a adaptação/consulta da nova trilha.
- **Correção esperada:** adicionar mapeamento/exportação compatível, com IDs estáveis e relações PROV-O para eventos CSCW, sem incluir mensagens/PII em literais públicos; aplicar a mesma autorização da API e cobrir a projeção com teste. Se a decisão for manter apenas trilha relacional nesta entrega, registrar formalmente a exceção de escopo em vez de declarar projeção concluída.

### P2-03 — E2E de limpeza de filtro falha intermitentemente na suíte integral

- **Tipo:** defeito/intermitência de inicialização ou isolamento de estado; causa ainda não identificada.
- **Requisito:** SDD2 §9.3 e CSCW-CA-25; `PROMPT-ORCA.md`, exigência de E2E reproduzível e sem sleeps arbitrários.
- **Evidência:** execução integral `npx playwright test`: cenário `frontend-react/e2e/specs/09-atypical-popup-filters.spec.mjs:84-87` falhou esperando o botão acessível `cscw.popupButton` em `openDetail` (timeout de 10 s; elemento não encontrado). Repetição isolada do mesmo cenário passou 1/1 em 43,4 s.
- **Comportamento observado:** na sequência completa, depois de cenários de popup/filtros, o detalhe não apresentou o botão esperado; isolado com banco reiniciado, o botão apareceu e a operação de manter o período ao limpar dias passou.
- **Impacto:** a experiência de dias atípicos e a suíte completa não são determinísticas; um único passe isolado não invalida a falha observada em execução integral. CAs adjacentes passaram, mas não provam confiabilidade do cenário falho.
- **Correção esperada:** identificar se o botão some por estado global de análise/filtro, fixture/conta reaproveitada ou falha de carregamento; tornar o estado do fixture isolado e a espera dependente de condição da API/UI apropriada, então repetir a suíte completa sem falhas.

### P3-01 — Artefato incidental e whitespace

- **Tipo:** alteração acidental/limpeza de entrega.
- **Requisito:** inspeção integral do diff e entrega limpa.
- **Evidência:** arquivo não rastreado `debug.log` (258 bytes; duas mensagens Crashpad); `git diff --check 0920365` reporta trailing whitespace em SDDs/JSX e linhas finais em branco.
- **Comportamento/impacto:** não afeta a execução nem contém segredo aparente, mas é ruído na entrega e o diff não passa no verificador de whitespace.
- **Correção esperada:** remover o log incidental antes de integrar e limpar whitespace dos arquivos novos/editados.

### Limitações e divergências aceitas — não tratadas como defeitos

- **Papel único por UserAccount:** decisão explícita do dono do produto em `BACKLOG.md` e `MATRIZ-ACEITE.md`; AUT-CA-19 e CSCW-CA-33 são N/A, e as rotas rejeitam segundo papel de modo coerente.
- **Credenciais demo públicas (`patientN@demo.myglico.invalid`, `doctor@demo.myglico.invalid`, `qwerty`):** divergência de SDD1 §§8.1 e 10.1, aceita pelo dono do produto e limitada ao dataset público/flag de provisionamento. O validator confirma preservação de senha alterada e que reimport não a redefine. Não usar em contas comuns.
- **O8 enxuto:** decisão do dono em `BACKLOG.md` §“O8 — Versão enxuta implementada”; inbox/notificação nasce na transação e independe do dispatcher. Loop local ou CLI drena retry; no Vercel dispatcher fica `off`, portanto a coluna de entrega pode ficar PENDING sem cron/worker. É coerente com a ausência atual de canal externo, mas deixa explícita a limitação quando surgir integração externa.
- **Dispatcher no shutdown:** `app/main.py:45-52,64-72` usa `asyncio.to_thread`; cancelar e aguardar a task não interrompe necessariamente a thread já iniciada. SQLite com vários consumidores pode ainda disputar lock porque não há claim durável específico. A matriz anterior trata isso como risco operacional P3; não vi perda da inbox nem duplicação neste escopo/teste. Resolver antes de adicionar múltiplos workers ou efeitos externos.
- **Rate limit:** `app/core/rate_limit.py:1-4` guarda janela por processo; README §“Useful variables” documenta que produção multiworker/instância precisa backend compartilhado. Teste de limite local passou; defesa global não foi demonstrada e é limitação operacional documentada.

## 5. Veredito

# REPROVADO

Os fluxos de autenticação, autorização, revogação, CSCW, fuso, criptografia, importação, landing e notificações tiveram forte cobertura independente: pytest 68/68, seis validadores, sonda própria e Playwright integral 78/1 skip/1 falha (com repetição isolada do cenário falho passando). As duas decisões de produto encontradas foram classificadas como divergências aceitas, não como defeitos.

Ainda assim, **não aprovo a entrega integral**: P2-01 deixa o schema histórico dependente dos modelos ORM atuais, sem reprodução determinística do upgrade; P2-02 mantém a trilha CSCW fora da projeção PROV-O apesar do fluxo semântico existente; P2-03 mostra uma falha E2E real e não determinística em CSCW-CA-25, não explicada pela repetição isolada. A trilha relacional e os passes adjacentes não eliminam essas pendências. O P3-01 é limpeza de baixo impacto. É necessária correção e nova revisão dos pontos P2; não foram rebaixados a observações futuras.

AUDITORIA_INTEGRAL_CONCLUIDA veredito=REPROVADO

## 6. Reauditoria

Reauditoria realizada em 2026-10-09 sobre as correções listadas em
`BACKLOG.md`, sem alterar o parecer original acima. A regressão foi executada
com bancos SQLite descartáveis em `%TEMP%`; `data/myglico.db` permaneceu com
`LastWriteTime=2026-10-08 14:10:44` e tamanho de 614400 bytes antes do registro
desta seção. Os servidores E2E encerraram normalmente: não havia listener nas
portas 8250/8251 ao final.

### Estado dos achados anteriores

| Achado | Estado | Verificação independente |
|---|---|---|
| P2-01 — DDL das migrações | **Resolvido** | Revisei a cadeia 0001–0011: as revisões têm DDL explícito, inclusive 0003–0006; `validate_account_migration.py` passou na execução nova, e os testes completos exercitaram as migrações. A decisão do produto de não aplicar migrações a banco persistente e recriar a produção do zero está registrada em `BACKLOG.md`; considero essa divergência operacional aceita e coerente com a cadeia verificada. A ordem física de colunas diferente em algumas tabelas, registrada no backlog, não apresentou diferença semântica reportada. |
| P2-02 — projeção PROV-O dos eventos CSCW | **Resolvido** | Os testes de `tests/integration/test_cscw_prov_projection.py` passaram dentro do pytest completo (74 aprovados). A inspeção de `app/services/cscw_provenance.py` confirmou projeção dos tipos CSCW, filtro por paciente e ausência de texto de mensagem/PII como literais; o agente humano usa `_lookup_hmac("cscw_prov_agent", account_id)`. `scripts/export_cscw_provenance.py` implementa exportação PROV-JSON/Turtle como CLI de operador, exige destino e recusa diretórios públicos; não expõe endpoint HTTP. |
| P2-03 — instabilidade E2E | **Resolvido na reexecução observada** | O Playwright integral foi executado duas vezes, cada uma com 80 casos: **79 passed, 1 skipped, 0 failed** em ambas. CSCW-CA-25 (limpeza/composição e preservação do período) e CSCW-CA-23/A1 passaram nas duas execuções. O resultado confirma estabilidade nestas duas rodadas, sem alegação de prova universal. |
| P3-01 — log incidental e whitespace | **Resolvido** | `debug.log` não existe. `git diff --check` não reportou erro de whitespace; emitiu apenas avisos de conversão LF/CRLF do Git. Os espaços finais dos SDDs continuam documentados como quebras Markdown intencionais. |

### Revisão das alterações relacionadas

- **Pseudônimo HMAC:** o identificador de agente da projeção é derivado com
  HMAC keyed e domínio `cscw_prov_agent`, em vez de hash com sal público. A
  chave não é incluída no artefato. A implementação preserva um pseudônimo
  estável sob a mesma chave sem tornar a comparação offline trivial a partir
  de IDs conhecidos.
- **`PatientDetailPage.jsx`:** o retorno antecipado do efeito para dados já
  resolvidos agora também encerra `loading`; o caminho normal mantém a
  atualização no `finally`, limitada à requisição ativa. Os cenários de popup,
  filtros e estados de carregamento passaram nas duas rodadas E2E.
- **`tests/integration/conftest.py`:** a localização do arquivo SQLite deriva
  de `MYGLICO_INTEGRATION_DATABASE_URL`. A execução de pytest foi apontada para
  um arquivo em `%TEMP%`, sem usar `data/myglico.db`.
- **CSCW-CA-29:** o teste de integração agora drena a outbox até ficar ociosa,
  eliminando dependência de linhas pendentes de testes anteriores. O teste
  correspondente passou no pytest integral. O caso E2E de mesmo nome segue
  marcado como skip intencional porque injetar falha de publicação exige
  monkeypatch do serviço Python; o próprio teste registra a cobertura de
  retry/ausência de duplicação em
  `tests/integration/test_outbox_and_delivery.py`.

### Regressão executada

- `python -m pytest tests -q -rxXs`, com
  `MYGLICO_INTEGRATION_DATABASE_URL` apontando a SQLite em `%TEMP%`:
  **74 passed**.
- Os seis validadores (`validate_account_migration.py`,
  `validate_auth_flows.py`, `validate_doctor_links.py`,
  `validate_foundational_security.py`, `validate_investigations.py` e
  `validate_uci_demo_provisioning.py`): **6/6 passaram**, usando chaves
  hexadecimais efêmeras nas variáveis exigidas, sem imprimi-las.
- `cd frontend-react && npm run test:e2e`, duas execuções integrais com
  `MYGLICO_E2E_BACKEND_PORT=8251`, `MYGLICO_E2E_FRONTEND_PORT=8250` e arquivos
  SQLite separados em `%TEMP%`: **79 passed / 1 skipped / 0 failed** em cada
  rodada (7,8 e 7,7 minutos).
- `git diff --check`: nenhum erro; somente avisos de conversão de finais de
  linha. `debug.log`: ausente.

### Novos achados e veredito

Não identifiquei novo achado bloqueador nesta reauditoria. O skip CSCW-CA-29 é
deliberado e coberto pela integração, não uma falha da suíte. As correções
resolvem os quatro achados do parecer, e as mudanças adjacentes revisadas
passaram pela regressão executada.

# APROVADO

REAUDITORIA_CONCLUIDA veredito=APROVADO
