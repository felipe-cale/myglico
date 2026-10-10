# Revisão final independente — Revisão #7 (atual)

**Revisor:** Codex, worker independente; não autor das alterações revisadas. **Data/hora:** 2026-10-09 16:57 -03:00 (America/Sao_Paulo).

**Objeto:** worktree sobre `6a70133`, sem commit. Identificador do diff rastreado, excluindo este arquivo para evitar hash circular: SHA-256 **`334d98f87e2804e525d55784894708f8cef988cfcea7af3d34a327f82d3d6b6a`**, calculado em 2026-10-09 16:50 -03:00. Havia 18 arquivos novos não rastreados, inspecionados separadamente; eles não entram no hash do `git diff`.

## Veredito #7

# **APROVADO**

G1 e G2 foram corrigidos e confirmados por execução. O8 enxuto atende ao escopo escolhido: as requisições não drenam a outbox, inbox e contadores continuam disponíveis pela persistência transacional, e retry/idempotência permanecem demonstrados. Não encontrei regressão obrigatória na amostragem da matriz. Registro abaixo um risco operacional P3 de encerramento/concorrência que não bloqueia este escopo, pois a outbox atual não produz efeitos externos e o caminho de produção Vercel mantém o dispatcher desligado.

## Critérios desta revisão

### G1 — aviso de privacidade para paciente e médico: aprovado, sem achado

**Critério:** SDD1 §8.2. **Gravidade:** sem achado. **Arquivos/linhas:** `app/api/routes.py:69-105, 190-198`; `app/services/auth_service.py:57-105`; `frontend-react/src/pages/RegisterPage.jsx:33-48`.

A API rejeita aceite ausente, falso ou nulo com 422: o campo default `false` e o validador cobrem ausência/falso, e `null` é inválido para o tipo booleano. `register_account` repete a exigência no serviço e grava `privacy_notice_accepted_at` para ambos os papéis. A UI bloqueia o envio sem marcar a caixa e inclui `privacy_notice_accepted` no payload compartilhado por paciente e médico. O registro é armazenado como ciência do aviso nesse campo específico, sem ser usado como consentimento genérico.

**Execução:** `tests/integration/test_lote4_timezone_and_provenance.py::test_patient_registration_records_privacy_notice_acknowledgement` passou; testa paciente com valor ausente, falso, nulo e verdadeiro, além da persistência do timestamp. O E2E de cadastro do médico confirmou payload com aceite verdadeiro. A validação comum da API e do serviço aplica-se aos dois papéis.

### G2 — flag de investigação não atravessa ciclos nem médicos: aprovado, sem achado

**Critério:** SDD2 §10 / CSCW-CA-10. **Gravidade:** sem achado. **Arquivo/linhas:** `app/api/routes.py:724-750`; regressões em `tests/integration/test_lote4_timezone_and_provenance.py:90-108`.

No contexto médico, a rota localiza o vínculo ACTIVE atual e restringe `has_investigation` por `doctor_id` e `association_id`; sem vínculo ativo, a comparação com `None` não encontra investigação. Reassociar o mesmo médico não expõe a flag do ciclo revogado. No contexto do paciente não há esse filtro médico, então ele mantém a visão das próprias investigações.

**Execução:** o teste de reassociação passou: médico A vê `true` antes da revogação e `false` depois da nova associação; paciente continua vendo `true`. Fiz também uma verificação adicional com dois médicos e dois dias de origem: cada médico recebeu `true` apenas para a própria investigação, e o paciente recebeu `true` para ambas. E2E AUT-CA-15/CSCW-CA-17 também confirmou isolamento entre médicos.

### O8 — versão enxuta: aprovada

**Critério:** escopo O8 em `BACKLOG.md`, CSCW-CA-29, durabilidade/retry/idempotência e independência da inbox. **Gravidade:** sem achado obrigatório; risco residual P3 abaixo. **Arquivos/linhas:** `app/main.py:39-73`; `app/core/config.py:43-50`; `app/services/notification_outbox.py:23-64`; `scripts/notification_outbox.py:1-62`; `README.md:219-230, 339-343`.

- O middleware não chama o consumidor. `test_o8_api_requests_never_drain_the_outbox` passou: consultas repetidas de notificações e vínculos deixam a linha em `PENDING`, com zero tentativas.
- O loop inicia no startup apenas com `notification_dispatcher=loop`, cancela no shutdown e captura/loga exceções para nova tentativa. Config aceita `loop|off`; Vercel usa `off` por padrão. O README corresponde ao código.
- `scripts/notification_outbox.py stats` informou 63 pendentes no SQLite descartável; `run` processou 63 com 0 falhas; o segundo `stats` mostrou 159 `DELIVERED` e nenhum `PENDING`. Foi usado `data/integration.db`, não `data/myglico.db`.
- `test_cscw_ca_29_failed_publication_is_retried_from_a_durable_row_without_duplicate_effects` passou: falha deixa `PENDING`, persiste tentativa/backoff e classe do erro sem conteúdo privado; retry marca `DELIVERED` e mantém exatamente uma notificação de inbox. O E2E correspondente é skip deliberado porque falha exige injeção Python; a cobertura de integração passou.
- Inbox e contadores são gravados junto com a mutação em tabelas próprias e foram recuperados nos testes de persistência/reconexão; não dependem do consumidor da outbox.

**Risco operacional P3 — cancelamento durante trabalho em thread e concorrência SQLite.** **Critério:** ciclo de vida e múltiplos workers O8. **Arquivo/linhas:** `app/main.py:45-73`; `app/services/notification_outbox.py:31-62`. `asyncio.to_thread` executa o dreno fora do event loop; cancelar a task awaiter no shutdown não interrompe a thread já iniciada. Com múltiplos processos SQLite, `FOR UPDATE SKIP LOCKED` não fornece exclusão efetiva e pode haver disputa/`database is locked`; exceções são registradas e o loop tenta de novo, e a transação evita confirmar tentativa parcialmente. No MySQL, o bloqueio de linha serializa o lote; na Vercel o loop fica desligado. O “delivery” atual só confirma a existência do registro de inbox já persistido, então seleções concorrentes não criam notificações ou efeitos externos duplicados; `attempts` conta tentativas confirmadas, não seleções. **Impacto:** encerramento abrupto pode adiar atualização de status até outro ciclo; concorrência SQLite pode gerar erro transitório e ruído de log, sem perder a inbox ou duplicar `DELIVERED` neste desenho. **Correção esperada:** aguardar trabalho em curso com limite no shutdown e, caso múltiplos consumidores SQLite ou efeitos externos sejam adicionados, introduzir claim/serialização durável antes da publicação. Não é pendência obrigatória para o O8 enxuto avaliado.

## Regressão executada

- `python -m pytest tests -q -rxXs`: **68 passed**, sem falhas ou skips; um aviso de `joblib` sobre detecção de núcleos físicos no Windows.
- Seis `scripts/validate_*.py`, com `MYGLICO_ENCRYPTION_KEY_V1` e `MYGLICO_LOOKUP_HMAC_KEY` efêmeras e hexadecimais no ambiente dos processos: **6/6 passaram**. As chaves não foram impressas nem gravadas.
- `cd frontend-react && MYGLICO_E2E_BACKEND_PORT=8231 MYGLICO_E2E_FRONTEND_PORT=8230 npx playwright test`: **79 passed, 1 skipped, 0 failed** em SQLite descartável. **`database is locked`: 0 ocorrências** na execução concluída. A primeira tentativa parou antes da suíte por bloqueio de leitura do workspace pelo sandbox; a repetição autorizada executou os 80 casos.
- Usei apenas as portas **8230/8231**. Não usei 8000/8001/8101/8220/8221 nem `data/myglico.db`; as portas 8230/8231 ficaram livres após o Playwright.

## Matriz de aceite e amostragem

Recontei **68 critérios: 66 Aprovado e 2 Não aplicável** (AUT-CA-19 e CSCW-CA-33), sem status parcial/reprovado na matriz. A suíte E2E cobriu AUT-CA-01..23 e CSCW-CA-01..45 por cenários de landing/cadastro/sessão, autorização/troca de conta, busca/vínculos/revogação, isolamento de investigações, mensagens/encerramento, convites, notificações/contadores, filtros de dias atípicos, fuso local, idiomas e PDF. A suíte backend cobriu criptografia/transações, autorização, idempotência, concorrência e retry da outbox; CSCW-CA-29 foi verificado nela por causa do skip no navegador. A verificação cruzada confirmou G1 em AUT-CA-03/04/05 e G2 em AUT-CA-15/CSCW-CA-10/17. O8 não regrediu CSCW-CA-29, CSCW-CA-39..44 nem a inbox/contadores.

---
## Registro histórico — Revisão #6, auditoria geral e revisões anteriores

### Revisão final independente — revisão #6 (registro histórico)

**Revisor:** Codex, worker independente; não autor das alterações revisadas. Revisão conduzida em 2026-10-09, horário local America/Sao_Paulo.

