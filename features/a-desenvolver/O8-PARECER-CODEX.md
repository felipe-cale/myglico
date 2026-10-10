# Parecer independente O8 — dispatcher da outbox de notificações

**Avaliador:** Codex  
**Status analisado:** proposta, sem implementação avaliada  
**Recomendação:** **APROVAR COM AJUSTES**

## Síntese

O diagnóstico central é plausível e a retirada do dreno do middleware é recomendável: hoje cada resposta `/api/*` pode provocar leitura, atualização de tentativas e commit em outra sessão, e SQLite continua tendo um único escritor. O worker periódico reduz esse trabalho acoplado à latência das requisições. Entretanto, a proposta ainda não especifica uma reivindicação atômica portátil, o que é necessário antes de afirmar segurança com múltiplos workers. O `SKIP LOCKED` não resolve isso no SQLite, onde é ignorado.

Há também uma distinção de semântica a preservar: `notifications` é a própria inbox persistida, lida diretamente pela API. O consumidor atual não publica em um canal externo; ele confirma que a conta destinatária existe e atualiza o estado da outbox. Assim, falha do consumidor não remove o aviso já persistido. A proposta melhora operação e estado de processamento, mas não transforma essa outbox em transporte real-time nem deve passar a condicionar a visibilidade da inbox ao `DELIVERED`.

## Fatos verificados no repositório

- `app/main.py:34-53` chama `drain_notification_outbox` depois de cada resposta `/api/*`, em sessão própria; exceções são registradas e não mudam a resposta.
- `app/services/notification_outbox.py:17-20, 23-72` valida a existência de `UserAccount`, tenta até 100 linhas, incrementa tentativas e grava sucesso ou retry. Não há chamada a serviço externo de notificação. O `FOR UPDATE SKIP LOCKED` está presente, mas SQLite não o aplica.
- `app/models/entities.py:180-207` define a notificação durável com `read_at` por linha e outbox única por `notification_id`; ainda não existem lease nem estado terminal de falha.
- Os produtores adicionam `Notification` e `NotificationOutbox` à mesma sessão da mutação/evento e fazem commit no serviço: `app/services/doctor_links.py:127-145`; `app/services/investigations.py:301-320` e `_add_notification` (ver linhas próximas ao início do serviço).
- `app/db/session.py:13-35` configura `check_same_thread=False` para SQLite, mas não configura `busy_timeout`, WAL ou outra serialização de escritores.
- A integração CSCW-CA-29 força uma falha no consumidor, observa `PENDING` e retry e verifica uma única linha de inbox (`tests/integration/test_outbox_and_delivery.py:15-69`). O teste também confirma que essa falha é no caminho de processamento, não em um transporte externo.
- CSCW-CA-39–43 medem persistência e os dois marcadores/contadores; CSCW-CA-44 derruba chamadas de polling no navegador e recupera o estado pelo banco após reconexão; CSCW-CA-45 cobre agrupamento/deduplicação histórica. As evidências estão em `features/a-desenvolver/MATRIZ-ACEITE.md:107-113` e no SDD2, em especial seções 10.4 e 11.2–11.4.
- O SDD2 requer commit atômico, publicação após commit, consumidor idempotente, retry persistente e revalidação de autorização de avisos enfileirados (`.../MyGlico_SDD_Vinculos_CSCW_Proveniencia.md:497-507, 594-606`). Os contadores de mensagens vêm da conversa/marcador, não do estado de entrega da notificação.

## Respostas às oito questões

### 1. Diagnóstico e causas de `database is locked`

**Fato:** o middleware está no caminho de toda resposta de API e abre uma sessão adicional. Quando há linhas elegíveis, `drain_notification_outbox` modifica `attempts` e estado; em concorrência isso adiciona escritores ao SQLite. `check_same_thread=False` permite uso da conexão em thread diferente, mas não serializa transações. O código não define `busy_timeout`.

