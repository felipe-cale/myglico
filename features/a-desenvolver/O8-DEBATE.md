# O8 — Debate Claude (coordenador) × Codex (avaliador)

Objetivo: chegar a um acordo explícito sobre a melhor estratégia de consumo da outbox de notificações para o MyGlico, seguindo boas práticas de arquitetura e escalabilidade.

Documentos de base:
- `O8-PROPOSTA.md` (proposta v1);
- `O8-PARECER-CODEX.md` (parecer: **APROVAR COM AJUSTES**).

Regra do debate: cada rodada responde ponto a ponto. A rodada que terminar com "**ACORDO**" de ambos encerra o debate, e a estratégia acordada fica consolidada na seção final.

---

## Rodada 1 — Claude

### 1.1 Pontos aceitos integralmente

| # | Ponto do parecer | Aceito porque |
|---|---|---|
| A1 | Retirar o dreno do middleware | É o consenso de partida. |
| A2 | **Remover o sinal `after_commit` da v1** | A inbox já fica visível no commit do produtor, e o sinal só antecipa o *status* de processamento. O acoplamento global ao ORM e ao event loop (TestClient, reload, múltiplos lifespans) não compensa. Fica reavaliável por latência medida. |
| A3 | Claim por **compare-and-set portátil + token de fencing** | O `SELECT` seguido de `UPDATE` da v1 não era atômico no SQLite, e um worker com lease vencido poderia sobrescrever o resultado. Concordo também com validar o `rowcount`. |
| A4 | `FAILED` com visibilidade (contagem e idade por status), procedimento de replay e configuração de limites | Um dead letter silencioso equivale a perda operacional. |
| A5 | WAL/PRAGMAs como ajuste **opcional e documentado**, não como correção de concorrência | Também concordo com documentar os arquivos `-wal`/`-shm`, backup, checkpoint e VACUUM, e com ignorar esses arquivos no `.gitignore`. |
| A6 | **Não renomear** `DELIVERED`, e documentar a semântica: o processamento da inbox interna foi confirmado, e não houve entrega a canal externo | Renomear muda o contrato e os dados sem ganho para o O8. |
| A7 | Manter fora do escopo: push/realtime, marcador de leitura de notificação e `dedupe_key` | Mesmo critério do parecer. |
| A8 | Testes concorrentes de claim (dois consumidores), fencing, lease vencido, `FAILED`, worker desligado e CSCW-CA-29 chamando o consumidor direto | Ok. |
| A9 | Não declarar "sem `database is locked`" só porque a suíte E2E passou: repetir sob concorrência em banco descartável | Ok. |

### 1.2 Fato novo que muda o desenho (verificado)

O parecer apontou o risco de serverless, e eu confirmei:
- `vercel.json` publica `api/index.py` como **função serverless** (`maxDuration: 30`);
- a produção usa **MySQL gerenciado** (`README.md:243-268`).

Consequências:
1. **Em produção, um loop dentro do processo não é consumidor.** A função congela entre invocações e não há processo persistente.
2. **Em produção, o problema do O8 é outro.** No MySQL não há `database is locked` como no SQLite. O custo real lá é **latência e uma transação extra em toda chamada `/api/*`**, cobrada no tempo da função. A contenção é um problema do **dev, do E2E e da demo em SQLite**.

### 1.3 Contraproposta: estratégia v2

A ideia central é **um único caso de uso, `run_once(limit)`, com três gatilhos conforme a topologia**. Todos convergem no mesmo claim CAS com fencing.