**Objeto:** branch `felipe-cale/auth-vinculos-cscw`, diff do worktree sobre `6a70133`, sem commit. Identificador do código avaliado (excluindo este arquivo para evitar hash circular): `git diff 6a70133 -- . ':(exclude)features/a-desenvolver/REVISAO-FINAL.md'` — 40 arquivos rastreados, **+1367/−220**, SHA-256 **`a9d8b71a945408c9d478359f9b29adb68b61fdb25f5b0db5232440f3f95441ea`**, medido em **2026-10-09 09:34 -03:00**. Havia ainda 11 arquivos novos não rastreados; foram inspecionados separadamente. Não editei código, testes, migrações nem a matriz.

## Veredito

# **APROVADO**

As pendências obrigatórias da revisão #5 foram verificadas e resolvidas no diff avaliado. Nenhum defeito obrigatório ficou rebaixado a observação. Os riscos abaixo são limitações não bloqueantes, conforme a lista de liberação da revisão #5.
## Auditoria geral posterior — **REPROVADO**

Em resposta ao pedido de confrontar todo o desenvolvimento com os SDDs, um segundo agente fez leitura independente do diff e dos requisitos. Esta auditoria ampliada não invalida os testes que passaram nem o veredito da revisão #6 dentro do escopo delimitado; ela encontrou duas lacunas obrigatórias fora dos casos que aquele parecer confirmou. Portanto, **o desenvolvimento como um todo não está aprovado até corrigir ou decidir formalmente os itens abaixo**.

### G1 — aceite do aviso de privacidade não é registrado para pacientes

- **Requisito:** SDD1 §8.2, registrar a ciência do aviso de privacidade. **Gravidade:** P2, média. **Arquivo/linhas:** `frontend-react/src/pages/RegisterPage.jsx:45-47`; `app/services/auth_service.py:105`.
- **Comportamento:** o formulário só envia `privacy_notice_accepted` quando `role === "doctor"`; o serviço só preenche `privacy_notice_accepted_at` para médicos. O formulário de paciente não persiste a ciência.
- **Impacto:** o registro de aceite fica ausente para contas de paciente, apesar do requisito geral de cadastro.
- **Correção esperada:** enviar, validar e registrar a ciência também para pacientes, sem tratá-la como consentimento genérico.

### G2 — sinalizador de conversa atravessa ciclos de reassociação

- **Requisito:** SDD2 §10 e CSCW-CA-10; reassociação não restaura contexto anterior. **Gravidade:** P2, média. **Arquivo/linhas:** `app/api/routes.py:729-739`.
- **Comportamento:** `has_investigation` filtra por paciente e indicador e, no contexto médico, por `doctor_id`, mas não pelo `association_id` ativo. Se o mesmo médico for reassociado, uma investigação do ciclo revogado pode fazer o endpoint retornar `has_investigation: true`.
- **Impacto:** o médico descobre a existência e o dia de uma conversa do ciclo anterior, embora continue sem acesso ao conteúdo.
- **Correção esperada:** filtrar pela associação ACTIVE atual e adicionar regressão cobrindo a flag antes/depois da reassociação.

A auditoria adicional reportou pytest com 64 aprovados e os seis validadores aprovados; não repetiu o E2E, cujo resultado da revisão #6 permanece 79 aprovados, 1 skip e nenhuma falha. O agente informou que a execução pytest reconstruiu `data/integration.db`; `data/myglico.db` não foi tocado. A divergência das credenciais demo públicas permanece registrada como não bloqueante por instrução explícita anterior do usuário. O agente adicional não localizou `REVISAO6-ESCOPO.md` no worktree no momento da sua leitura; o escopo havia sido lido na revisão #6 anterior.

## Verificações e achados

### P1 — fuso horário, migração e classificação UCI: resolvido

**Requisito:** CSCW-CA-26, AUT-CA-21, SDD1 §6.5 e SDD2 §9.3. **Gravidade original:** crítica. **Status:** corrigido e aprovado.

- `app/services/manual_entry.py:34-39` interpreta o `datetime-local` sem offset no fuso do paciente e grava UTC ingênuo. `app/services/uci_importer.py:449` aplica a mesma conversão às horas locais do diário. A leitura converte o UTC para o fuso do paciente (`app/api/routes.py:985`, `app/services/analytics.py:125-126`, `app/services/reports.py:444`). A busca por intervalos também usa limites UTC do dia local (`app/services/analytics.py:259-260`). A busca por escritores de `measured_at` não encontrou outro caminho de produção que grave hora local sem conversão; inserções diretas restantes são fixtures/testes e a migração.
- A migration `alembic/versions/20261008_0011_normalize_measurement_timestamps_to_utc.py:24-42` percorre os registros legados por lotes e converte conforme `patients.timezone`. Fiz um upgrade real: usei `git archive 6a70133`, apliquei o schema desse código, importei os dados UCI para um SQLite temporário e então apliquei a cadeia atual até 0011 e recalculei a análise. O banco descartável `data/myglico.db` não foi tocado.
- Repeti a classificação UCI completa (29.297 eventos brutos, 13.531 leituras de glicose, 70 pacientes). Referência `6a70133`: 3.860 buckets diários e 222 dias atípicos. Código atual importado do zero: **mesmos 3.860 buckets e 222 dias**. Upgrade real de `6a70133` pela 0011, seguido de recálculo: **mesmos 3.860 buckets e 222 dias**. Comparei por código externo de paciente e data: zero dias atípicos adicionados/removidos e zero divergência nos buckets (contagem de leituras, média, flag atípica e cluster). Os 18 deslocamentos reportados na revisão #5 não se reproduziram. Correção esperada (atendida): converter no ponto de entrada, migrar uma vez os horários legados e sempre apresentar no fuso do paciente.
- A sonda E2E preencheu o formulário real com **00:30 e 23:30**; a consulta da API devolveu ambos no dia e horário locais esperados (`frontend-react/e2e/specs/09-atypical-popup-filters.spec.mjs:210-225`). Isso confirma CSCW-CA-26 e AUT-CA-21.
- Conferi as regras históricas de `America/Sao_Paulo` em 1990/91. A zona identifica lacunas no início do horário de verão; por exemplo, `1990-10-21 00:30` não existiu e o helper atual a interpreta como `03:30 UTC`, que volta como `01:30` local. Nenhuma leitura UCI estava na hora 00 nas datas de transição consultadas, e a comparação completa confirma que isso não alterou a classificação. **Observação de robustez, baixa e não bloqueante:** entradas manuais históricas em horas locais inexistentes são aceitas e normalizadas silenciosamente; seria melhor rejeitá-las e documentar a escolha `fold` para horas ambíguas. Correção esperada: validar lacunas na entrada e auditar casos legados impossíveis antes de converter. Não há evidência de ocorrência nos dados UCI avaliados nem impacto nos critérios obrigatórios desta rodada.

### P2 — escopo da proveniência: resolvido

**Requisito:** CSCW-CA-17, AUT-CA-15, CSCW-CA-32 e SDD2 §§3, 10.2 e 10.6. **Gravidade original:** alta. **Status:** corrigido e aprovado.

- `app/api/routes.py:745-780` exige acesso ao paciente; para médico, restringe vínculos e investigações ao vínculo ACTIVE atual (`:754-763`) antes de listar os eventos (`:767-775`).
- Executei os casos de `tests/integration/test_lote4_timezone_and_provenance.py`: com dois médicos, A não recebeu eventos de associação/investigação de B; B recebeu o próprio histórico; o paciente recebeu o histórico completo dos dois. Após revogar e reassociar o mesmo médico, a resposta médica não continha eventos nem investigação do ciclo anterior; o paciente manteve o histórico anterior. A suíte e `test_cscw_ca_32_revoked_doctor_cannot_use_provenance_or_audit_endpoints` confirmaram que médico revogado recebe negação sem conteúdo; as fronteiras para outro paciente também passaram.
- **Metadata:** a filtragem de eventos por médico/ciclo está correta, sem evidência de metadados de B ou do ciclo revogado no retorno de A. A rota ainda serializa `metadata_json` integralmente (`routes.py:779`), que pode incluir IDs internos como `patient_id`, `doctor_id` e `daily_indicator_id`, datas e versões. Esses valores pertencem ao próprio contexto autorizado e não constituíram vazamento entre médicos nesta verificação; ainda assim, são mais detalhe interno do que a UI precisa. Correção esperada para a observação: projetar apenas os campos de auditoria necessários em cada tipo de evento. **Observação baixa, não bloqueante:** preferir uma projeção de campos permitidos por tipo de evento. Correção esperada: substituir o repasse integral de metadata por whitelist e manter auditoria técnica em endpoint de privilégio específico.

### A15 — afirmação do README sobre 0003–0006: resolvido

**Requisito:** A15 / histórico imutável de migrations. **Gravidade anterior:** parcial. **Status:** aprovado.