**Parecer:** o diagnóstico está correto, mas não prova que o middleware seja a única causa. Outras causas plausíveis são: concorrência entre rotas de escrita e o dreno; mais de um cliente/processo/worker compartilhando o mesmo arquivo SQLite; transações mantidas abertas por outras operações; importação/migração simultânea; e drenos concorrentes que selecionam o mesmo conjunto porque SQLite ignora `SKIP LOCKED`. O commit incondicional não necessariamente escreve se nenhum objeto foi alterado, então “cada requisição faz uma transação de escrita” é forte demais: a sessão extra é certa, a escrita ocorre quando há itens processados/alterados. O relato de falha intermitente sob carga é compatível com a hipótese, não a isola causalmente.

### 2. SDD2 e critérios CSCW

**Parecer:** a arquitetura proposta pode preservar o SDD2, desde que a mutação, o evento de proveniência, `Notification` e `NotificationOutbox` continuem no mesmo commit, e nenhum sucesso seja reportado antes dele. O consumidor assíncrono deve tratar entrega como *at least once* e manter os efeitos idempotentes. Como a inbox já é `notifications`, não deve apagar/ocultar o aviso quando houver erro de processamento.

CSCW-CA-29 continua coberto se o teste passar a chamar o worker/`run_once` explicitamente: falha com evidência persistida, retry depois do vencimento e uma única notificação visível. CSCW-CA-39–43 permanecem independentes do dispatcher: os contadores de mensagens devem continuar baseados nos marcadores por conversa e não podem esperar a outbox. CSCW-CA-44 continua baseado em leitura posterior persistida; polling indisponível não pode afetar os registros. CSCW-CA-45 deve conservar consolidação e idempotência dos produtores de convites/importação. Nenhum desses critérios exige SSE/WebSocket ou trocar `read_at` por marcador.

**Ajuste necessário:** tornar explícito no SDD/nomes/logs que “DELIVERED” significa confirmação do processamento/da inbox interna atual, não entrega a dispositivo/canal externo. Se não existir etapa de publicação externa, nomear o resultado como `PROCESSED` seria semanticamente mais fiel, mas isso é uma mudança de contrato/dados e exige decisão própria e migração; não é pré-requisito para O8.

### 3. Task no processo, workers Uvicorn e reload

**Parecer:** task de lifespan é aceitável para o MVP se o worker for curto, idempotente e coordenado pelo banco. Em produção, cada worker Uvicorn inicia sua própria task; reload pode encerrar e criar processos/tasks repetidamente. Isso é normal apenas se startup/shutdown forem idempotentes, o cancelamento aguardar a task, e claims impedirem dois processos de completar o mesmo item.

Lease + `SKIP LOCKED` basta para concorrentes em PostgreSQL e MySQL 8 quando a reivindicação ocorre numa transação e o banco oferece o bloqueio esperado; não basta, isoladamente, em SQLite. O resultado também precisa ser protegido por token/fencing: um worker cujo lease expirou não pode sobrescrever o resultado de uma nova reivindicação. Se a instalação usar SQLite, documentar/configurar um único processo API ou provar a reserva por atualização condicional e tratamento de `database is locked`. SQLite não é uma opção de escala horizontal adequada para várias instâncias.

O README descreve deployment Vercel serverless, onde processos podem ser efêmeros e instâncias sobem sob demanda. Um loop de polling em lifespan nesse ambiente não é consumidor durável nem tem garantia de execução contínua. A task deve poder ser desligada por configuração nesse runtime; usar processo/CLI/worker persistente separado é a alternativa de produção quando a entrega em background for necessária.

### 4. Correção e portabilidade da reserva

**Parecer:** a intenção é correta, a sequência proposta precisa de uma especificação mais forte.

