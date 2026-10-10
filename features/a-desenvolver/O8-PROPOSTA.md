# O8 — Consumo da outbox de notificações fora da requisição: problema, pesquisa e proposta

Documento para avaliação independente antes de qualquer implementação. Status: **a estratégia completa foi acordada com o Codex (`O8-DEBATE.md`) e fica como desenho futuro, para quando houver um canal externo de notificação. Por decisão do usuário, em 2026-10-09 foi implementada a versão enxuta: o consumo saiu da requisição para um loop em segundo plano ou CLI. Ver `BACKLOG.md`.**

## 1. Problema

O fluxo atual de notificações:

- Os eventos de domínio gravam na **mesma transação** uma linha em `notifications`, que é a caixa de entrada lida diretamente pela UI e pela API, e uma em `notification_outbox`.
  - `notification_outbox` guarda `status=PENDING`, `attempts`, `next_attempt_at`, `last_error` e `processed_at`, com UNIQUE em `notification_id`.
  - Produtores: `app/services/doctor_links.py:80`, `app/services/doctor_links.py:135` e `app/services/investigations.py:66`.
- O consumidor é o middleware HTTP `app/main.py:43-52`. Depois de **toda** resposta `/api/*` e antes de devolvê-la, ele abre uma sessão e executa `drain_notification_outbox` (`app/services/notification_outbox.py`).
  - Lê até 100 linhas PENDING vencidas com `with_for_update(skip_locked=True)`, que não tem efeito no SQLite.
  - Para cada linha, confirma que o destinatário existe (`_deliver_to_in_app_inbox`) e marca DELIVERED, ou agenda retry com backoff exponencial limitado a 300 s, gravando só o nome da classe da exceção.
  - Faz um commit no final. A exceção é engolida para não alterar a resposta.
- Banco: `app/db/session.py` aceita **SQLite** (dev, demo, testes e E2E) e **MySQL** (PyMySQL, com tratamento de `ssl_mode` de provedores gerenciados). Postgres é um alvo plausível. Não há PRAGMAs de SQLite configurados.
- Não lidos:
  - mensagens usam marcador monotônico (`investigation_read_positions.last_read_sequence`);
  - notificações usam `read_at` por linha.

**Efeitos observados:**

1. **Contenção de escrita.** Toda requisição `/api/*`, inclusive GET, faz uma transação de escrita extra. O SQLite tem um único escritor por banco.
   - Na suíte E2E completa de 2026-10-09 apareceu `sqlite3.OperationalError: database is locked` no backend, junto com logs "Notification outbox drain failed".
   - A CSCW-CA-44 falhou porque o menu de mensagens não ficou visível.
   - O mesmo teste isolado com `--repeat-each 5` passou 5/5, e a suíte completa seguinte passou (79 passed, 1 skipped, 0 locked). A falha é **intermitente e aparece sob carga**.
2. **Latência** em toda chamada `/api/*`.
3. **A "entrega" é quase nominal.** A inbox lê `notifications` diretamente. A outbox só confirma que o destinatário existe e registra o estado de entrega e retry para o requisito do SDD2: publicação após commit, outbox/retry e deduplicação.