`README.md:122-129` agora afirma explicitamente que 0003–0006 foram preservadas como escritas, mas parte do DDL deriva dos modelos ORM em tempo de execução e, portanto, os resultados não são snapshots congelados. Também orienta novas migrations a usar DDL explícita e não reescrever revisões aplicadas. Isso corresponde ao código histórico e não cria uma promessa incorreta de reprodutibilidade. Correção esperada (atendida): explicitar a limitação e exigir DDL explícita nas novas migrations, preservando as revisões já aplicadas. Não alterei as migrations antigas.

## Regressões e execução independente

- `python -m pytest tests -q -rxXs`: **64 passed**, sem falhas ou skips (um aviso de `joblib` sobre detecção de núcleos físicos no Windows).
- Seis `scripts/validate_*.py`, com chaves hexadecimais aleatórias geradas só no processo e nunca impressas ou gravadas: **6/6 passaram**.
- `cd frontend-react && MYGLICO_E2E_BACKEND_PORT=8231 MYGLICO_E2E_FRONTEND_PORT=8230 npx playwright test`: backend e Vite reais, SQLite descartável, **79 passed, 1 skipped, 0 failed**. O skip é o cenário secundário de falha de publicação de CSCW-CA-29, coberto pelo teste de integração da outbox. Após a execução, as portas 8230/8231 estavam livres.

## Matriz de aceite

Recontei as linhas dos critérios: **68 no total**, 66 Aprovado e 2 Não aplicáveis (AUT-CA-19 e CSCW-CA-33). Confirmei como aprovados os quatro itens pendentes da revisão #5: **CSCW-CA-26, AUT-CA-21, AUT-CA-15 e CSCW-CA-17**. A suíte completa E2E cobre os grupos funcionais AUT-CA-01..23 e CSCW-CA-01..45; a suíte pytest cobre transações, criptografia, autorização, concorrência, proveniência e outbox. Para critérios sem mudança desde a #5, conferi a execução integral e amostras cruzadas de landing/cadastro, busca/vínculo/revogação, investigação/mensagens, notificações, filtros, idiomas/PDF e limites entre pacientes e médicos. CSCW-CA-29 mantém a evidência de integração porque seu caso de falha injetada não é exercitável pelo navegador.

## Observações não bloqueantes registradas

- **O7 — sem teto por IP:** `app/core/rate_limit.py:17-26` usa baldes por IP+identidade e por identidade; não há balde independente por IP. Uma origem pode tentar várias identidades distintas sem teto agregado por origem. Impacto: menor contenção de password spraying distribuído por contas. Correção futura esperada: limite por IP com política que evite bloquear usuários atrás de NAT, ou rate limiter compartilhado.
- **O8 — consumidor da outbox na requisição:** `app/main.py:43-52` chama `drain_notification_outbox` depois de toda resposta `/api/*`. Impacto possível: trabalho de entrega e disputa de banco no caminho da requisição; o try/except preserva a resposta já produzida. Correção futura esperada: mover o consumo para worker ou execução em background com orçamento limitado, mantendo retry/idempotência.
- **Credenciais demo públicas:** README e configuração documentam `qwerty` para contas `*.demo.myglico.invalid`. Isso diverge de SDD1 §8.1, mas é uma decisão explícita para demonstração de dataset público e foi solicitado como não bloqueante nesta revisão. Manter a restrição a contas públicas de demonstração; não reutilizar em contas reais.

---

## Registro histórico — revisão #5

### Revisão #5 (registro histórico)

**Revisor:** o mesmo worker Claude independente das revisões #1 a #4. Não edita código: só lê, executa e escreve este parecer.

**Objeto:**
- Branch `felipe-cale/auth-vinculos-cscw`. O estado aprovado na revisão #4 já está commitado em `6a70133 feat: add account auth and doctor-patient linking with CSCW collaboration`.
- Esta revisão cobre o **diff do worktree sobre `6a70133`**, inspecionado entre **2026-10-08 15:27 e 15:45**: 39 arquivos rastreados (+1113/−203) e 8 novos. Os novos são as migrações 0008–0010, `app/core/patient_time.py`, `app/services/notification_outbox.py`, `InvestigationOrigin.jsx` e dois arquivos de teste de integração.

**Escopo:** o dono do produto passou a tratar como bloqueantes as pendências da revisão #4: A15, O2, O3, AUT-CA-21, R2, R3, CSCW-CA-26/O4 e CSCW-CA-22. Também verifico a reclassificação do CSCW-CA-29 feita pelo coordenador e as observações O5/O6 que registrei na #4.

## Veredito #5

# **REPROVADO — não fazer o commit deste diff ainda**

A maior parte das correções é real e verifiquei cada uma: O2, O3, R3, B1, B4/CSCW-CA-29, B7, CSCW-CA-22, O5 e O6.

Mas a rodada **introduziu duas regressões**, ambas confirmadas por execução, e nenhuma é pega pela suíte:

1. **P1, crítico: deslocamento de −3h em todos os horários reais (CSCW-CA-26 e AUT-CA-21).**
2. **P2, alto: o endpoint de proveniência vaza metadados das conversas e do vínculo de outro médico (SDD2 §3, §10.2, §10.6).**

Por isso, a afirmação de **66 Aprovado / 0 Parcial** da `MATRIZ-ACEITE.md` **não se sustenta**.

O commit `6a70133`, aprovado na revisão #4, continua válido. O problema está só no diff atual.

## Evidência de execução (revisão #5)

| Verificação | Resultado |
| --- | --- |
| 6 validadores (`scripts/validate_*.py`, SQLite isolado, chaves efêmeras) | **6/6 PASS**. |
| `python -m pytest tests -q -rxXs` | **60 passed, 0 skipped, 0 xfail** (67 s). |
| Suíte E2E completa (`npx playwright test`, backend e Vite reais) | **79 passed, 1 skipped** (CSCW-CA-29 secundário, `test.skip` documentado), **0 falhas** (7,8 min). |
| Caminho de upgrade real: banco criado pelo código do commit `6a70133` (`git archive`) até 0007, com um paciente legado; depois `alembic upgrade head` com o código atual | 0008 → 0010 aplicadas. **Schema idêntico** ao de um banco criado do zero (colunas e índices). O paciente legado ficou com `short_id`/`name_encrypted` não nulos e `timezone=America/Sao_Paulo`. |
| Upgrade do banco UCI real da revisão #2 (em 0007) até 0010 e navegação | Ok. Ver O3/O5/O6 abaixo. |
| Importação UCI real do zero com o código atual, comparada com a importação da revisão #2 | Ver **P1**. |
| Sondas de API (`TestClient`, SQLite novo) | Ver P1, P2, R3, B7 e O2. |

## Regressões bloqueantes

### P1 — Crítico: horários reais deslocados em −3h; dias mudam perto da meia-noite; classificação UCI mudou

**Requisitos afetados:** CSCW-CA-26 ("leitura próxima da meia-noite pertence ao dia correto"), AUT-CA-21 ("dias atípicos preservam os resultados anteriores"), SDD2 §9.3 e SDD1 §6.5.

**Causa:**
- `app/core/patient_time.py` e os novos usos em `reports.py`, `analytics.py` e `manual_entry.py` passaram a interpretar **todo `measured_at` armazenado como UTC** e a convertê-lo para `patients.timezone`.
- Nenhum caminho real de entrada grava UTC:
  - o formulário manual (`ManualGlucoseEntryForm.jsx:19,56,83`) envia o valor de `datetime-local`, que é hora de parede **sem offset**, e o backend grava exatamente esse valor;
  - o importador UCI grava a hora local do diário;
  - não há migração convertendo as linhas existentes.

**Evidência:**
- Sonda via API, fazendo exatamente o que o formulário envia:
  - `POST measured_at="2026-10-08T00:30"` → armazenado `2026-10-08 00:30` → exibido no detalhe como **`2026-10-07 21:30`**;
  - `"2026-10-08T12:00"` → exibido **`09:00`**.
- Importação UCI real (29 297 registros), código atual contra o código da revisão #2: o mesmo número de dias atípicos (222), mas **18 dias atípicos mudaram de data e 18 surgiram em outras datas**, por exemplo `uci-08 1990-08-21 → 1990-08-04` e `uci-09 1990-05-01 → 1990-04-30`. Um bucket diário também desapareceu (3860 → 3859).

**Por que os testes passam:**
- `frontend-react/e2e/scripts/seed_atypical_days.py` foi alterado para converter a hora de parede em UTC antes de gravar ("so this fixture tests the same boundary contract as real API records"). Os registros reais da API, porém, **não** são convertidos.
- O teste de AUT-CA-21 compara apenas antes e depois da recriptografia, e não antes e depois da mudança de fuso.

**Correção esperada:** escolher uma convenção única e aplicá-la de ponta a ponta. Uma das duas:
- (a) tratar o `measured_at` armazenado como hora de parede local do paciente e não converter na leitura;
- (b) converter para UTC **na entrada**: o formulário manual interpreta a hora no fuso do paciente, e o importador UCI usa o fuso do dataset. Isso exige uma migração de dados idempotente para as linhas existentes, e o fixture do E2E deve usar o mesmo caminho da API real.

