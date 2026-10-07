# Revisão final independente — revisão #4 (atual, final)

**Revisor:** o mesmo worker Claude independente das revisões #1 a #3. Não edita código: só lê, executa e escreve este parecer.
**Objeto:** diff do worktree `C:\Users\felip\orca\workspaces\myglico\doliolid` (branch `felipe-cale/feature-orca-prompt-features`, **sem commit**), inspecionado entre **2026-10-07 10:00 e 10:25 (horário local)**. Base: `0920365`.

## Veredito final

# **APROVADO**

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
