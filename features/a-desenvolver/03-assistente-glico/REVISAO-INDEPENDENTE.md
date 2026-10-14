# Revisão independente — Assistente Glico F1

**Data:** 2026-10-13  
**Branch:** `codex/glico-fase1`  
**Escopo observado:** backend, migração `20261013_0014`, testes de integração Glico, tela/API React e locales. A árvore está em andamento e contém numerosas alterações locais; nenhuma foi modificada por esta revisão, exceto este parecer.

## Parecer

**F1 não está pronta para aceite/liberação.** Há um bloqueador de segurança no caminho de mídia: a extração não valida a versão de contexto enviada pelo cliente e a verificação pós-worker compara valores que são recarregados do mesmo estado atualizado. Uma alteração de paciente/contexto durante a inferência pode, portanto, deixar passar uma resposta calculada para contexto obsoleto. Também faltam partes funcionais normativas F1 (áudio, consultas completas e PDF integrado). A matriz continua marcando todos os critérios como “Não executado”; não encontrei critério marcado aprovado sem evidência.

## Bloqueadores

1. **A extração de mídia não vincula o trabalho ao contexto/request do cliente nem revalida o snapshot inicial.** `app/api/glico_routes.py:697-711` verifica sessão/CSRF e vínculo, mas ignora `X-Glico-Context-Version` e `X-Glico-Request-Id`, embora o cliente os envie (`frontend-react/src/api.js:266-278`) e o contrato de upload os exija. Após a chamada externa, `db.expire_all()` invalida `conversation`; a comparação em `app/api/glico_routes.py:772-776` então lê `conversation.context_version` e `conversation.patient_id` novamente do banco, tal como `current`. Assim a comparação não preserva o snapshot pré-inferência e pode aceitar resultado obsoleto após mudança de contexto. **Impacto:** associação de OCR ao contexto errado e propostas não idempotentes. **Exigir:** validar os dois headers antes de consumir bytes, copiar versão/paciente/associação antes do worker e comparar esses valores imutáveis após revalidar sessão, papel e vínculo; teste concorrente de mudança/revogação durante o worker.

2. **F1 está incompleta frente ao escopo especificado.** O endpoint de mídia declara áudio indisponível sem executar ASR (`app/api/glico_routes.py:697-711`, 704-710); capacidades sempre anunciam `audio: false` (`app/api/glico_routes.py:305-308`). O fluxo de mensagens rejeita conversa sem paciente antes de resolver FAQ/ajuda (`app/api/glico_routes.py:398-405`), contrariando a conversa médica sem contexto clínico com FAQ/listagem autorizada (SDD FUN-12). A tela Glico não implementa PDF nem consultas e colaboração fica sem interface operacional completa (`frontend-react/src/pages/GlicoAssistantPage.jsx`). SDD/contrato definem os incrementos F1.0–F1.4 como fase 1 completa; não há base para aprovar F1 com apenas partes da fundação/texto. **Ação:** manter estado de fase não aprovada; implementar e demonstrar cada capacidade normativa ou ajustar formalmente escopo/critério antes de declarar F1 concluída.

## Importantes

1. **Idempotência do envio de mensagens não é aplicada.** `client_request_id` é validado em `app/api/glico_routes.py:389-400`, mas não é gravado nem consultado; cada repetição pode consumir quota e criar nova proposta. O identificador existe no contrato e no payload da UI (`frontend-react/src/pages/GlicoAssistantPage.jsx`). Tornar retries do mesmo pedido idempotentes e testar repetição/concor­rência.

2. **Consultas de leituras ignoram `period_end` sem `period_start`.** Em `app/api/glico_routes.py:247-253`, o filtro final é condicionado à existência de `period_end`, mas seu limite inicial não é posto quando falta início; o contrato permite período opcional e consultas limitadas. Aplicar cada limite independentemente e validar a janela máxima de 366 dias também nas consultas.