Em qualquer caso, incluir:
- um E2E que registre uma leitura pelo formulário real às 00:30 e às 23:30 e confira data e hora exibidas;
- um teste que compare a classificação UCI antes e depois.

### P2 — Alto: `/api/patients/{id}/provenance` expõe a um médico os metadados do vínculo e da investigação de outro médico

**Requisitos afetados:**
- SDD2 §3 ("Ser médico associado não concede acesso às conversas de outros médicos");
- §7.3 ("Não expor conversas de outro médico nesse indicador");
- §10.2 ("Metadados que identifiquem contextos clínicos precisam das mesmas restrições de acesso");
- §10.6 ("consulta técnica de auditoria usa permissão específica, sem conceder acesso geral a médicos");
- AUT-CA-15 e CSCW-CA-17 (isolamento).

**Causa:** a correção de R2 (`routes.py`, `api_patient_provenance`) inclui eventos de **todos** os `patient_doctor_links` e de **todas** as `investigations` do paciente. Basta o solicitante passar em `_require_patient_access`, que aceita qualquer médico com vínculo ACTIVE. O `metadata_json` sai completo.

**Evidência (sonda):**
- Paciente P vinculado aos médicos A e B. P abre uma investigação com B.
- `GET /api/investigations/{id}` feito por A → **404** (correto).
- `GET /api/patients/P/provenance` feito por A → devolve **`InvestigationOpened`, `AssociationRequested` e `AssociationConfirmed` de B**, com `doctor_id` e `association_id` de B e o `atypical_day_event_id` da conversa.

**Correção esperada:**
- Para o contexto Médico, limitar os eventos a vínculos e investigações com `doctor_id == principal.doctor.id`, do ciclo autorizado.
- Para o Paciente, manter o histórico completo.
- Reduzir o `metadata` exposto ao mínimo necessário.
- Adicionar um teste de integração com dois médicos.

## Situação dos itens pedidos

| Item | Situação | Evidência |
| --- | --- | --- |
| **A15** (congelar DDL; NOT NULL; VACUUM) | **Parcial** | NOT NULL ok (0010, conferido no upgrade real). `VACUUM` documentado (README:117-121). As novas 0007–0010 têm DDL explícita e idempotente. **Mas 0003–0006 continuam com `Model.__table__.create`**, ou seja, derivam a DDL dos modelos vivos, e o README:122-124 diz que elas "permanecem inalteradas para reprodutibilidade", o que não é exato. Hoje o schema resultante é idêntico (verificado), mas cada coluna futura obriga a migração nova a se proteger com `inspect` (como 0008/0009 fizeram). Correção: congelar 0003–0006 com a DDL equivalente à que o commit `6a70133` produz, ou corrigir a afirmação no README e registrar a regra. |
| **O2** (rate limit e NAT) | **Corrigido**, com nota | Baldes por (IP, identidade) e por identidade (`rate_limit.py`). Sonda: 11 falhas na mesma conta → 429; login válido de **outra** conta no mesmo IP → **200**. Nota (O7): não há mais teto por IP; 40 e-mails distintos a partir de um IP → todos 401, sem 429. Ou seja, *password spraying* a partir de um IP não é limitado. É um tradeoff aceitável para o MVP, desde que fique registrado. |
| **O3** (convites consolidados) | **Corrigido** | Navegador (UCI `patient1`): **1** banner, "Identificamos 7 dias atípicos nas suas leituras, entre 25 de abr. de 1991 e 22 de ago. de 1991…", com um único "Agora não". Dispensar e recarregar → 0 banners. O endpoint agrupa por paciente e status (`batch_id`, `indicator_ids`, `dates`); `POST /api/atypical-day-prompts/defer` em lote. |
| **AUT-CA-21** (baseline) | **Reprovado** (P1) | O teste novo cobre apenas a recriptografia. Na base UCI real, a mudança de fuso alterou 18 dias atípicos. |
| **R2** (proveniência e dedupe) | **Dedupe corrigido; endpoint com regressão P2** | `AtypicalDayDetailViewed` deduplicado por ator e dia local. O histórico agora inclui vínculos, investigações e convites, mas sem o filtro por médico (P2). |
| **R3** (CRM+UF+privacidade) | **Corrigido** | API: médico sem CRM → 422; sem `privacy_notice_accepted` → 422; com `false` → 422; paciente sem o campo → 201. `user_accounts.privacy_notice_accepted_at` gravado para o médico (migração 0009). |
| **CSCW-CA-26 / O4** (fuso do paciente) | **Reprovado** (P1) | O agrupamento por fuso existe, mas parte de uma premissa de armazenamento em UTC que nenhum caminho de entrada cumpre. |
| **CSCW-CA-22** (origem / "classificação anterior") | **Corrigido** | `origin.is_current_classification` na API; `InvestigationOrigin.jsx:22-25` mostra o selo "classificação anterior". O teste `test_cscw_ca_22_recompute_that_drops_the_flag…` passa (true → false após uma execução vazia e após recálculo). E2E grupo 06 verde. |
| **CSCW-CA-29** (reclassificado pelo coordenador) | **Aprovado — a reclassificação procede** | `drain_notification_outbox` existe (`app/services/notification_outbox.py`, arquivo novo nesta rodada, e não "desde o Lote 1" do commit) e é chamado no middleware `/api/*` (`main.py`). O teste força a falha (`PENDING`, `attempts=1`, `last_error` só com o nome da classe), refaz (`DELIVERED`, `attempts=2`) e confirma que não há notificação duplicada. **Notas (O8):** (i) a "entrega" é só uma confirmação de que o destinatário existe, porque a caixa de entrada lê a tabela `notifications` diretamente, independentemente do estado da outbox; (ii) o consumo roda de forma síncrona em **toda** requisição `/api/*`, com uma transação de escrita a mais, o que pode gerar contenção (`database is locked`) em SQLite sob carga. Recomendo mover para um job ou worker. |
| **B1** (`no-store`) | **Corrigido** | `main.py` inclui `/api/investigations`, `/api/notifications` e `/api/doctor-links`. |
| **B7** (cancelar sem versão) | **Corrigido** | Sem corpo → 422. |
| **O5** (limpar após reload) | **Corrigido** | Navegador: período 01/06–31/08, aplicar 25/04 → ampliado com aviso; **reload** → aviso continua; limpar → `start_date=1991-06-01&end_date=1991-08-31` restaurado (`sessionStorage`, `PatientDetailPage.jsx:214-231`). |
| **O6** (rótulo "Janela padrão") | **Corrigido** | Período padrão → "Janela padrão de 30 dias…"; período 01/06–31/08 → "**Período personalizado de 92 dias escolhido no filtro.**" |

## Matriz (`MATRIZ-ACEITE.md`)

O arquivo afirma **66 Aprovado / 0 Reprovado / 0 Parcial / 2 Não aplicável** (recontei a coluna Status). Com base no que verifiquei, o correto é:

| Critério | Matriz | Revisor #5 | Motivo |
| --- | --- | --- | --- |
| CSCW-CA-26 | Aprovado | **Reprovado** | P1: a evidência citada ("Fixture converte hora de parede em UTC") é justamente o que mascara a regressão. |
| AUT-CA-21 | Aprovado | **Reprovado** | P1: a classificação UCI real mudou (18 dias). |
| AUT-CA-15 / CSCW-CA-17 | Aprovado | **Parcial** | P2: o conteúdo da conversa está isolado, mas os metadados da conversa e do vínculo de outro médico vazam pela proveniência. |
| CSCW-CA-32 | Aprovado | Aprovado | Médico revogado continua recebendo 404 na proveniência (`_require_patient_access`). |
| Demais | Aprovado / N/A | Confere | A suíte completa, o pytest e os validadores passam. |

**Totais do revisor: 62 Aprovado · 2 Reprovado · 2 Parcial · 2 Não aplicável.**

## Para liberar o commit (revisão #6)

1. **P1**: convenção única de fuso aplicada à entrada, ao armazenamento e à leitura, com migração de dados se for a opção (b). E2E com o formulário real perto da meia-noite. Teste de não regressão da classificação UCI antes e depois.
2. **P2**: proveniência filtrada pelo escopo do médico, com teste de dois médicos.
3. **A15**: congelar 0003–0006 ou corrigir a afirmação do README.
4. Atualizar a matriz: CSCW-CA-26, AUT-CA-21, AUT-CA-15 e CSCW-CA-17.

**Recomendado, sem bloquear:** registrar O7 (sem teto por IP), O8 (consumidor da outbox na requisição) e a divergência já aceita das credenciais demo públicas.

---

# Registro: revisão #4

