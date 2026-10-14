# Relatório de implementação — backend Glico F1

**Data:** 2026-10-13  
**Branch:** `codex/glico-fase1`  
**Status:** correções do parecer backend aplicadas; F1 ainda não aprovada para liberação.

## Correções desta rodada

- Upload de imagem/áudio exige `X-Glico-Context-Version` correspondente à conversa e UUID em `X-Glico-Request-Id` antes de consumir o corpo. A rota congela versão, paciente, associação, papel e owner antes do worker e compara com a autorização revalidada após a inferência.
- O gateway seleciona `/internal/extract/image` ou `/internal/extract/audio`, assina método/path/timestamp/nonce/digest por HMAC, desativa redirects e limita corpo, resposta e timeout. Áudio também fica desligado por padrão; capability só é anunciada quando flag, URL, segredo com comprimento válido e quota global estão configurados. ASR retorna apenas resposta tipada/proposta, sem eco de transcrição.
- Consultas FAQ e listagem limitada de pacientes vinculados funcionam em conversa médica sem paciente selecionado. Propostas de glicemia continuam vedadas ao médico. `period_end` é aplicado mesmo sem `period_start`; seleção de intervalo segue limitada a 366 dias.
- Mensagens persistem resposta de idempotência cifrada por 24 horas; retries iguais devolvem a resposta original, payload diferente conflita e pedido inválido/contexto/CSRF inválido não debita quota. Após TTL, o identificador pode ser reutilizado. Criação de conversa retorna `capabilities` também em repetição.
- Migração `20261013_0017` persiste recibos de retry; a quota global da migração `0016` contém buckets de imagem e áudio. As quotas de mídia continuam compartilhadas no banco. Como cada áudio está limitado a 60 segundos e há no máximo cinco jobs/dia por conta, o limite agregado superior é cinco minutos/dia.
- Adicionado harness de backend real em `scripts/glico_e2e_backend.py`: prepara SQLite temporário, aplica `alembic upgrade head`, verifica `PRAGMA foreign_keys=1`, sobe Uvicorn, cria paciente, médico vinculado e médico sem vínculo, e imprime uma linha JSON com URL e credenciais descartáveis. Encerra ao receber Ctrl+C/SIGTERM; o processo pytest também encerra apenas o PID filho que iniciou.

## E2E real e uso pelo Playwright

Executado contra Uvicorn por HTTP loopback (não `TestClient`):

```powershell
python -m pytest tests/e2e/test_glico_live_api.py -q
```

Resultado: **1 passed**. O fluxo cobre conversa, mensagem e replay, proposta, edição versionada, confirmação e replay de receipt, criação de `glucose_record`, `GlucoseRecordSource` (`glico_text`) e evento de proveniência, cancelamento idempotente e 404 para médico sem vínculo.

Para a suíte Playwright, em um terminal na raiz:

```powershell
python scripts/glico_e2e_backend.py --port 8012
```

O script imprime a configuração JSON de fixture (URL `http://127.0.0.1:8012`, caminho SQLite, emails e senhas de teste) após o seed. Em outro terminal:

```powershell
cd frontend-react
$env:VITE_API_TARGET = 'http://127.0.0.1:8012'
npm run dev
```

Abra `http://localhost:8000` no navegador Playwright. O proxy preserva `Host` para a validação de origem/CSRF. Encerre o fixture com Ctrl+C; o banco e diretórios temporários são removidos no encerramento normal.

## Validação executada

- `python -m pytest tests/integration/test_glico_foundation.py -q`: **15 passed** em SQLite temporário com FK ON. Inclui CSRF/autorização, contexto durante worker simulado, headers ausentes/inválidos, MIME/tamanho, HMAC do gateway, áudio sem echo e retry sem segunda inferência, idempotência/quota, TTL de proposta/recibo, concorrência de confirmação, FAQ, consulta e colaboração.
- `python -m pytest tests/e2e/test_glico_live_api.py -q`: **1 passed** no backend real iniciado pelo harness acima.
- `docker compose ps`: não conseguiu ler `C:\Users\felip\.docker\config.json` (acesso negado); MySQL 8 não estava acessível e a migração não foi exercitada nele.
- Execução ampla anterior de `python -m pytest tests/integration -q`: **81 passed, 8 errors** em setup UCI/PROV por caminho Windows inválido (`\\Users\\...` sem unidade). Esses erros não são apresentados como sucesso e não foram corrigidos neste escopo.