3. **Evidência de backend parcial; migração de produção ainda sem verificação.** `tests/integration/test_glico_foundation.py` cobre confirmação/ownership/contexto e alguns casos de colaboração, mas não cobre a falha crítica do worker/contexto acima, ataques de mídia, ciclo de quota, TTL/cleanup, ausência de sessão, nem comportamento MySQL 8. A migração 0014 define tabelas/chaves e a fixture SQLite habilita FK (`tests/integration/conftest.py:149-153`), mas não houve execução MySQL. O SDD/decisão exige validação SQLite com FK ON e MySQL 8 antes de persistência ser considerada pronta.

4. **A interface não foi validada em navegador.** O build passou, mas não demonstra fluxos, acessibilidade, responsividade nos breakpoints e nos três idiomas nem revisão/captura/descartar de mídia real. Critérios UX da matriz continuam corretamente não executados.

## Menores

1. `app/api/glico_routes.py:143-199`: extração textual por regex é muito estreita para datas/unidades em formatos localizados e trata “HI/LO” em qualquer ocorrência do texto como sinal, não implementando os esclarecimentos completos SDD FUN-18–22. Restringir a oferta de proposta quando não houver interpretação segura e adicionar casos pt-BR/en-US/es.
2. `app/services/glico.py:161-187` e `app/api/glico_routes.py:389-410`: quota de mensagens é incrementada antes da validação de contexto e sem idempotência por request; pedidos inválidos podem consumir quota. Avaliar ordem/semântica e cobrir nos testes.
3. `app/api/glico_routes.py:311-333`: uma repetição idempotente de criação retorna a representação de conversa, enquanto a primeira resposta inclui `capabilities`; alinhar forma de resposta ao contrato.

## Segurança e privacidade observadas

- As rotas exigem sessão; mutações verificam token CSRF/origem (`app/services/glico.py:40-55`). Conversas/propostas são filtradas por owner e o acesso de médico revalida vínculo ativo/ciclo (`app/services/glico.py:57-110`). Confirmação de leitura e investigação usa autorização atual e efeito/receipt compartilham transação (`app/api/glico_routes.py:523-651`). Os testes Glico exercitam isolamento e rollback.
- Não encontrei echo do corpo bruto no retorno do gateway, nem rota pública de mídia. O corpo é contado até 3 MiB e redirecionamentos HTTP estão desativados (`app/api/glico_routes.py:721-759`). A falha de snapshot de contexto acima continua sendo bloqueadora.
- Campos novos do frontend estão presentes em `pt-BR`, `en-US` e `es` (55 grupos/entradas de primeiro nível cada, conforme inspeção); não encontrei texto novo do Glico hardcoded na página. Não fiz teste de paridade recursiva de todas as chaves ou browser.
- Todos os itens de aceite da matriz consultada estão como “Não executado”; nenhum “Aprovado” sem evidência foi encontrado. Isso é consistente com a decisão de arquitetura nº 10.

## Comandos executados

- `git branch --show-current` → `codex/glico-fase1`.
- `git status --short` → confirmou arquivos de backend/frontend/migrações não rastreados ou modificados, coerente com desenvolvimento em andamento; nenhum arquivo foi alterado por esta revisão além do parecer.
- `python -m pytest tests/integration -q` → **83 passed, 8 errors, 5 warnings, 149.97s**. Os oito erros são setup em `tests/integration/test_idempotency_recompute_import.py` ao gerar proveniência UCI: caminho de destino começa `\\Users\\felip\\...` (sem drive) e `shutil.move` falha com `FileNotFoundError` em `app/services/provenance.py:111`. Logo, a suíte completa não ficou verde; o erro observado é na fixture/import/proveniência Windows, não atribuído ao código Glico sem evidência.
- `npm run build` (em `frontend-react`) → **passou**, Vite 5.4.21, 904 módulos transformados, build concluído em 14.12s.
- Inspeção de locales via Python → `pt-BR.json`, `en-US.json`, `es.json` contêm `glicoAssistant` (55 entradas/grupos de primeiro nível em cada).
- Não executei migração contra MySQL 8 nem browser/E2E de Glico; matriz continua não executada para tais critérios.

## Limites desta revisão

Revisão pontual de código em desenvolvimento. Não certifica qualidade do PaddleOCR/ASR, isolamento operacional do worker, egress/APM/logs em deploy, compatibilidade MySQL, comportamento visual/acessível no navegador ou requisitos da matriz que exigem testes adversariais/produção.