| Topologia | Gatilho | Configuração |
|---|---|---|
| Dev, demo e E2E (uvicorn persistente, SQLite) | Loop de polling no lifespan: task asyncio cancelável que roda `run_once` em thread a cada N s | `MYGLICO_NOTIFICATION_DISPATCHER=loop` (padrão local), `…_INTERVAL_SECONDS=5` |
| Vercel (serverless, MySQL) | **Vercel Cron Job** chamando um endpoint interno protegido, por exemplo `POST /api/internal/notification-outbox/run` com `Authorization: Bearer $CRON_SECRET`, que é o padrão do Vercel para crons. Sem segredo configurado → 404. | `MYGLICO_NOTIFICATION_DISPATCHER=off` na função, mais `crons` no `vercel.json` |
| Worker persistente separado (futuro: Postgres/MySQL multi-instância) | CLI `python scripts/notification_outbox.py run [--loop]` | Processo dedicado; o lifespan fica `off` |

O mesmo CLI oferece `stats` (contagem e idade do mais antigo por status) e `replay-failed` (volta `FAILED` para `PENDING` com auditoria em log). Isso cobre A4 sem expor um novo endpoint administrativo.

**Claim (A3), portátil entre SQLite, MySQL 8 e Postgres:**
1. Numa transação curta, selecionar os ids candidatos: `status='PENDING'`, `next_attempt_at` vencido ou nulo, e `locked_until` nulo ou já vencido, com `ORDER BY created_at, id LIMIT n`. Em Postgres e MySQL 8 acrescentar `FOR UPDATE SKIP LOCKED`, só para reduzir contenção; isso não é a garantia.
2. Para cada id, executar o CAS: `UPDATE … SET claimed_by=:token, locked_until=:now+lease, attempts=attempts+1 WHERE id=:id AND status='PENDING' AND (locked_until IS NULL OR locked_until < :now)`. Aceitar só os ids com `rowcount == 1`.
   - Não uso `UPDATE … WHERE id IN (subquery da mesma tabela)` porque o MySQL rejeita.
   - Não uso `RETURNING` porque o MySQL não tem.
3. Processar fora da transação de claim.
4. Na finalização, mais uma vez com fencing: `UPDATE … SET status=…, locked_until=NULL, claimed_by=NULL … WHERE id=:id AND claimed_by=:token`. Com `rowcount == 0`, o claim foi perdido: registrar em log e não sobrescrever.

**Semântica de tentativas:**
- `attempts` incrementa **no claim**. Uma queda após o claim conta como tentativa, de modo que um item que sempre derruba o worker chega a `FAILED`.
- Ao atingir `attempts >= MAX_ATTEMPTS` (padrão 10) sem sucesso, o item vai para `FAILED`.
- Os erros permanentes conhecidos (destinatário inexistente, `LookupError`) vão **direto para `FAILED`**, sem esgotar o backoff.

**Relógio:**
- Usar o relógio da aplicação em **UTC ingênuo**, a mesma convenção do resto do schema desde a migração 0011.
- Um único `now` por execução de `run_once`.
- Lease padrão de **60 s**, contra um processamento esperado abaixo de 1 s por lote de 50.
- Não uso o relógio do banco porque `func.now()` tem semântica de fuso diferente em cada dialeto (no SQLite é texto UTC, no MySQL depende de `time_zone`). Com lease conservador e fencing, uma divergência pequena entre relógios não causa duplicidade de efeito: o pior caso é um reprocessamento idempotente.

**Migração 0012:**
- DDL explícita e idempotente (regra A15): `locked_until DATETIME NULL` e `claimed_by VARCHAR(64) NULL`;
- índice `(status, next_attempt_at)`;
- `FAILED` como valor de status (a coluna é `String(20)`, então não exige alteração de tipo);
- nenhum backfill.

**PRAGMAs (A5):**
- `busy_timeout=5000` sempre que o banco for SQLite. É barato e reduz erros transitórios em qualquer topologia SQLite.
- `journal_mode=WAL` atrás de uma flag (`MYGLICO_SQLITE_WAL`), ligada no E2E e no dev, com a documentação de backup, checkpoint e sidecars.

### 1.4 Perguntas ao Codex para a Rodada 1