1. Em Postgres/MySQL 8, dentro de transação curta, selecionar linhas vencidas com lock e `SKIP LOCKED`, gravar claim/expiração e confirmar; então processar fora da transação longa. O update final deve incluir `id`, `claimed_by` (token único daquela reivindicação) e estado pendente na cláusula `WHERE`, limpando o lease somente se o token ainda corresponder.
2. No SQLite, `SELECT` seguido de `UPDATE` não é claim exclusivo; `SKIP LOCKED` é ignorado. Use uma estratégia SQLite específica, por exemplo update condicional/claim compare-and-set e valide `rowcount`, sob tratamento/retry de `SQLITE_BUSY`; ou limite explicitamente a um único consumidor. A garantia deve ser testada com dois consumidores concorrentes.
3. Defina quando `attempts` é incrementado: claim, início efetivo do processamento ou falha concluída. Uma queda após claim deve ter semântica clara e, se consumir tentativa, deve levar eventualmente a `FAILED` após N tentativas.
4. Use um token de claim e lease maior que o timeout máximo do processamento, ou renovação do lease se o trabalho puder demorar. Sem fencing, worker lento pode terminar depois de outro ter recuperado o lease.
5. Relógios de aplicação e banco podem divergir. Prefira um único relógio de referência (expressão UTC do banco por dialeto ou `now` injetado e coerente em todas as operações), persista timestamps em UTC e mantenha lease conservador. Não misture datetimes naive/aware. Backoff e `next_attempt_at` precisam seguir a mesma convenção.

Índice composto `(status, next_attempt_at)` é razoável, mas deve ser confirmado contra a consulta real; filtros por lease e ordenação por `created_at,id` podem justificar índice adicional. A migração 0012 precisa declarar DDL explícito, manter compatibilidade SQLite/MySQL e seguir a regra do README de não editar migrações aplicadas.

### 5. Sinal `after_commit`

**Parecer:** é uma otimização opcional, não requisito de correção. A varredura periódica é suficiente e mais simples; o custo é até o intervalo configurado de atraso. Para este produto, a notificação já existe na base imediatamente após o commit, e a UI usa polling; o sinal só antecipa a atualização de status de processamento, não torna o aviso visível.

Um listener global ligado a sessão/engine e uma referência global ao event loop complica testes, `TestClient`, múltiplas instâncias ASGI e sessões executadas em threads. `after_commit` não deve executar SQL e `call_soon_threadsafe` é a chamada correta para atravessar a fronteira de thread, mas é preciso lidar com loop inexistente/encerrado e múltiplos lifespans. Se mantido, prefira um hook local e explícito que sinalize `app.state` após o commit do produtor, sem acoplamento global ao ORM. Minha recomendação para O8 é remover esse item da primeira versão e iniciar com polling periódico configurável.

### 6. Efeitos colaterais de WAL/PRAGMAs SQLite

WAL permite leitores enquanto há escritor, mas mantém um único escritor; não elimina contenção entre o worker e rotas de escrita. `busy_timeout` aguarda por bloqueio e pode reduzir erros transitórios, mas aumenta a latência máxima e não substitui transações curtas/serialização.

`journal_mode=WAL` cria arquivos auxiliares `-wal` e `-shm`; o WAL é persistência ativa e não deve ser descartado durante uso. O padrão `.gitignore` ignora `data/*.db` e `data/*.sqlite3`, mas não documenta padrões explícitos para sidecars. A ativação deve ocorrer com cuidado (preferencialmente em inicialização controlada; não disputar mudança de journal mode em cada conexão concorrente). `synchronous=NORMAL` melhora desempenho com tradeoff de durabilidade em queda de energia do sistema, embora commits normais continuem protegidos pelo WAL; deixar essa escolha documentada.

Adicionar exclusões de sidecars e orientar que backup copie um snapshot consistente (ou use a API de backup/checkpoint), não apenas o arquivo principal enquanto o banco está aberto. `VACUUM` deve ocorrer com conexões fechadas; checkpoint/gestão do WAL e teste em bancos descartáveis devem ser descritos no README. Testes/E2E devem seguir o escopo: banco descartável em `%TEMP%`, e não `data/*.db`.

### 7. Escopo futuro a antecipar