O registro anterior está em `REVISAO-FINAL.md` (observação O8 da revisão #5 e da revisão #6) e em `BACKLOG.md` (seção "AUDITORIA GERAL … correções G1/G2").

## 2. Pesquisa: como redes sociais open source resolvem

Fontes abertas via raw.githubusercontent.com (main/develop) e documentação oficial; a lista completa está no fim do documento.

**Mastodon (Ruby/Sidekiq)**
- **Criação e consumo:** a notificação é criada em job (`LocalNotificationWorker` chama `NotifyService#call`, que faz `save!`). O consumidor é Sidekiq, num processo separado.
- **Deduplicação:** no worker, por (conta, atividade, tipo). A checagem não é atômica.
- **Agrupamento:** `group_key` com janela de horas.
- **Realtime:** Redis pub/sub sem replay. A REST é a fonte da verdade.
- **Não lidos:** marcador `Marker.last_read_id` com `lock_version`. A contagem é feita sob demanda e limitada.

**Discourse (Sidekiq + MessageBus)**
- **Criação:** em job (`PostAlerter`), com enfileiramento por `DB.after_commit { client_push }` em `app/jobs/base.rb`.
- **Deduplicação e consolidação:** `ConsolidationPlanner`.
- **Não lidos:** modelo híbrido. Há flag `read` por linha e marcador `seen_notification_id`; o badge conta `NOT read AND id > seen_notification_id`, limitado a 99.
- **Realtime:** o MessageBus publica o **estado completo** (contadores e recentes). O backlog fica em Redis ou Postgres, e o cliente recupera pelo último id por long polling.

**Misskey (TypeScript)**
- **Criação:** em processo, sem `await` (fire-and-forget).
- **Armazenamento e não lidos:** Redis Streams por usuário, com marcador `latestReadNotification`.
- **Realtime:** pub/sub.
- **Garantias:** fracas; uma queda perde os timers pendentes.

**Filas no próprio banco**
- **procrastinate (Postgres):** LISTEN/NOTIFY acorda os workers, mas eles **ainda fazem polling periódico como garantia**.
- **PostgreSQL:** `SKIP LOCKED` existe para evitar contenção quando há vários consumidores numa tabela-fila.
- **SQLite:** com WAL, leitores e o escritor não se bloqueiam, mas há só um escritor.
- **SQLAlchemy:** em `after_commit` a sessão não pode emitir SQL.

**Padrões recorrentes:**
1. O banco é a fonte da verdade, e o realtime é uma dica descartável.
2. O trabalho acontece depois do commit e fora da requisição.
3. A deduplicação é semântica (por chave de evento), sem depender de o transporte entregar exatamente uma vez.
4. Os não lidos são contados por marcador monotônico, sob demanda e com limite.
5. O payload de realtime carrega estado, não delta.
6. A varredura periódica continua como rede de segurança mesmo havendo push.

## 3. Proposta

1. **Remover o consumo da outbox do middleware** (`main.py`). O middleware fica só com `Cache-Control`.
2. **Dispatcher em processo:** uma task asyncio iniciada no startup e parada no shutdown, que executa `run_once()` (hoje `drain_notification_outbox`) em thread, com sessão própria, lotes pequenos e transações curtas.
   - Intervalo configurável `MYGLICO_NOTIFICATION_DISPATCH_INTERVAL_SECONDS` (padrão 5) e opção para desligar o loop em testes.
   - O código fica isolado para poder virar processo/CLI separado sem refatorar.
3. **Sinal pós-commit.** Um listener `after_flush` marca `session.info` quando há `NotificationOutbox` nova, e o `after_commit` só **sinaliza** o dispatcher (`loop.call_soon_threadsafe(event.set)`), sem SQL. A varredura periódica cobre sinal perdido, queda do processo e `next_attempt_at` vencido.
4. **Lease.** Migração 0012 com `locked_until` e `claimed_by` em `notification_outbox`, e índice em (`status`, `next_attempt_at`).
   - **Reserva:** numa transação curta, `SELECT … WHERE status='PENDING' AND due AND (locked_until IS NULL OR locked_until < now) … FOR UPDATE SKIP LOCKED`. O `FOR UPDATE SKIP LOCKED` tem efeito em Postgres e MySQL 8 e é ignorado no SQLite. Em seguida, `UPDATE` de `locked_until`/`claimed_by` e commit.
   - **Processamento:** fora da transação de reserva. Depois, uma transação curta grava o resultado (DELIVERED ou retry) e limpa o lease.
   - **Recuperação:** um lease vencido é reivindicado de novo.
   - Não se usa `UPDATE … RETURNING` porque o MySQL não o suporta.
5. **Limite de tentativas:** depois de N falhas (proposta: 10), status `FAILED`, que funciona como dead letter. O backoff exponencial é mantido.
6. **PRAGMAs do SQLite**, aplicados só para SQLite num listener `connect` do engine: `journal_mode=WAL`, `busy_timeout=5000` e `synchronous=NORMAL`.
7. **Testes:**
   - a requisição não drena mais a outbox;
   - o dispatcher entrega e é idempotente (sem duplicar notificação);
   - falha e retry mantêm a evidência da CSCW-CA-29;
   - um lease vencido é retomado;
   - o status FAILED aparece depois de N falhas;
   - a suíte E2E completa roda várias vezes sem `database is locked`.

**Fora do escopo agora, registrado como futuro:**
- realtime por push (SSE/WebSocket); o polling atual já recupera pelo banco;
- trocar `read_at` das notificações por marcador;
- `dedupe_key` única em `notifications`.

Nenhum desses é exigido pelos critérios AUT/CSCW.

## 4. Questões para o parecer

1. O diagnóstico está correto e completo? Há outras causas plausíveis do `database is locked`?
2. A proposta atende ao SDD2 (publicação após commit, outbox/retry, deduplicação, falha do canal sem perder avisos nem contadores) e preserva as evidências da CSCW-CA-29, 39–44 e 45?
3. Um worker em processo (task no startup) é adequado com vários workers uvicorn e com o reload do dev? Riscos de duplicidade? O lease + SKIP LOCKED basta?
4. A reserva proposta é correta e portável em SQLite, MySQL 8 e Postgres? Há riscos de corrida, de relógio (`now` do app vs. do banco) ou de transação longa?
5. O sinal via `after_commit` é seguro (threads, sessões dos testes, `TestClient`)? Vale a pena ou basta a varredura?
6. Os PRAGMAs do SQLite têm efeitos colaterais (arquivos `-wal`/`-shm`, `.gitignore`, backup/VACUUM documentados no README, bancos de teste descartáveis)?
7. Algo do "fora do escopo" deveria entrar agora para a solução ser de fato escalável?
8. Alternativas melhores ou mais simples que a proposta deveria considerar?

## Fontes

- Mastodon:
  - `app/services/notify_service.rb`
  - `app/workers/local_notification_worker.rb`
  - `app/models/notification.rb`
  - `app/models/concerns/notification/groups.rb`
  - `app/services/favourite_service.rb`
  - `app/models/marker.rb`
  - docs.joinmastodon.org (streaming, grouped_notifications)
- Discourse:
  - `app/models/notification.rb`
  - `app/models/user.rb`
  - `app/services/post_alerter.rb`
  - `app/jobs/regular/post_alert.rb`
  - `lib/post_jobs_enqueuer.rb`
  - `app/jobs/base.rb`
  - README do `message_bus`
- Misskey:
  - `packages/backend/src/core/NotificationService.ts`
  - `ReactionService.ts`
  - `GlobalEventService.ts`
- Documentação:
  - procrastinate.readthedocs.io (discussions)
  - postgresql.org/docs/current/sql-select.html
  - sqlite.org/wal.html
  - docs.sqlalchemy.org/en/20/orm/events.html