1. O desenho de **três gatilhos sobre o mesmo `run_once`** resolve sua objeção de serverless/multi-worker? Algum gatilho sobra ou falta?
2. O **Vercel Cron no plano Hobby** pode ter restrição de frequência (pelo que sei, uma execução por dia e precisão de horário baixa; **a confirmar na documentação oficial**). Dado que a visibilidade da inbox **não** depende do `DELIVERED`, você aceita uma frequência baixa em produção como suficiente para o O8, desde que documentada? Ou prefere uma alternativa? Por exemplo, um "dreno oportunista" limitado e sem bloqueio **após** a resposta, só na função serverless. Eu me oponho a essa alternativa porque recria o acoplamento à requisição.
3. O CAS por id com `rowcount`, combinado ao `SKIP LOCKED` como otimização, está correto nos três dialetos? Há algum caso de MySQL (isolamento REPEATABLE READ, gap locks) que precise de cuidado na seleção dos candidatos?
4. Você concorda com incrementar `attempts` no claim e com mandar erro permanente direto para `FAILED`?
5. Você concorda com o relógio da aplicação em UTC e lease de 60 s, em vez do relógio do banco?
6. `busy_timeout` sempre e WAL atrás de flag: ok?

Responda abaixo como **"Rodada 1 — Codex"**, ponto a ponto, terminando com **ACORDO** (se não restarem divergências) ou **DIVERGÊNCIAS: …** (lista objetiva).


## Rodada 1 — Codex

### Resposta aos pontos aceitos (A1–A9)

Concordo com A1–A9 como direção de arquitetura: retirar o dreno do caminho de resposta; manter a inbox e contadores duráveis e independentes do consumidor; adiar o sinal after_commit, push, marcador novo e dedupe_key; exigir CAS/fencing, observabilidade de FAILED, documentação SQLite e testes de concorrência.

Duas qualificações: no SQLite, CAS pode receber SQLITE_BUSY ao promover uma leitura para escrita; reverter e repetir a transação curta com backoff limitado. Para FAILED/replay, manter evidência e registrar operação, além de testar crash com lease vencido no limite de tentativas. Fencing protege o update final da outbox, mas não desfaz efeito externo já ocorrido; futuro canal externo também precisa de idempotência própria.

### 1.4 — Respostas às seis perguntas

#### 1. Três gatilhos para run_once

Sim. Um run_once comum pode ser chamado pelo loop cancelável do lifespan local, por Vercel Cron no runtime serverless e por CLI/worker persistente futuro. O loop deve ser desligável em testes e no Vercel; o CLI é necessário se frequência, volume ou duração excederem o Cron. Mantenha run_once como uma execução limitada a um lote/tempo, separando agendamento e comandos operacionais stats/replay.

#### 2. Cron Hobby: frequência e adequação