## Limites restantes

- O worker e modelos reais de OCR/ASR não foram iniciados nesta máquina. O teste de corrida usa worker simulado e comprova que mudança de contexto durante inferência impede proposta. Mídia segue fail-closed até provisionamento explícito da URL/segredo, flags e quota.
- O harness real verificou o fluxo de API; a página React/Playwright ainda precisa executar o fluxo visual completo nos breakpoints e locales. O comando de frontend acima aponta para o mesmo backend e seed.
- MySQL 8 continua pendente por indisponibilidade de Docker. A revisão independente mantém a fase como não aprovada até todos os critérios da matriz, inclusive UI, workers e validação MySQL, terem evidência.

## Rodada 2 — validação backend (2026-10-14)

### Alterações e cobertura adicionada

- `tests/integration/test_glico_foundation.py`: o teste de concorrência de confirmação agora dispara 10 requests paralelos, exige receipts idênticos e um único efeito persistido. Em SQLite local, os 10 requests passaram.
- Adicionados testes para respostas Glico `Cache-Control: no-store, private`, rejeição de `Origin: null` e token CSRF incorreto, e equivalência de 404 para conversa/proposta alheias e inexistentes. A verificação IDOR adicionada cobre leitura de conversa/proposta e envio de mensagem; não equivale a uma campanha para cada ID/endpoint da matriz.
- Adicionado teste do endpoint PDF autenticado nos idiomas `pt-BR`, `en-US` e `es`, com período explícito e cabeçalho sem cache.
- Cobertura já existente e exercitada na fundação: propostas de colaboração só abrem investigação/mensagem após confirmação explícita; quotas de reserva de imagem/áudio liberadas em sucesso, erro, timeout e cancelamento; TTL/cleanup de replay; HMAC/replay concorrente do worker. Rotas de investigação seguem em `app/api/routes.py` e PDF em `/api/patients/{patient_id}/report.pdf`; consulta Glico oferece resposta orientativa e consulta limitada por contexto/período, mas não aciona download silencioso.

### Comandos executados nesta rodada

| Comando | Resultado observado |
|---|---|
| `docker compose up -d db` (com chaves hex temporárias apenas no ambiente do processo) | Não iniciado: `//./pipe/docker_engine` inexistente. `com.docker.service` estava `Stopped`; tentativa de iniciar o serviço também falhou por não conseguir abrir o serviço. Nenhum container/volume foi removido. |
| `python -m pytest tests/integration/test_glico_foundation.py -q` | **41 passed** (SQLite isolado, FK ON), após os testes adicionados. |
| `python -m pytest tests/integration -q` | **117 passed, 5 warnings** em 163.04s, antes das adições finais de testes. |
| `python -m pytest -q` | Primeira execução: **144 passed, 5 warnings** em 208.52s. Reexecução após todos os testes desta rodada, inclusive PDF trilingue: **147 passed, 5 warnings** em 237.95s. |

### Lacunas que permanecem

- MySQL 8, migrações 0014–0017 e concorrência de confirmação/quota em MySQL não foram executados: daemon Docker indisponível, apesar da autorização e da tentativa de acesso elevada. Os resultados SQLite não são evidência de concorrência MySQL.
- Os testes novos de IDOR cobrem alguns recursos Glico, não todos os IDs `conversation/proposal/attempt` em todas as rotas exigidas por GLI-CA-001..021. Origin adversário e token incorreto foram exercitados; Origin ausente e header interno forjado contra todas as rotas ainda requerem matriz adversarial completa.
- HMAC incorreto/path, replay, TTL, quota global concorrente e liberação de reserva têm testes de componentes/fundação, mas não todos foram repetidos em MySQL ou contra processo worker real nesta rodada. Os critérios correspondentes continuam sem aprovação na matriz.
- A implementação do PDF recebe período e idioma no backend e o teste adicionado verifica os três locales; o fluxo visual/integrado da página React não foi testado por esta tarefa backend.
- Nenhuma linha da `MATRIZ-ACEITE.md` foi marcada como aprovada.

## Rodada 2b — validação MySQL 8 (2026-10-14)

### Ambiente e migrações