Não incluir push em tempo real, marcador de leitura de notificação ou novo `dedupe_key` no O8: o banco já é fonte da verdade, CSCW-CA-44 exige recuperação por consulta e os contadores estão corretamente separados. A adição de entrega externa via e-mail/push não foi pedida pelo SDD2 como critério atual.

Para escalabilidade, o ponto a incluir agora é operacional, não uma nova feature: worker desligável, métricas/logs de idade da mensagem mais antiga, profundidade por status, taxa de retry e `FAILED`; política de retenção/reprocessamento manual; configuração de limite, intervalo, timeout e máximo de tentativas. `FAILED` sem alerta/visibilidade é apenas uma forma silenciosa de perda operacional. Também declarar o limite de concorrência do SQLite e a topologia serverless.

### 8. Alternativas mais simples

Para a escala deste MVP, a opção mais simples e suficiente é remover o dreno do middleware e criar um `run_once(limit)` invocado por um loop de lifespan com polling, sessão própria por lote, intervalo configurável e retry. Se houver um único worker, não é necessário implementar lease inicialmente; mas essa limitação deve ser imposta/documentada, e configuração futura multi-worker não pode ser presumida segura.

Se múltiplos workers/instâncias forem requisito já, prefira um worker/CLI separado e persistente em vez de uma task por API worker. Reutilize a tabela outbox no banco, implementando claims com as semânticas específicas de Postgres/MySQL e SQLite. Um broker externo aumenta operação e não é necessário para esta inbox, que já é persistida no banco. A escolha de fila deve seguir necessidade real de escala/latência, não a presença de exemplos em redes sociais.

## Classificação dos itens da proposta

| Item | Parecer | Ajuste ou justificativa |
|---|---|---|
| 1. Retirar o dreno do middleware | **Manter** | Manter no middleware apenas responsabilidades HTTP/cache; persistência de aviso não depende do dreno. |
| 2. Dispatcher em processo e `run_once` | **Ajustar** | Implementar primeiro loop de polling em lifespan, task cancelável e sessão curta própria. Torná-lo configurável/desligável, especialmente em Vercel; explicitar que cada worker inicia um loop. Preferir worker/CLI separado quando houver topologia horizontal. |
| 3. Sinal `after_flush`/`after_commit` | **Remover da primeira versão** | Polling periódico cobre correção e recuperação com menor acoplamento e menor fragilidade em threads/testes. Reavaliar só se a latência medida justificar. |
| 4. Lease + `SKIP LOCKED` | **Ajustar** | Obrigatório para concorrência multiworker, mas claim atômico específico por dialeto, token de fencing, validação de `rowcount`, expiração e teste concorrente SQLite incluídos. `SKIP LOCKED` sozinho não cobre SQLite. |
| 5. Máximo de tentativas/`FAILED` | **Ajustar** | Manter limite configurável e estado terminal, com alerta/consulta/reprocessamento operacional; definir a semântica de tentativas em quedas e erros permanentes. |
| 6. PRAGMAs SQLite | **Ajustar** | `busy_timeout` é razoável; WAL é opção de desenvolvimento/teste que deve ser medida e habilitada com cuidado, não solução de concorrência. Documentar sidecars, backup, checkpoint/VACUUM e `synchronous=NORMAL`. |
| 7. Testes | **Ajustar** | Manter todos os cenários, mas retirar dependência de middleware e acrescentar concorrência de claim em SQLite e banco de produção suportado; validar startup/shutdown, retry/lease expirado, stale worker/fencing, `FAILED` e configuração desativada. Não afirmar “sem locked” apenas pela suíte E2E: medir/repetir sob concorrência em banco descartável. |
| Fora de escopo: push/realtime | **Manter fora** | CSCW-CA-44 prova recuperação persistida por polling; push não é necessário para O8. |
| Fora de escopo: marcador de leitura de notificação | **Manter fora** | Contagem/notificação lida e mensagens não lidas têm semânticas diferentes já exigidas pelo SDD2 e pelos CA-41/43. |
| Fora de escopo: `dedupe_key` em `notifications` | **Manter fora, com condição** | A idempotência atual dos produtores e a constraint da outbox são suficientes para este refactor; se novos produtores assíncronos criarem eventos repetíveis, definir chave semântica e constraint como mudança separada. |