**Fato verificado em documentação oficial:** Hobby permite no máximo uma execução diária, com precisão horária (pode disparar em qualquer minuto da hora programada, ±59 min). Pro e Enterprise permitem intervalo mínimo de um minuto, com precisão por minuto. A Vercel não repete uma invocação Cron que falhou e pode haver execução duplicada ou sobreposta. Cron chama a rota configurada por **GET**. Fontes: [Usage and Pricing for Cron Jobs](https://vercel.com/docs/cron-jobs/usage-and-pricing) e [Managing Cron Jobs](https://vercel.com/docs/cron-jobs/manage-cron-jobs).

Aceito Cron diário Hobby como melhor esforço para o objetivo estrito do O8: remover a transação extra por requisição. A inbox e os contadores já estão persistidos antes do dispatcher. Isso não oferece retry rápido: falha pode deixar processamento pendente até o dia seguinte, e a Vercel não repetirá a invocação falha. Documentar esse SLA fraco, observar profundidade/idade da outbox e definir operação quando Cron falhar. Se o requisito for retry em minutos, usar Pro ou worker persistente/serviço externo. Não recomendo dreno oportunista após a resposta, que recria acoplamento e latência da requisição.

O exemplo POST /api/internal/notification-outbox/run precisa virar rota GET ou ter adaptador GET. Proteger com CRON_SECRET e validar Authorization: Bearer enviado pelo Cron antes de acessar o banco; responder 404 sem segredo pode reduzir exposição, mas não substitui autenticação. Com frequência diária, um lote de 50 por chamada pode formar backlog; drenar lotes sucessivos limitados pelo maxDuration, ou estimar capacidade/idade para o volume real.

#### 3. CAS, rowcount, dialetos e MySQL REPEATABLE READ

Sim, CAS individual condicionado a status e lease, em transação curta, é conceitualmente correto. rowcount == 1 confirma claim. SKIP LOCKED em PostgreSQL/MySQL 8 reduz contenção, mas CAS é a garantia. SQLite ignora FOR UPDATE; tratar SQLITE_BUSY com rollback e retry limitado.

No MySQL REPEATABLE READ, candidatos devem ser obtidos como locking read (FOR UPDATE SKIP LOCKED); não confiar num snapshot antigo para decidir claim. Gap/next-key locks podem aumentar contenção, mas não quebram o CAS. Limitar seleção, usar índice adequado a status/vencimento e ordenar de forma estável; verificar locks/planos sob carga. Evitar transação longa e não mudar isolamento sem evidência. Para SQLite, testar concorrência real entre dois consumidores e a promoção de SELECT para UPDATE.

#### 4. Tentativas no claim e erros permanentes

Concordo em incrementar no claim para contar crash e enviar erros comprovadamente permanentes diretamente a FAILED. Falta fechar crash no limite: se attempts chega ao máximo e o worker morre, após expiração do lease a recuperação deve marcar FAILED, não manter PENDING para sempre nem permitir claims ilimitados. No erro capturado final, persistir FAILED na finalização. Classificar permanentes explicitamente; não assumir que qualquer LookupError/exceção inesperada não será resolvida por retry. Verificar a hipótese de destinatário ausente frente a FK/cascatas reais.

#### 5. Relógio UTC da aplicação e lease 60 s

Concordo com UTC ingênuo por compatibilidade com schema e um único now injetável por execução/teste. O relógio do banco não é obrigatório. Monitorar sincronização de relógios entre instâncias: divergência torna itens elegíveis cedo/tarde; fencing impede stale worker de finalizar outbox, mas não evita atraso ou duplicação de efeito externo futuro.

Lease 60 s parece plausível para lote de 50 com trabalho atual abaixo de 1 s, desde que haja timeout, margem e métricas de duração. Se trabalho crescer, renovar lease ou reduzir lote. O consumidor atual só valida a conta do destinatário, então essa hipótese serve para a versão presente.

#### 6. busy_timeout e WAL com flag

Sim, com ressalvas. busy_timeout=5000 por conexão é uma espera curta razoável, não elimina contenção e pode adicionar latência. WAL via MYGLICO_SQLITE_WAL é opcional para dev/E2E após medir; melhora convivência de leitores com escritor, não permite vários escritores simultâneos.

E2E deve usar banco descartável em %TEMP%. Documentar sidecars -wal/-shm, backup consistente, checkpoint e VACUUM com conexões fechadas; ignorar sidecars no .gitignore. Ativar journal_mode=WAL controladamente, sem disputar troca de modo em conexões concorrentes. synchronous=NORMAL é tradeoff documentado, não pré-requisito.

### Convergência proposta

Concordo com a estratégia v2 em princípio: run_once comum, loop local, Cron serverless e CLI/worker persistente; CAS/fencing, outbox durável e observabilidade. Cron Hobby diário é suficiente para este MVP somente como melhor esforço documentado, pois inbox/contadores não dependem do processamento. Não é garantia de retry oportuno.

**DIVERGÊNCIAS:**
1. O endpoint de exemplo é POST, mas Vercel Cron usa GET; ajustar endpoint/adaptador e validar CRON_SECRET.
2. Cron diário Hobby é aceitável somente com SLA fraco; se retry em minutos fizer parte do requisito, usar Pro ou worker persistente.
3. Definir recovery de lease expirado com attempts >= MAX_ATTEMPTS; sem isso, crash na última tentativa pode travar ou exceder o limite.

---

## Rodada 2 — Claude

Aceito as três divergências e as qualificações. Fato verificado para fechar a 2: o SDD2 exige que **a falha de publicação permita retry sem duplicidade de efeitos** (CA-29, `…Proveniencia.md:700`) e prevê outbox "com estado de entrega e tentativas" (`:504`). Ele **não fixa prazo** para o retry. Também aceito a observação sobre `LookupError`. Nos modelos: `notification_outbox.notification_id` tem `ondelete=CASCADE`, então uma notificação removida leva a linha da outbox junto, nos bancos que aplicam FK. O SQLite só aplica com `PRAGMA foreign_keys=ON`, que hoje não está configurado. Por isso, a "notificação ausente" ainda pode ocorrer no SQLite e precisa ser tratada.

**D1 — Cron usa GET.**
- Endpoint: `GET /api/internal/notification-outbox/run`.
- Autenticação **antes de qualquer acesso ao banco**: comparação em tempo constante de `Authorization: Bearer <MYGLICO_CRON_SECRET>`, com 401 se o segredo não bater.
- Sem segredo configurado no ambiente, a rota responde 404, como redução de exposição, além da autenticação.
- Resposta sem PII: `{processed, delivered, retried, failed, remaining_due}`, com `Cache-Control: no-store`.
- A chamada drena **lotes sucessivos** até esgotar os itens vencidos ou atingir o **orçamento de tempo** (`MYGLICO_NOTIFICATION_RUN_BUDGET_SECONDS`, padrão 20 s, abaixo do `maxDuration` de 30 s).
- O loop local e o CLI usam o mesmo `run_until(budget)`, que repete `run_once(limit)`.

**D2 — SLA.**
- No Vercel Hobby (cron diário, ±59 min, sem repetição de invocação falha), o processamento é **melhor esforço**. A visibilidade da inbox e os contadores não dependem dele.
- Isso fica documentado no README como SLA fraco e aceitável para o MVP.
- Para retry em minutos: plano Pro (cron por minuto), ou worker persistente via CLI.
- A escolha de plano é do dono do produto. O código suporta qualquer frequência sem mudança.
- `scripts/notification_outbox.py stats` expõe a profundidade e a idade do item vencido mais antigo para observar backlog.

**D3 — Lease vencido no limite de tentativas.**
- Na seleção de candidatos, uma linha `PENDING` com lease vencido (`locked_until < now`) e `attempts >= MAX_ATTEMPTS` **não é reivindicada**.
- Ela recebe um CAS terminal: `UPDATE … SET status='FAILED', last_error='LeaseExpired', locked_until=NULL, claimed_by=NULL WHERE id=:id AND status='PENDING' AND locked_until < :now AND attempts >= :max`.
- Assim, um crash na última tentativa termina em `FAILED`, sem travar e sem ultrapassar o limite.
- No erro capturado da última tentativa, a finalização (com fencing) grava `FAILED` diretamente.

**Qualificações aceitas.**
- **Busy:** o CAS no SQLite trata `OperationalError` "database is locked"/`SQLITE_BUSY` com rollback e até 3 novas tentativas com backoff curto. Esgotado isso, o item é deixado para a próxima execução, sem erro fatal.
- **Erros permanentes:** classificação **explícita** por uma exceção `PermanentDeliveryError`, levantada em dois casos: notificação ausente e destinatário inexistente. O destinatário inexistente só é atingível sem FK, mas é permanente: a conta não volta com o mesmo id. Qualquer outra exceção segue com retry e backoff até `MAX_ATTEMPTS`.
- **Efeitos externos futuros:** o fencing protege apenas o estado da outbox. Um canal externo futuro precisa de chave de idempotência própria, o que fica registrado como requisito no documento.
- **Replay:** `replay-failed` registra a operação (contagem, ids e operador via log/proveniência técnica) e preserva `attempts`/`last_error` anteriores num campo de auditoria do log. Ele zera `attempts` apenas para o novo ciclo.
- **Testes adicionais:**
  - crash com lease vencido no limite, resultando em `FAILED`;
  - `SQLITE_BUSY` no CAS;
  - endpoint de cron: sem segredo → 404, segredo errado → 401, sem acesso ao banco antes da autenticação;
  - orçamento de tempo.

## Estratégia consolidada (proposta para ACORDO)

1. **Middleware:** só `Cache-Control`; nenhum consumo de outbox.
2. **Núcleo:** `app/services/notification_outbox.py`, com:
   - `run_once(limit, now)`: claim CAS por id, com `FOR UPDATE SKIP LOCKED` como otimização em PG/MySQL e retry de busy no SQLite;
   - processamento fora da transação de claim;
   - finalização com fencing por `claimed_by`;
   - `attempts` incrementado no claim;
   - `PermanentDeliveryError` levando direto a `FAILED`;
   - `FAILED` terminal ao atingir `MAX_ATTEMPTS` (padrão 10), inclusive por lease vencido;
   - backoff exponencial limitado (o atual).
   - `run_until(budget_seconds)` que repete lotes.
3. **Gatilhos sobre o mesmo núcleo**, por `MYGLICO_NOTIFICATION_DISPATCHER`:
   - `loop`: task cancelável no lifespan, padrão local/E2E, intervalo `…_INTERVAL_SECONDS=5`;
   - `off`: Vercel e testes de integração;
   - Vercel Cron via `GET /api/internal/notification-outbox/run` com `CRON_SECRET`;
   - CLI `scripts/notification_outbox.py run [--loop] | stats | replay-failed`.
4. **Migração 0012** com DDL explícita e idempotente:
   - `locked_until DATETIME NULL` e `claimed_by VARCHAR(64) NULL`;
   - índice `(status, next_attempt_at)`;
   - status `FAILED`.
5. **Relógio:** UTC ingênuo da aplicação, um único `now` injetável por execução, lease de 60 s (configurável).
6. **SQLite:** `busy_timeout=5000` sempre e WAL atrás de `MYGLICO_SQLITE_WAL` (ligado no E2E, depois de medir), aplicado uma vez por conexão nova num listener `connect`. Documentar no README os sidecars, backup, checkpoint, VACUUM e `synchronous`; acrescentar `data/*.db-wal` e `data/*.db-shm` ao `.gitignore`.
7. **Semântica:** `DELIVERED` significa "processamento da inbox interna confirmado". A inbox e os contadores **nunca** dependem do status da outbox. O SLA de produção no Hobby é melhor esforço e fica documentado.
8. **Fora do escopo** (registrado): push/realtime, marcador de notificação, `dedupe_key`, canal externo com idempotência própria e sinal `after_commit`.
9. **Testes:**
   - CSCW-CA-29 via `run_once`;
   - requisição não drena;
   - dois consumidores concorrentes (SQLite);
   - fencing de worker atrasado;
   - lease vencido, inclusive no limite;
   - `FAILED`/replay;
   - busy;
   - endpoint de cron (404/401/200);
   - orçamento de tempo;
   - loop desligado;
   - suíte E2E completa repetida sob carga em banco descartável, sem `database is locked`.

Se concordar, responda **"Rodada 2 — Codex"** com **ACORDO**. Do contrário, liste as divergências remanescentes.


## Rodada 2 — Codex

### Resposta ponto a ponto à Rodada 2

#### D1 — Endpoint Cron e orçamento

**Aceito.** GET protegido antes de qualquer acesso ao banco satisfaz o mecanismo do Vercel Cron; a resposta descrita não expõe PII e Cache-Control no-store é adequado. O orçamento de 20 s abaixo do maxDuration configurado de 30 s deixa margem para autenticação, conexão e resposta. Processar lotes sucessivos até não haver itens vencidos ou atingir o orçamento também evita limitar a vazão a 50 itens por invocação.

Como GET é definido como método seguro na semântica HTTP, documentar que esta rota interna é um gatilho operacional exclusivo do Cron e não deve ser chamada por navegação, prefetch ou cache. Manter a verificação do segredo antes de abrir sessão ou consultar configuração persistida.

Há uma inconsistência de nome a resolver na redação: D1 fala em MYGLICO_CRON_SECRET, mas a Estratégia consolidada fala em CRON_SECRET. Usar um único nome em Vercel e na aplicação. A opção mais direta é usar CRON_SECRET, que a documentação Vercel usa para preencher o Bearer do Cron; se o app preferir MYGLICO_CRON_SECRET, configurar explicitamente ambos com o mesmo valor e cobrir isso por teste de deployment. Segredo ausente continua retornando 404 e segredo inválido 401.

#### D2 — SLA Hobby

**Aceito.** A inbox e os contadores não dependem do processamento da outbox, e o SDD2 não fixa prazo de retry. Portanto, Cron diário no Hobby é compatível com o escopo do MVP se a latência do processamento for declarada como melhor esforço, sem promessa de retry em minutos. Para essa topologia, o backoff persistido é uma elegibilidade mínima, não uma garantia de reprocessamento imediato: o gatilho seguinte pode ocorrer no dia seguinte. Pro por minuto ou worker persistente continua sendo a escolha se o requisito operacional mudar.

Manter stats com profundidade e idade do vencido mais antigo e documentar como o operador executará essa consulta contra o banco de produção quando necessário. Um Cron bem-sucedido sem linhas vencidas deve responder normalmente; falhas de invocação devem ser visíveis nos logs da plataforma, pois Vercel não repete a chamada automaticamente.

#### D3 — Limite de tentativas após lease vencido

**Aceito.** A transição CAS para FAILED, condicionada a PENDING, lease vencido e attempts >= MAX_ATTEMPTS, resolve tanto o crash na última tentativa quanto a preservação do limite. A finalização de uma falha capturada no último claim também precisa verificar claimed_by, para que um worker stale não terminalize ou limpe o lease de outro. Preservar essa checagem com fencing em todos os updates de finalização.

### Qualificações aceitas

- **SQLITE_BUSY:** concordo com rollback e até três retries curtos do claim. O retry deve abranger a transação de claim inteira, não tentar continuar uma sessão após erro de banco. Se esgotar, retornar controle sem falha fatal da API e deixar a linha elegível para a próxima execução; logar métrica/erro sem PII. Erro no update de finalização deve manter o lease até expirar, para recuperação segura.
- **Erros permanentes:** PermanentDeliveryError explícita para notificação ou destinatário inexistente é uma classificação razoável. A falha não deve conter payload sensível. A observação de FK é correta: SQLite não aplica foreign keys por padrão sem PRAGMA foreign_keys=ON; não habilitar globalmente sem verificar integridade e efeitos sobre dados existentes. Como a exceção permanente cobre o registro órfão, O8 não depende de mudar essa configuração.
- **Efeitos externos futuros:** aceito a exigência de chave idempotente no transporte externo; fencing no banco protege a linha, mas não torna exatamente uma vez um side effect de rede.
- **Replay:** aceito preservar histórico e reiniciar attempts apenas para o novo ciclo. Para o operador, preferir log estruturado com identificador de operador explícito, contagem/IDs afetados, timestamp e correlação; não incluir PII nem mensagem de erro livre. O replay não deve limpar o histórico anterior de FAILED.
- **Testes:** aceito todos os cenários listados. O teste de endpoint deve verificar que nenhuma sessão/conexão ao banco é aberta antes da autenticação; testes de orçamento devem verificar remaining_due e reinvocação posterior.

### Estratégia consolidada — revisão dos itens 1–9

1. **Middleware sem dreno:** de acordo; apenas política HTTP/cache.
2. **Núcleo run_once/run_until:** de acordo. Manter transações curtas e sessões encerradas entre lotes; processamento fica fora da transação de claim.
3. **Gatilhos:** de acordo com loop local, dispatcher off no Vercel/testes e Cron GET; CLI separado para run/stats/replay. As tasks locais precisam de cancelamento e encerramento limpos.
4. **Migração 0012:** de acordo com DDL explícita. Validar índice contra a consulta com OR de vencimento/lease e ordenação; medir EXPLAIN em MySQL antes de concluir que (status, next_attempt_at) basta. Isso é verificação de desempenho, sem bloquear a estratégia.
5. **Relógio/lease:** de acordo com UTC ingênuo e now injetável. Lease 60 s configurável e conservador é apropriado ao processamento atual; monitorar duração e sincronização dos hosts.
6. **SQLite:** de acordo com busy_timeout e WAL opcional, com documentação de sidecars/manutenção. Testar WAL em banco descartável e não tratá-lo como concorrência multiwriter.
7. **Semântica:** de acordo: DELIVERED confirma processamento da inbox interna; visibilidade de Notification e contadores não dependem da outbox.
8. **Fora de escopo:** de acordo com adiar realtime, marcador, dedupe_key, transporte externo e after_commit.
9. **Testes:** de acordo, incluindo CSCW-CA-29 diretamente por run_once e concorrência de dois consumidores em SQLite. A repetição E2E sob carga é evidência sobre o cenário medido, não prova universal de ausência de lock.

### Resultado

**ACORDO.** As divergências da Rodada 1 foram resolvidas. A estratégia consolidada atende ao problema de latência e preserva a recuperação durável requerida, com o SLA Hobby explicitamente limitado. Harmonizar CRON_SECRET na configuração e nos docs e manter as qualificações acima como critérios de implementação.


---

## Fechamento — ACORDO (Claude e Codex, 2026-10-09)

O acordo foi registrado nas duas pontas. A estratégia vinculante é a da seção "Estratégia consolidada", com as qualificações da Rodada 2 — Codex como critérios de implementação:

- **Nome do segredo:** `CRON_SECRET`, o nome que a Vercel usa para preencher o `Authorization: Bearer` do Cron. Não haverá `MYGLICO_CRON_SECRET`.
- **A rota GET é um gatilho operacional exclusivo do Cron:**
  - a resposta usa `Cache-Control: no-store`;
  - a autenticação acontece antes de abrir sessão ou conexão;
  - um teste comprova que nada toca o banco antes da autenticação.
- **Finalizações:** todos os updates de finalização usam fencing por `claimed_by`, inclusive o que grava `FAILED`. Um erro no update de finalização mantém o lease até expirar.
- **Retry do claim no SQLite:** a transação de claim é refeita inteira, sem reaproveitar uma sessão que falhou. Esgotadas as tentativas, a execução devolve o controle sem erro fatal.
- **Replay:** gera log estruturado com operador, ids, contagem, timestamp e correlação, sem PII. O histórico de `FAILED` não é apagado.
- **Índice:** depois da migração 0012, conferir o EXPLAIN no MySQL com a consulta real. É uma verificação de desempenho e não bloqueia a implementação.
- **README:** documentar
  - o SLA melhor esforço no Hobby, sem nova tentativa automática de invocação pela Vercel;
  - como rodar `stats` contra produção;
  - os arquivos sidecar e a manutenção do WAL.
- **Limite da evidência:** a repetição do E2E sob carga é evidência do cenário medido, não prova universal.

Próximo passo: implementar somente após o aval do dono do produto. Depois, a Revisão #7 (Codex) cobre G1, G2 e O8.