**Revisor:** o mesmo worker Claude independente das revisões #1 a #3. Não edita código: só lê, executa e escreve este parecer.
**Objeto:** diff do worktree `C:\Users\felip\orca\workspaces\myglico\doliolid` (branch `felipe-cale/feature-orca-prompt-features`, **sem commit**), inspecionado entre **2026-10-07 10:00 e 10:25 (horário local)**. Base: `0920365`.

## Veredito final

**APROVADO** (revisão #4, sobre o estado hoje commitado em `6a70133`)

Nenhum critério obrigatório está reprovado. Os N2 e N3 da revisão #3 foram corrigidos, e verifiquei isso por execução, sem me apoiar nos relatos. A suíte completa, que ninguém tinha rodado depois de N2/N3, passa sem falhas.

O estado final é **62 Aprovado / 0 Reprovado / 4 Parcial / 2 Não aplicável**, nos 68 critérios. Os parciais e não aplicáveis estão justificados abaixo, e as pendências que ficaram não bloqueiam a entrega.

## Evidência de execução da revisão #4

| Verificação | Resultado |
| --- | --- |
| Suíte E2E completa: `npx playwright test` (backend e Vite reais, SQLite descartável, saída no scratchpad) | **76 cenários: 75 passed, 1 skipped (CSCW-CA-29/B4), 0 falhas, 0 `test.fail`** (8,4 min). |
| Grupo 09 (popup e filtros) dentro da execução completa | **10/10**, incluindo o cenário novo "CSCW-CA-23/25 (N2, N3)". |
| `grep test.fail\|test.fixme\|.only(` nos specs | Só o `test.skip` documentado do B4. |
| Cenário novo (N2/N3), lido linha a linha | Testa o que deveria: período ativo termina na véspera do último dia atípico. Verifica popup = card < total, texto de escopo (`atypical-scope`), "Ver todo o histórico" = total, aplicar o dia de fora amplia só o `end_date` com o aviso `period-adjusted`, resumo `period-summary` sem "- -" e sem "Janela padrão", e limpar restaura o `end_date` original e remove o aviso. |
| pytest completo | **52 passed, 1 skipped (B4)**. |
| `MATRIZ-ACEITE.md` | Recontagem pela coluna Status: **62/0/4/2**. Os não aprovados são exatamente AUT-CA-19 e CSCW-CA-33 (N/A) e AUT-CA-21, CSCW-CA-22, 26 e 29 (Parcial). O cabeçalho (75 passed/1 skip, grupo 09 10/10) bate com a minha execução. CSCW-CA-23/25 têm a evidência de N2/N3. |

**Navegador real** (Vite :8020 → backend :8022 com cópia do banco UCI real; scripts ad hoc removidos e servidores encerrados):

| Passo (`patient1`, pt-BR, período padrão `1991-08-05..09-03`) | Resultado |
| --- | --- |
| Card | "Dias atípicos **1**". |
| Popup | **1 dia**, com "1 dias atípicos no período exibido no detalhamento (5 de ago. de 1991 a 3 de set. de 1991), o mesmo escopo do card." **N2 corrigido.** |
| "Ver todo o histórico" | **7 dias**, com "7 dias atípicos em todo o histórico do paciente." |
| Selecionar 25/04/1991 (fora do período) e aplicar | URL `start_date=1991-04-25&end_date=1991-09-03&dates=1991-04-25`. Aviso: "Período ajustado para incluir o(s) dia(s) selecionado(s) 25/04/1991: de 05/08/1991 – 03/09/1991 para 25/04/1991 – 03/09/1991…". Resumo: "Dias selecionados (1) 25/04/1991 … Período de referência: 25/04/1991 a 03/09/1991". **N3 corrigido.** |
| Esc no popup | O foco volta ao botão "Ver dias atípicos". |
| en-US (`patient3`) | Texto de escopo traduzido. Dia dentro do período: nenhum aviso de ajuste. Limpar restaura o período. |

Observação nova encontrada nesta checagem: ver O5 abaixo. Não é bloqueante.

## Jornada da revisão (#1 → #4)

| Revisão | Veredito | O que motivou | Principais correções confirmadas na rodada seguinte |
| --- | --- | --- | --- |
| **#1** (~06:20) | REPROVADO | 9 critérios reprovados; 16 achados (A1–A16) e 10 observações (B1–B10); suíte E2E com 61/75 `fixme`, 41/41 testes de integração em `skip`, matriz vazia. | — |
| **#2** (~09:30) | REPROVADO (1 critério) | CSCW-CA-25: aplicar dias apagava o período e limpar voltava à janela padrão (R1); matriz desatualizada (R4). | A1 (popup vazio para UCI), A2 (dias exatos), A4 (senha demo não é mais redefinida; domínio `.invalid`), A5 (limite de tentativas 429), A6 (`notes` cifrado e exceção documentada), A7 ("Agora não" persistente), A8 ("Meus pacientes" do médico), A9 (notificação consolidada), A11 (não lidas por conversa, motivo de encerramento), A14 (Docker e README), B2, B5, B6, N1, NEW-1. A3 passou a não aplicável (papel único). |
| **#3** (~09:55) | REPROVADO (achado novo) | N2: card (1) e popup (7) com escopos diferentes sem explicação (CSCW-CA-23). N3: dia fora do período deixava o resumo em "- - -/Janela padrão" sem aviso. | R1 e R4 corrigidos; suíte completa 74/1 skip. |
| **#4** (agora) | **APROVADO** | — | N2 e N3 corrigidos; suíte completa 75 passed/1 skip; matriz consistente. |

## Itens Parciais e Não aplicáveis (aceitos)

| Critério | Situação | Motivo |
| --- | --- | --- |
| AUT-CA-19, CSCW-CA-33 | Não aplicável | Decisão do dono do produto: cada `UserAccount` tem um único papel (Patient **ou** Doctor). O servidor impõe a regra (409 ao registrar o segundo papel; sessão de conta com os dois perfis é invalidada, verificado na revisão #2). |
| AUT-CA-21 | Parcial | Recálculos dão resultados idênticos e o NEW-1 está corrigido, mas não existe baseline anterior à proteção para comparar. |
| CSCW-CA-22 | Parcial | O backend preserva a origem histórica da investigação após recálculo; a UI não sinaliza "classificação anterior". |
| CSCW-CA-26 | Parcial | A leitura às 23:59 fica no próprio dia, mas as datas são ingênuas (data de parede), sem fuso por paciente. |
| CSCW-CA-29 | Parcial | Evento, notificação e outbox são gravados de forma durável e atômica, mas a outbox não tem consumidor nem retry (B4). |

## Pendências recomendadas (não bloqueantes) para o backlog futuro

| ID | Pendência | Referência |
| --- | --- | --- |
| **A15** | Migrações 0003–0006 usam `Model.__table__.create` (DDL não congelada); `patients.name_encrypted`/`short_id` ficam `NULL`-áveis no banco; `VACUUM` pós-migração só documentado. | SDD1 §11 |
| **B1** | `Cache-Control: no-store` ausente em `/api/investigations*`, `/api/notifications*` e `/api/doctor-links` (conteúdo clínico decifrado). | SDD1 §8.4, SDD2 §5.3 |
| **B3** | No encerramento por revogação, `closed_by` grava o humano que revogou, e não o sistema (o evento está correto). | SDD2 §5.4 |
| **B4** | `NotificationOutbox` sem consumidor nem retry (linhas ficam `PENDING`). A entrega funciona por polling da tabela. | SDD2 §10.4, CSCW-CA-29 |
| **B7** | `POST /api/doctor-links/{id}/cancel` aceita requisição sem `version` (contorna o controle otimista). | SDD2 §12 |
| **R2** | `GET /api/patients/{id}/provenance` só devolve eventos de visualização e filtro, sem o histórico de vínculos e investigações. `AtypicalDayDetailViewed` é gravado a cada abertura do popup (sem deduplicação; GET com efeito de escrita). | SDD2 §10.3, §10.6 |
| **R3** | CRM/UF obrigatórios e ciência do aviso de privacidade existem só no frontend. A API aceita médico sem CRM/UF e não registra a ciência. | SDD1 §5.3, §8.2 |
| **O2** | O limitador de tentativas também conta por IP, então 10 falhas bloqueiam por 60 s todas as contas daquele IP (NAT). É em memória por processo, sem compartilhamento entre workers (documentado). | SDD1 §8.3 |
| **O3** | Os convites de dia atípico aparecem como um banner por dia (até 9 por paciente UCI). A notificação já é consolidada. | SDD2 §7.6 |
| **O4** | Sem fuso horário por paciente (relacionado a CSCW-CA-26). | SDD2 §9.3 |
| **O5** (novo) | Depois de um **reload** com um período ampliado por N3, o período original (guardado só em memória, `preservedRangeRef`) se perde. "Limpar seleção de dias" mantém o período ampliado e o aviso de ajuste não reaparece. Sem reload, o fluxo está correto (E2E e navegador). O estado continua único e visível na URL e no resumo. | SDD2 §9.3 |
| **O6** (anterior à entrega) | O resumo "Período analisado" sempre mostra o texto "Janela padrão de 30 dias…", mesmo com período customizado. Já era assim em `HEAD` (`PatientDetailPage.jsx`); só deixa de aparecer quando há `dates` ativo. | cosmético |
| Divergência aceita | Credenciais públicas da demonstração UCI (`patientN@demo.myglico.invalid` / `doctor@demo.myglico.invalid`, senha `qwerty`) versionadas e documentadas no README e em `CRYPTO_CONFIGURATION.md`, por decisão do dono do produto, restritas ao dataset público e ao modo `--provision-demo-accounts`. Os SDDs ainda dizem "não versionar credenciais": recomenda-se registrar a exceção no próprio SDD. | SDD1 §8.1, §10.1 |
| Divergência aceita | Glicemia, `measured_at` e `context_label` ficam legíveis no banco por exigência do algoritmo, com exceção documentada em `CRYPTO_CONFIGURATION.md` (SDD1 §6.5). Não afirmar proteção integral nem conformidade LGPD por causa da criptografia. | SDD1 §6.5, §15 |

Esta aprovação vale para o diff do worktree no estado inspecionado. Qualquer alteração posterior ao código exige pelo menos a reexecução da suíte E2E completa, do pytest e dos validadores antes do commit.

---

# Registro: revisão #3

**Revisor:** o mesmo worker Claude independente das revisões #1 e #2, que não edita código.
**Objeto:** diff do worktree `doliolid` (sem commit), inspecionado entre **2026-10-07 09:30 e 09:55**.
- `git diff --stat`: 23 arquivos rastreados (+2989/−257).
- 33 entradas não rastreadas.

**Histórico:**
- Revisão #1 (~06:20): **REPROVADO**, com 9 critérios reprovados e os achados A1–A16 e B1–B10.
- Revisão #2 (~09:30, mantida integralmente abaixo como registro): **REPROVADO** só pelo CSCW-CA-25 (R1). A matriz estava desatualizada (R4).
- Revisão #3: verifica R1 e R4, conforme o BACKLOG ("R1FIX").

## Veredito #3

**REPROVADO** (um problema novo no CSCW-CA-23; R1 e R4 foram corrigidos — resolvido na revisão #4)

**Corrigido e verificado nesta rodada:**
- **R1 / CSCW-CA-25: corrigido.**
  - `npx playwright test e2e/specs/09-atypical-popup-filters.spec.mjs` deu **9/9 passed** (3,5 min). `grep test.fail|test.fixme` em todos os specs não encontrou nada.
  - Li o teste novo. Ele compara com o período ativo, que o backend normaliza ao fim dos dados, e confere a URL e o campo de data. Não foi enfraquecido.
  - Navegador real com dados UCI (`patient1`), período `1991-04-21..1991-09-03`:
    - aplicar 2 dias → `?start_date=1991-04-21&end_date=1991-09-03&dates=1991-07-26,1991-08-22`, com 2 chips e o campo de data em 1991-04-21;
    - recarregar mantém o mesmo estado;
    - "Limpar seleção de dias" → `?start_date=1991-04-21&end_date=1991-09-03` (período restaurado, não a janela padrão);
    - na janela padrão, aplicar e limpar também restaura `1991-08-05..1991-09-03`.
  - Código: `PatientDetailPage.jsx:271-301,545-579` (`preservedRangeRef`; o pedido com `dates` envia só os dias; a URL mantém o período). A solução faz sentido.
- **Suíte E2E completa reexecutada por mim** depois do R1 (ninguém tinha feito isso): **74 passed, 1 skipped (B4), 0 falhas, 0 `test.fail`** (7,7 min). Não houve regressão nos outros grupos.
- **R4 / matriz: corrigido.** Recontei pela coluna Status: **62 Aprovado / 0 Reprovado / 4 Parcial / 2 Não aplicável** (68), exatamente o relatado. CSCW-CA-23, CSCW-CA-25 e AUT-CA-21 estão atualizados e o cabeçalho reflete as execuções.

**Problema novo que impede a aprovação. Não testei esse cenário na revisão #2, que só comparou o período completo (7 = 7).**

**N2 — CSCW-CA-23: no período padrão, o card e o popup mostram escopos diferentes e nada explica a diferença** (defeito; SDD2 §9.1: "Se já houver filtros de período no detalhamento, card e popup devem usar o mesmo escopo. A contagem deve ser coerente com a lista ou explicar quando representa todo o histórico"; CSCW-CA-23: "Popup com lista correspondente à contagem/escopo explicado").
- Navegador (UCI, `patient1`, detalhamento aberto sem parâmetros → janela padrão `1991-08-05..1991-09-03`):
  - o card mostra **"Dias atípicos 1"**;
  - o popup lista **7 dias**, de 25/04 a 22/08/1991;
  - os campos "Data inicial/Data final" do popup ficam vazios e não há texto dizendo que a lista é do histórico inteiro.
- Causa: `AtypicalDaysPopup.jsx:22-23,34-35` inicia `rangeStart`/`rangeEnd` vazios e não recebe o período ativo de `PatientDetailPage` (`<AtypicalDaysPopup>` em `:696-701` só recebe `patientId`, `appliedDates` e os callbacks). Por isso `GET /atypical-days` sai sem período.
- Por que o E2E não pega: o cenário CA-23 abre o detalhe com `RANGE` (`2026-06-01..07-31`), que cobre todos os dias semeados. Não existe cenário com dias atípicos fora do período ativo.
- Correção esperada:
  - passar o período ativo ao popup e usá-lo como filtro inicial, para que o popup e o card contem o mesmo escopo;
  - ou, se o popup mostrar o histórico inteiro, dizer isso com a contagem (por exemplo "7 dias em todo o histórico; 1 no período exibido");
  - acrescentar um cenário E2E com dias fora do período ativo.

**N3 — Dia selecionado fora do período ativo: o estado fica inconsistente e a interface não avisa** (defeito, **médio**; SDD2 §9.3: "Se as datas selecionadas estiverem fora do período global, ajustar explicitamente o período para abranger a seleção, indicando a mudança na interface"; CSCW-CA-25 "indicação visual e estado único").
- Navegador, na janela padrão `1991-08-05..09-03`:
  - selecionar **25/04/1991** no popup e aplicar → URL `?start_date=1991-08-05&end_date=1991-09-03&dates=1991-04-25`;
  - o resumo mostra "Período analisado - - -" com o texto "Janela padrão de 30 dias a partir da data mais recente disponível", o que é incorreto: os dados exibidos são do dia 25/04;
  - não aparece nenhum aviso de ajuste do período.
- Resolver o N2 (popup limitado ao período ativo) praticamente elimina esse caminho. Se o popup permitir escolher fora do período, ajuste o período explicitamente e mostre a mudança, e troque o resumo por "Dias selecionados: …" quando `dates` estiver ativo.

### Para aprovar (revisão #4)
1. **N2**: popup e card com o mesmo escopo, ou escopo do histórico explicitamente indicado, mais o cenário E2E correspondente.
2. **N3**: seleção fora do período ajusta ou indica o período, e o resumo não mostra "- - -" nem "Janela padrão" quando há dias exatos.
3. Reexecutar o spec 09 e atualizar CSCW-CA-23/25 na matriz.

Nada mais bloqueia. Os demais 66 critérios estão no estado que verifiquei na revisão #2 e confirmei pela suíte completa de agora.

### Pendências recomendadas (não bloqueantes), herdadas da revisão #2
- **Parciais:** AUT-CA-21 (sem baseline anterior à proteção), CSCW-CA-22 (a UI não sinaliza "classificação anterior"), CSCW-CA-26 (datas sem fuso por paciente) e CSCW-CA-29 (outbox sem consumidor, B4).
- **Não aplicáveis:** AUT-CA-19 e CSCW-CA-33, pela decisão de papel único por conta (invariante verificada na revisão #2).
- **R2:** o endpoint de proveniência não traz o histórico de vínculos e investigações; `AtypicalDayDetailViewed` é gravado a cada abertura do popup.
- **R3:** CRM/UF obrigatórios e ciência de privacidade só no frontend.
- **B1:** `Cache-Control: no-store` ausente em `/api/investigations*`, `/api/notifications*` e `/api/doctor-links`.
- **B3:** `closed_by` grava o humano no encerramento por revogação.
- **B7:** cancelar sem `version`.
- **A15:** migrações usam `__table__.create`.
- **O2:** limite por IP pode bloquear outras contas atrás de NAT; o limitador é em memória por processo.
- **O3:** um banner de convite por dia.

---

# Registro: revisão #2

**Revisor:** o mesmo worker Claude independente da revisão #1. Continua sem editar código: só leio, executo e escrevo este parecer.
**Objeto:** diff do worktree `C:\Users\felip\orca\workspaces\myglico\doliolid` (branch `felipe-cale/feature-orca-prompt-features`, sem commit), inspecionado entre **2026-10-07 08:45 e 09:30 (horário local)**. Base: `0920365`.
- `git diff --stat`: 23 arquivos rastreados alterados (+2954/−251).
- 33 entradas não rastreadas, incluindo a nova migração `20261007_0007_glucose_notes_encrypted.py` e o novo `app/core/rate_limit.py`.

**Revisão #1** (mesmo arquivo, 2026-10-07 ~06:20): **REPROVADO**, com 16 achados (A1–A16), 10 observações (B1–B10) e 9 critérios reprovados. Este documento a substitui e registra, para cada achado, se foi corrigido.

**Mudança de escopo aceita (decisão do dono do produto, BACKLOG 10:32):** cada `UserAccount` tem um único papel. Por isso o achado A3 sai da lista de defeitos, e **AUT-CA-19 e CSCW-CA-33 passam a "Não aplicável"**. Conferi que o servidor impõe essa regra (ver A3 abaixo).

## Veredito (revisão #2)

**REPROVADO** (por um critério obrigatório; o restante está pronto)

A rodada de correção resolveu quase tudo, e confirmei isso por execução, não pelos relatos.

**Corrigido e verificado:**
- 7 dos 9 critérios antes reprovados: CSCW-CA-23, CSCW-CA-24, CSCW-CA-27, CSCW-CA-37, CSCW-CA-45, AUT-CA-17 e AUT-CA-07.
- Os 2 restantes (AUT-CA-19 e CSCW-CA-33) passaram a "Não aplicável" pela decisão de produto.
- Achados resolvidos: A1, A2, A4, A5, A6, A7, A8, A9, A11, A14, B2, B5 e B6, além de N1 e NEW-1.

**O que impede a aprovação:** **CSCW-CA-25**, que é obrigatório, ainda falha. Reproduzi no navegador real com dados UCI:
- Aplicar a seleção de dias apaga `start_date`/`end_date` da URL.
- "Limpar seleção de dias" volta para a janela padrão (`1991-08-05..1991-09-03`), e não para o período escolhido pelo usuário (`1991-04-21..1991-09-03`).
- A própria suíte E2E mantém esse caso como `test.fail` (A10 residual).

Corrigido esse ponto, a minha recomendação passa a **APROVADO**, desde que os itens "recomendados" abaixo sejam registrados como pendências conhecidas.

## Evidência de execução desta revisão

| Verificação | Comando / método | Resultado |
| --- | --- | --- |
| Validadores | `python scripts/validate_{foundational_security,account_migration,auth_flows,doctor_links,investigations,uci_demo_provisioning}.py`, com chaves efêmeras e SQLite no scratchpad | **6/6 PASS**. As mensagens agora cobrem: papel único, `notes` cifrado, execução global, `dates=` exato, 404 para médico revogado e credenciais preservadas na reimportação. |
| pytest completo | `python -m pytest tests -q -rxXs` | **52 passed, 1 skipped** (B4: outbox sem consumidor), **0 xfail**. O xfail do NEW-1 virou um teste normal que passa. Na revisão #1: 8 passed / 41 skipped. |
| E2E completo | `npx playwright test` (backend e Vite reais, SQLite descartável, saída no scratchpad) | **75 cenários: 73 passaram, 1 falha esperada (`test.fail` CSCW-CA-25 / A10 residual), 1 skip (CSCW-CA-29 / B4)**. Duração 7,7 min. O Playwright soma a falha esperada no total "74 passed". Na revisão #1: 2 de 14 passavam e 61 eram `fixme`. Li amostras (CA-24, CA-25, CA-36, CA-37): as asserções são reais, sobre URL, requisições, API e banco. |
| Importação UCI real | `alembic upgrade head` + `import_uci_diabetes.py --provision-demo-accounts` em um SQLite novo e isolado | 70 pacientes, 71 contas, 70 vínculos ACTIVE e 222 convites, mas **70 notificações** (era 222), ou seja, uma consolidada por paciente. `glucose_records` agora tem `notes_encrypted` e não tem mais `notes`. |
| Credenciais na reprovisão | Troquei a senha de `patient2@demo.myglico.invalid` e rodei `provision_demo_accounts` de novo | Senha nova **continua válida**; `qwerty` **não volta**. A4 corrigido. |
| Limite de tentativas | 12 logins errados via `curl` contra uvicorn | `401` ×10, depois **`429`** ×2. Logo em seguida, um login válido de **outra** conta a partir do mesmo IP também recebeu 429 (ver O2). |
| Navegador real | Vite :8020 → backend :8022 sobre cópia do banco UCI, script Playwright ad hoc (removido ao final) | Detalhes na tabela de achados abaixo. |
| Sondas de API | `TestClient` em SQLite novo | Ver A3, A12, A13, B2, B3 e B7. |

Todos os bancos e servidores foram temporários (scratchpad, portas 8020/8022 e as 8100/8101 da própria suíte) e foram encerrados. Nenhum arquivo de produto foi alterado.

## Situação de cada achado da revisão #1

| Achado | Situação | Evidência desta revisão |
| --- | --- | --- |
| **A1** popup vazio para pacientes UCI | **Corrigido** | Navegador, `patient1`: card `anomaly_days = 7` no período completo e popup com **7 dias**. `routes.py:650-655` agora faz join pelos indicadores do paciente. E2E "CSCW-CA-23 (A1)" passa. |
| **A2** dias não consecutivos viram intervalo | **Corrigido** | Navegador: selecionar o 1º e o 3º dia → URL `?dates=1991-07-26,1991-08-22`. E2E CA-24 compara indicadores e eventos só com esses dois dias e passa. |
| **A3** conta com dois papéis | **Não aplicável** (decisão de produto) | Mesmo e-mail registrado com o outro papel → **409**. Sessão de conta com Patient e Doctor inseridos por fora do fluxo → `authenticated: false` (`security.py:87`, `auth_service.py:161`). |
| **A4** importador redefinia a senha | **Corrigido**; credenciais públicas viraram divergência documentada | Reprovisão preserva a senha alterada. O domínio agora é `demo.myglico.invalid`. `qwerty` continua versionada e documentada no README e em `CRYPTO_CONFIGURATION.md`, por decisão de produto (B5-FIX): aceitável como exceção, já que o dataset é público. |
| **A5** sem limite de tentativas | **Corrigido**, com limitação documentada | 429 após 10 tentativas por minuto (login, busca e pedido de vínculo, por IP e por conta). Limitador em memória por processo, documentado no README. Ver O2. |
| **A6** leituras e `notes` em claro | **Corrigido** | `notes_encrypted` com migração 0007 (o validador de migração passa). A exceção para glicemia, horário e `context_label` está justificada em `CRYPTO_CONFIGURATION.md:51-55` (SDD1 §6.5). |
| **A7** "Agora não" reaparecia | **Corrigido** | Navegador: 7 botões → "Agora não" → 6 → **reload → 6**. `ProactivePrompt.jsx:25` filtra `created`. |
| **A8** médico sem caminho ao detalhamento | **Corrigido** | Navegador: médico demo vê **70** links "Ver detalhamento" e abre o detalhe; o formulário de leitura manual não aparece para ele. |
| **A9** enxurrada de convites | **Corrigido no backend, parcial na UI** | 70 notificações (uma por paciente, com `count`/`dates`). Ainda há um banner por dia (7 empilhados para `patient1`), agora **com a data** ("…em 22 de ago. de 1991"). Ver O3. |
| **A10** popup sem acessibilidade/estados | **Corrigido, exceto o resíduo de filtros** | `role=dialog`, foco inicial no título ("H3:Dias atípicos"), Esc, loading/erro e chips confirmados no navegador e no E2E. **Resíduo aberto: ver R1 (CSCW-CA-25).** |
| **A11** lista e conversa incompletas | **Corrigido** | `InvestigationsList.jsx` mostra não lidas por conversa, contraparte, data e origem. `InvestigationPage.jsx:127` mostra o motivo de encerramento traduzido. E2E grupos 06 e 08 passam. |
| **A12** eventos e histórico de proveniência | **Parcial** | Ver R2. |
| **A13** CRM/UF opcionais e aviso de privacidade | **Parcial** | Ver R3. |
| **A14** Docker e README sem chaves | **Corrigido** | `docker-compose.yml:32-33` exige as duas chaves (`:?`). O README documenta autenticação, chaves, `--provision-demo-accounts`, papel único, limitador e `VACUUM`. Não subi o Docker. |
| **A15** migrações dependem dos modelos ORM | **Aberto** (assumido no BACKLOG) | Ainda há 10 chamadas `__table__.create` em 0003–0006. O `VACUUM` foi apenas documentado. |
| **A16** suíte e matriz | **Corrigido, com matriz desatualizada** | Suíte real (ver acima). Problema na `MATRIZ-ACEITE.md`: ver R4. |
| **B1** `no-store` incompleto | **Aberto** | `/api/investigations`, `/api/notifications`, `/api/notifications/unread-summary` e `/api/doctor-links` continuam sem `Cache-Control` (testado com `curl`). |
| **B2** 409 revelava a investigação | **Corrigido** | Médico revogado → **404** no GET e no POST de mensagem. |
| **B3** `closed_by` humano no encerramento por revogação | **Aberto** | `closed_by` = ID do paciente que revogou. O evento continua correto. |
| **B4** outbox sem consumidor | **Aberto** | Skip documentado no pytest e no E2E (CSCW-CA-29 parcial). |
| **B5** enumeração por tempo no login | **Corrigido** | Hash fictício para e-mail inexistente (`auth_service.py:27,155`). |
| **B6** strings fixas e `role=alert` | **Corrigido** | Nenhum "Carregando" literal no JSX; strings novas em i18n nos 3 locales (paridade conferida pelo E2E do grupo 10). |
| **B7** cancelar sem `version` | **Aberto** | `POST /api/doctor-links/{id}/cancel` sem corpo → 200. |
| **B8** ciphertext adulterado → 500 genérico | Sem mudança (aceitável) | — |
| **B9** dispensar convite após recálculo | **Sem efeito prático** | Prompts e `defer` usam o mesmo `daily_indicator_id` gravado, e a UI dispensa pelo ID que vem dos prompts. |
| **B10** pontos positivos | Mantidos | Landing chama só `/api/auth/session`; logout sem vazamento. |
| **N1** card zerava após análise de outro paciente | **Corrigido** | E2E "CSCW-CA-23 (N1)" passa sem `test.fail`. No navegador, card e popup do UCI coincidem (7 = 7). |
| **NEW-1** pandas ≥ 3 com `context_label` misto | **Corrigido** | Teste de regressão agora normal e passando dentro dos 52 do pytest. |

## Achados remanescentes

**R1 — CSCW-CA-25: aplicar/limpar dias destrói o período do usuário** (defeito, **médio, bloqueante** por reprovar um critério obrigatório; SDD2 §9.3)
- Navegador (UCI, `patient1`): partindo de `?start_date=1991-04-21&end_date=1991-09-03`, aplicar 2 dias → `?dates=1991-07-26,1991-08-22`, sem o período. "Limpar seleção de dias" → `?start_date=1991-08-05&end_date=1991-09-03`, a janela padrão, e não o período original.
- Causa: com `dates=`, o backend devolve `filters.start_date/end_date = null`, e `PatientDetailPage.jsx:276-288` reescreve a URL a partir desses valores.
- Correção: manter `start_date`/`end_date` na URL junto com `dates`, e fazer o "limpar" remover apenas `dates`. Depois, tirar o `test.fail` de `09-atypical-popup-filters.spec.mjs:85`.

**R2 — A12 parcial: histórico de proveniência e deduplicação** (omissão, **baixo/médio**; SDD2 §10.3, §10.6)
- `GET /api/patients/{id}/provenance` só retorna `AtypicalDayDetailViewed` e `PatientDetailFilterApplied`. Um paciente com pedido, confirmação, revogação e investigação recebeu `{"events":[]}`. O §10.6 pede o histórico autorizado dessas ações.
- `AtypicalDayDetailViewed` é gravado a cada `GET /atypical-days`, ou seja, a cada abertura ou refresh do popup (2 aberturas → 2 eventos no banco). O SDD pede que abrir o popup não gere eventos repetidos por re-renderização. Além disso, um GET com efeito de escrita não é o ideal.

**R3 — A13 parcial: regras do cadastro de médico ficam só no frontend** (divergência, **baixo/médio**; SDD1 §5.3, §8.2)
- `POST /api/auth/register` com `role=doctor` e sem CRM/UF → **201**. A obrigatoriedade existe só no `RegisterPage.jsx`, então qualquer chamada direta à API contorna a regra.
- A ciência do aviso de privacidade é um checkbox de UI e **não é registrada** no backend. O SDD pede "registrar ciência".

**R4 — `MATRIZ-ACEITE.md` não acompanhou a correção do N1/NEW-1** (documentação, **baixo**)
- O total está correto (60 Aprovado / 4 Parcial / 2 Reprovado / 2 Não aplicável), mas três pontos ficaram para trás:
  - **CSCW-CA-23** ainda aparece "Reprovado por N1", e o N1 está corrigido (E2E passa).
  - **AUT-CA-21** ainda cita o "xfail strict" do NEW-1, que já virou teste normal.
  - O cabeçalho ainda diz "72 passaram, 2 `test.fail` / 51 passed, 1 xfailed". O estado atual é 73 + 1 `test.fail` / 52 passed, 0 xfail.
- O resto da matriz que conferi bate com o que executei: CA-07, 17, 22, 26, 29, 31, 32, 37 e 45.

**Observações (não bloqueantes)**
- **O1** — A15, B1, B3, B4 e B7 continuam abertos (detalhes na tabela acima).
- **O2** — O limitador usa um balde também por IP. Atrás de NAT, ou com um atacante no mesmo IP, 10 falhas bloqueiam o login de todas as contas daquele IP por 60 s (confirmado: o login válido de outra conta recebeu 429). Ele também não é compartilhado entre workers/processos (está documentado). É aceitável para o MVP, mas vale registrar como risco de negação de serviço.
- **O3** — A9 na UI: o banner de convites lista um bloco por dia (até 9 por paciente UCI). Cada um tem a data e o "Agora não" vale por dia. Atende ao critério porque a notificação é consolidada e não há datas falsas, mas um aviso único por lote seria mais fiel ao §7.6.
- **O4** — CSCW-CA-26 continua parcial: as datas são de parede, sem fuso por paciente. O teste das 23:59 passa porque grava e mostra a mesma data.

## Critérios de aceite — veredito do revisor (revisão #2)

Legenda: **E** = executado por mim (E2E completo, pytest, curl, navegador ou sonda); **V** = validador que rodei.

| Grupo | Veredito | Observação |
| --- | --- | --- |
| AUT-CA-01..06, 08..16, 18, 20, 22, 23 | **Aprovado (E/V)** | Suíte E2E 01/02/04/10 + pytest + validadores. AUT-CA-05 agora tem teste real com falha injetada (pytest de atomicidade passa). |
| AUT-CA-07 | **Aprovado (E)** | `notes` cifrado; exceção de glicemia documentada (A6). |
| AUT-CA-17 | **Aprovado (E)** | Reimportação real estável e senha alterada preservada (A4). |
| AUT-CA-19 | **Não aplicável** | Papel único por conta (decisão de produto); invariante verificada. |
| AUT-CA-21 | **Parcial** | Recálculos idênticos e o NEW-1 corrigido; sem baseline anterior à proteção para comparar. |
| CSCW-CA-01..21, 28, 30, 31, 32, 34..36, 38..44 | **Aprovado (E/V)** | E2E grupos 03–08 + pytest (incluindo corridas reais com threads para o CA-30 e o endpoint de proveniência para o CA-32). |
| CSCW-CA-22 | **Parcial** | Backend preserva a origem histórica; a UI não sinaliza "classificação anterior". |
| CSCW-CA-23 | **Aprovado (E)** | A1 e N1 corrigidos (navegador 7 = 7; E2E passa). A matriz ainda diz "Reprovado" (R4). |
| CSCW-CA-24 | **Aprovado (E)** | Datas exatas. |
| **CSCW-CA-25** | **Reprovado (E)** | R1. |
| CSCW-CA-26 | **Parcial** | O4. |
| CSCW-CA-27 | **Aprovado (E)** | Dialog, foco, Esc, loading/erro/vazio. |
| CSCW-CA-29 | **Parcial** | B4. |
| CSCW-CA-33 | **Não aplicável** | Decisão de produto. |
| CSCW-CA-37 | **Aprovado (E)** | A7. |
| CSCW-CA-45 | **Aprovado (E)**, com O3 | 70 notificações consolidadas na importação real. |

**Totais da revisão #2: 61 Aprovado · 4 Parcial (AUT-CA-21, CSCW-CA-22, 26, 29) · 1 Reprovado (CSCW-CA-25) · 2 Não aplicável.** A diferença para a matriz está só no CSCW-CA-23 (ver R4).

## Para aprovar

Obrigatório:
1. **R1**: preservar `start_date`/`end_date` ao aplicar `dates`, e fazer "Limpar seleção de dias" remover só `dates`. Tirar o `test.fail` do CSCW-CA-25 e ver o teste passar.
2. **R4**: atualizar a `MATRIZ-ACEITE.md` (CSCW-CA-23 → Aprovado, AUT-CA-21 sem a menção ao xfail, CSCW-CA-25 conforme o resultado de R1, e o cabeçalho com os números atuais).

Recomendado (pode virar pendência conhecida, sem bloquear): R2 (histórico de vínculo e investigação no endpoint de proveniência, deduplicação do `AtypicalDayDetailViewed`), R3 (CRM/UF obrigatórios e ciência de privacidade no backend), B1, B3, B7, A15 e O2.