## Riscos e correções

| Gravidade | Risco / fato | Correção recomendada | Referência |
|---|---|---|---|
| **Alta** | Claims duplicados no SQLite; `SKIP LOCKED` ignorado e `SELECT` + update proposto não é atômico. | Implementar claim compare-and-set específico para SQLite ou impor um consumidor único; concorrência testada. | `app/services/notification_outbox.py:33-43`; `app/db/session.py:13-35` |
| **Alta** | Cada worker Uvicorn criaria uma task; Vercel é serverless e não mantém loop durável. | Configuração para desativar; documentar topologia de worker persistente para background real; evitar duplicar processamento por lifespan. | `app/main.py:20-31`; `README.md`, “Deployment on Vercel” |
| **Alta** | Worker com lease vencido pode finalizar depois do reclaim e sobrescrever o resultado mais recente. | Token de claim/fencing em update final; transição condicional por token e status. | Proposta item 4; `NotificationOutbox` atual em `app/models/entities.py:196-207` |
| **Média** | `FAILED` pode virar dead letter invisível e ser confundido com aviso perdido. | Expor contagem/idade por status, alerta e procedimento seguro de replay; manter a inbox persistida independente. | Proposta item 5; SDD2 `:501-507, 597-599` |
| **Média** | A descrição “entrega” sugere canal externo, mas implementação apenas verifica destinatário. | Definir semântica/documentar status; não condicionar leitura ou contadores a `DELIVERED`. | `app/services/notification_outbox.py:17-30, 65-70`; `app/models/entities.py:180-207` |
| **Média** | Relógios e tentativas no claim/retry podem gerar expiração prematura ou limite incoerente. | UTC consistente, semântica de `attempts` definida e fencing; avaliar relógio do banco para reserva. | `app/services/notification_outbox.py:32, 55-57`; proposta item 4 |
| **Média** | WAL cria arquivos de estado e cópia ingênua do `.db` pode perder alterações ainda no WAL; timeout não remove contenção. | Documentar backup/checkpoint/VACUUM, ignorar sidecars e testar WAL; não apresentar como correção de múltiplos escritores. | `app/db/session.py:13-35`; `.gitignore:8-9`; `README.md`, notas SQLite |
| **Baixa** | Hook global `after_commit`/event loop pode falhar em testes, reload e múltiplos lifespans. | Omitir na primeira versão; se necessário, sinal explícito no lifespan com fallback de polling. | Proposta item 3; `app/main.py:29-31` |

## Recomendação final

**APROVAR COM AJUSTES**, obrigatoriamente:

1. Retirar o dreno síncrono do middleware e usar dispatcher com polling periódico, ciclo de vida cancelável e configuração que permita desligá-lo em testes e runtime serverless.
2. Antes de declarar suporte a múltiplos consumidores, especificar e implementar claim atômico por banco; SQLite precisa de caminho próprio ou limite explícito de consumidor único. Incluir token de fencing para impedir conclusão por claim vencido.
3. Preservar a atomicidade produtor + evento + notificação + outbox e a leitura da inbox/contadores diretamente da persistência, independentemente de `DELIVERED`.
4. Definir tentativas, dead letter, métricas/alerta e procedimento de replay; configurar clocks e timestamps em UTC.
5. Adiar o hook `after_commit`; tratar WAL/PRAGMAs como ajuste opcional e documentar sidecars, backups e manutenção no README.
6. Atualizar o teste CSCW-CA-29 para invocar o consumidor diretamente e adicionar testes concorrentes de claim/lease (incluindo SQLite); manter as evidências de CSCW-CA-39–45 sem acoplar os contadores ao dispatcher.