- `docker compose up -d db`: container `myglico-db` iniciado; `docker compose ps db` mostrou **Up (healthy)**. Versão consultada no servidor: **MySQL 8.4.10**.
- A base compartilhada preexistente `myglico` estava em `20260504_0002`, com 15 tabelas. Não foi migrada nem limpa. Todos os testes usaram schemas novos com `utf8mb4_unicode_ci` e `foreign_key_checks=1`.
- Schema vazio: `MYGLICO_DATABASE_URL=mysql+pymysql://myglico:***@127.0.0.1:3307/myglico_f1_2b_zero_20261014?charset=utf8mb4 python -m alembic upgrade head` — sucesso, executou `0001` a `0017`.
- Schema baseline: `MYGLICO_DATABASE_URL=mysql+pymysql://myglico:***@127.0.0.1:3307/myglico_f1_2b_baseline_20261014?charset=utf8mb4 python -m alembic upgrade 20261012_0013`, seguido de `... python -m alembic upgrade head` — ambos concluídos; head `20261013_0017`.
- Um primeiro upgrade dos schemas temporários retornou `1044 Access denied`: o usuário de aplicação só tinha grant na base preexistente. O administrador concedeu permissão apenas nos schemas temporários criados para esta rodada; após os testes, esses cinco schemas foram removidos.

### Falhas MySQL encontradas e correções

- Primeira execução focal: **35 passed, 6 failed**. As falhas identificaram comportamento específico do MySQL/InnoDB:
  - `app/services/glico.py`: `invalidate_proposals` gerava subquery `UPDATE glico_proposals ... WHERE id IN (SELECT ... FROM glico_proposals)`, rejeitada por MySQL `1093`. Agora materializa IDs antes do `UPDATE`.
  - `app/services/glico.py` e `app/api/glico_routes.py`: updates sem mudança de `status='ACTIVE'` podiam ter `rowcount=0`; a seleção/autorizacão agora usa `SELECT ... FOR UPDATE` e não interpreta rowcount de no-op como revogação.
  - `app/api/glico_routes.py`: durante confirmações concorrentes, um snapshot REPEATABLE READ antigo não via o receipt da transação que acabara de confirmar. A leitura de execution no ramo já executado agora é locking/current read.
  - A fixture de rollback tentou criar trigger em servidor com binary logging e recebeu `1419` (ausência de SUPER). Para esta execução, `log_bin_trust_function_creators` foi temporariamente ativado como administrador e restaurado para OFF ao fim. Nenhuma configuração permanente foi gravada.
- `tests/integration/conftest.py` aceita `MYGLICO_INTEGRATION_RAISE_SERVER_EXCEPTIONS=true` para depurar exceções ASGI sem mascará-las como 500; o padrão permanece sem propagação.
- A cobertura adversarial ampliada inclui IDs de conversa e proposta estrangeiros em leitura, contexto, mensagem, colaboração, extração de imagem/áudio, edição, confirmação e cancelamento; adiciona serialização da quota global de imagem com oito contas concorrentes (teste executado apenas em MySQL).

### Resultados finais

| Comando | Resultado observado |
|---|---|
| `MYGLICO_INTEGRATION_DATABASE_URL=mysql+pymysql://myglico:***@127.0.0.1:3307/myglico_f1_2b_foundation_20261014?charset=utf8mb4 python -m pytest tests/integration/test_glico_foundation.py -q` | **42 passed** em MySQL 8.4.10, incluindo 10 confirmações concorrentes e quota global entre contas. |
| `MYGLICO_INTEGRATION_DATABASE_URL=mysql+pymysql://myglico:***@127.0.0.1:3307/myglico_f1_2b_suite_final_20261014?charset=utf8mb4 python -m pytest tests/integration -q` | **123 passed, 5 warnings** em 211.28s, em schema limpo migrado até `20261013_0017`. |
| `python -m pytest tests/integration/test_glico_foundation.py -q` | **41 passed, 1 skipped** em SQLite; o teste de serialização de quota por row lock é marcado MySQL-only. |
| `docker compose stop db` | Concluído; `docker compose ps db` não listou container em execução. Container/volume do projeto não foram removidos. |

As cinco warnings são uma advertência do `joblib` sobre detecção de cores físicos no Windows e quatro `ConvergenceWarning` do scikit-learn por haver duas observações distintas para três clusters. Nenhuma linha da matriz foi marcada como aprovada; as lacunas fora do escopo de MySQL permanecem.
