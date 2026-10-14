# Revisão independente final — Assistente Glico F1 (R2)

**Data:** 2026-10-14  
**Branch / HEAD:** `codex/glico-fase1` / `82f6266` (conforme briefing; confirmado por `git rev-parse --short HEAD`).  
**Parecer:** **NO-GO para declarar F1 concluída ou liberar mídia.**  
**Escopo alterado:** somente este relatório. Não houve troca de branch, reset, clean, stash ou commit. O checkout já continha mudanças locais e arquivos não rastreados; foram preservados.

## Resumo da rodada

A revisão confrontou o SDD, contratos, decisões, matriz e relatórios anteriores. Os bloqueadores anteriores de regressão Python e as principais lacunas visuais de consulta, PDF contextual e colaboração foram resolvidos nesta rodada. A interface de idioma/conta limpa rascunhos, o build e a E2E geral passaram. A bateria focada passou no SQLite; em MySQL, as migrações e 41/42 testes passaram na primeira execução. O teste restante falhou porque o MySQL do container bloqueava triggers com binary logging (erro 1419); executado isoladamente com a configuração temporária permitida, passou.

O NO-GO permanece por gates obrigatórios de qualidade/segurança operacional de mídia. Os artefatos de mídia documentam avaliações locais, mas OCR falhou no caso ambíguo e o corpus ASR é sintético, pequeno e incompleto por idioma. Não foi executado nesta revisão um corpus humano conforme SDD, benchmark na hospedagem alvo, nem instrumentação de egress, logs/APM, armazenamento e descarte. A matriz versionada continua com todas as linhas F1 como “Não executado”; abaixo registro o estado de evidência desta auditoria sem editar a matriz, conforme limite do briefing.

## Verificação dos achados da revisão R1

| Achado R1 | Situação nesta rodada | Evidência |
|---|---|---|
| Fluxos de consulta, PDF e colaboração ausentes/incompletos na página | **Resolvido no nível de UI observado.** A tela apresenta leituras/investigações, período, link autenticado ao PDF e preparação/revisão de colaboração. | `GlicoAssistantPage.jsx`; suite Playwright atual: testes Glico 85–111, incluindo colaboração, PDF contextual e breakpoints/locales. O endpoint PDF trilingue passou na bateria focal. |
| Estado de conversa ao trocar conta/idioma/logout | **Parcialmente resolvido.** O relatório do frontend descreve limpeza por conta/idioma e a E2E atual confirma logout/retorno sem restaurar rascunho; cobertura de isolamento por instrumentação de cache ainda não existe. | `frontend-react/e2e/RELATORIO-FRONTEND.md`; teste Playwright 95. |
| Oito erros da regressão Python UCI/PROV | **Resolvido nesta execução.** | `python -m pytest tests/integration tests/unit tests/e2e -q`: 139 passed, 1 skipped, 5 warnings. |
| Apenas SQLite; MySQL 8 não exercitado | **Resolvido nesta rodada para migração vazia e testes focais.** Migrações `0001–0017` passaram em MySQL 8.4.10. 41 testes passaram; o teste de rollback passou após ajuste temporário do binlog para permitir trigger. Não foi feito upgrade de baseline nem regressão integral no MySQL. | Execuções registradas abaixo. Schema de teste foi isolado e removido; ajuste temporário restaurado para OFF. |
| Reserva de job de áudio liberada no bucket errado | **Resolvido.** A rota libera `media_kind`, e os casos de sucesso/erro/timeout/cancelamento para imagem e áudio passaram. | `app/api/glico_routes.py:932`; teste focal `test_media_job_reservation_is_released_on_every_exit` na suite Glico. |
| Qualidade real de OCR/ASR insuficiente para liberar mídia | **Continua bloqueador.** Melhorias de assessment, ambiguidade e workers aquecidos existem, mas as avaliações documentadas não atingem tamanho/cobertura do SDD. | `RELATORIO-MIDIA-F1.md`: OCR 3/4 valor exato e esclarecimento nos casos inseguros; ASR sintético, 10 frases em espanhol, limitado para avaliação e não satisfaz 30 exemplos humanos por idioma. |

## Bloqueadores

1. **Gate quantitativo de OCR não satisfeito.** A avaliação documentada usa quatro imagens e obteve 3/4 valores exatos; o caso `foto1` confunde `106` com `1006`. O worker atualizado pede esclarecimento para candidatos múltiplos/fora de faixa, mas quatro imagens não atendem ao corpus e cobertura da SDD. A qualidade e a unidade ainda não estão demonstradas para câmeras e casos representativos. Manter OCR desligado para usuários até cumprir GLI-CA-042/043.
2. **Gate de ASR não satisfeito.** A avaliação é de voz sintética Piper em espanhol, com alguns testes sintéticos pt/en reportados, não o conjunto humano mínimo por idioma. Foram registrados reconhecimento incorreto (`228` para `128`), valores múltiplos e fala não relacionada que extraiu número de horário. Datas, unidade e intenção não estão validadas em diversidade de fala real. Manter ASR desligado até cumprir GLI-CA-044/045.
3. **Privacidade/egress e operação de mídia sem evidência instrumental.** Permanecem sem execução nesta revisão os marcadores sintéticos em filesystem/DB/log/APM, egress allowlist, desconexão/crash real, restore/restart com TTL, limpeza externa, alertas e limites na hospedagem alvo. Implementação e testes unitários não demonstram que proxies, observabilidade e runtime não retêm dados. GLI-CA-031–038, 040–041 e 046 continuam parciais ou sem execução.
4. **Aceite F1 ainda não pode ser fechado.** Todos os critérios F1 são bloqueadores na matriz. Vários cenários específicos de concorrência, revogação, cache/CDN, egress, privacidade, mídia real e deploy não foram provados; logo não há base para GO mesmo com as suítes gerais verdes. A linha GLI-CA-059 também exige revisão sem bloqueadores.

## Importantes

1. **MySQL focal dependeu de configuração do servidor para fault injection.** A primeira execução teve 41 passed e 1 failed, erro 1419 ao criar trigger de falha. Com `log_bin_trust_function_creators=ON` temporário, o teste isolado de rollback passou. O valor foi restaurado para OFF. Não foi repetida toda a bateria focal com a configuração temporária, nem executada a suíte completa no MySQL.
2. **A matriz de aceite não reflete esta evidência.** Cada linha GLI-CA-001–059 permanece “Não executado” no arquivo de origem. Não editei a matriz por restrição expressa do briefing; os estados justificados desta auditoria estão na seção seguinte. A atualização formal da matriz deve ocorrer na rodada própria de aceite.
3. **A UI de mídia é exercitada sobretudo com endpoints simulados.** Playwright cobre erros, cancelamento, revisão e flags desligadas; o sucesso de OCR/ASR real integrado pelo navegador e a cadeia de autorização com worker real não foram demonstrados nesta execução.
4. **Migração MySQL só foi verificada em schema vazio.** Não repeti upgrade a partir do baseline `20261012_0013` nesta revisão. A evidência de baseline existente em `RELATORIO-BACKEND.md` é de relatório anterior, não execução minha.

## Menores

- `app/media_worker/audio.py:111,130,133,136,178,191` e `app/media_worker/image.py:120,123,126,249,264`: limpeza/encerramento usa blocos `except Exception: pass`. Os testes de boundary passaram, mas esses caminhos de limpeza silenciosa reduzem observabilidade de falha no shutdown; não mudam o NO-GO já imposto pelos gates operacionais.
- `frontend-react/src/pages/GlicoAssistantPage.jsx:577`: ditado depende da API de reconhecimento de fala do navegador. O E2E cobre navegador sem suporte e estado de erro; transcrição bem-sucedida no navegador não foi exercitada.
- `features/a-desenvolver/03-assistente-glico/MATRIZ-ACEITE.md:17-100`: estados formais ficaram desatualizados (“Não executado”) após as evidências desta rodada; não foram alterados por instrução de escopo.

## Comandos e resultados executados nesta revisão

| Comando/ação | Resultado observado |
|---|---|
| `git status --short --branch`; `git rev-parse --short HEAD` | Branch `codex/glico-fase1`, HEAD `82f6266`; alterações pré-existentes preservadas. |
| `python -m pytest tests/integration tests/unit tests/e2e -q` | **139 passed, 1 skipped, 5 warnings** em 220.23s. Avisos: loky não detectou núcleos físicos no Windows e quatro `ConvergenceWarning` esperados do scikit-learn. |
| `npm run build` (`frontend-react`) | **Passou**, Vite 5.4.21, 904 módulos, 13.84s. |
| `npm run test:e2e` (`frontend-react`) | **110 passed, 1 skipped** em 10.3 min, Chromium. O skip é CSCW-CA-29, retry de publicação da outbox. Inclui a spec Glico (27 testes) com locale, responsividade, fluxo de proposta, colaboração, PDF contextual, logout, FAQ, permissão/flag de mídia e estados simulados. |
| `python -m pytest tests/integration/test_glico_foundation.py -q` (SQLite) | **41 passed, 1 skipped** em 34.18s. A bateria inclui CSRF/Origin, IDs estrangeiros e ausentes, confirmação/idempotência/rollback, 10 confirmações concorrentes, quota, TTL/replay, mídia, expiração e PDF pt-BR/en-US/es. O skip é o caso de serialização de quota exclusivo de MySQL. |
| MySQL `mysql:8.4` / `alembic upgrade head` em schema novo `myglico_f1_r2_20261014` | **Passou**, migrations `20260414_0001` a `20261013_0017`. `docker compose ps db` mostrou MySQL saudável. |
| `MYGLICO_INTEGRATION_DATABASE_URL=mysql+pymysql://…/myglico_f1_r2_20261014 python -m pytest tests/integration/test_glico_foundation.py -q` | **41 passed, 1 failed** em 35.63s; única falha no setup do teste de rollback por erro MySQL 1419 (trigger bloqueado com binlog). |
| Mesmo setup MySQL, `python -m pytest tests/integration/test_glico_foundation.py::test_glico_confirmation_rolls_back_record_source_event_receipt_on_failure -q`, com `log_bin_trust_function_creators=ON` temporário | **1 passed** em 4.98s. Toggle foi restaurado para OFF e schema isolado removido. Não equivale a uma segunda execução das 42 como lote. |

## Matriz F1 — estado desta revisão

**Legenda:** “Parcial” significa que executei cobertura relacionada ou encontrei evidência concreta, mas o cenário integral da matriz não foi provado. “Não executado” significa que não rodei o gate indicado. Nenhum critério abaixo recebe “Aprovado” porque a matriz define os 59 critérios como bloqueadores, e permanecem gates operacionais e de mídia abertos. “Revisão” distingue as execuções deste relatório de resultados históricos nos relatórios de implementação.

| ID | Estado | Evidência desta revisão / lacuna remanescente |
|---|---|---|
| GLI-CA-001 | Parcial | Regressão e bateria Glico passaram; não testei cada endpoint anônimo e efeito de inferência por canal. |
| GLI-CA-002 | Parcial | Testes rejeitam identidade/IDs forjados; cobertura integral de todos os payloads de paciente B não foi demonstrada. |
| GLI-CA-003 | Parcial | Teste adversarial compara recurso estrangeiro/ausente; não cobre toda rota/ID de attempt. |
| GLI-CA-004 | Parcial | E2E verifica médico sem vínculo e seleção explícita; PENDING e prova instrumental de ausência de carga não cobertos por inteiro. |
| GLI-CA-005 | Parcial | Teste focal de revogação/reassociação passou; matriz completa com dois médicos e recursos históricos não executada. |
| GLI-CA-006 | Não executado | Não rodei corrida de revogação durante inferência/replay receipt em MySQL. |
| GLI-CA-007 | Não executado | Logout/expiração concorrente com inferência/confirm não testados nesta revisão. |
| GLI-CA-008 | Parcial | Versão/contexto, snapshot e worker simulado cobertos; corrida real de abas/contextos não exercitada. |
| GLI-CA-009 | Parcial | Playwright cobre troca/logout e limpeza do rascunho Glico; inspeção instrumentada de caches entre contas não executada. |
| GLI-CA-010 | Parcial | E2E impede confirmação de glicemia por médico; ataque HTTP completo a single/bulk não repetido. |
| GLI-CA-011 | Parcial | Teste focal executa Origin null e CSRF inválido/ausente; header interno forjado em todas as rotas não verificado. |
| GLI-CA-012 | Parcial | Teste Glico de `no-store` passou; CDN/deploy não foi inspecionado. |
| GLI-CA-013 | Parcial | Fluxos exigem proposta/ação de confirmar; injection adversarial simultânea em texto, OCR, ASR e tool result não executada. |
| GLI-CA-014 | Parcial | E2E e teste focal cobrem edição versionada e confirmação; adulteração de cada campo diretamente no confirm não foi repetida. |
| GLI-CA-015 | Parcial | Teste TTL de proposta expirada passou; combinações de cancelamento, versão/contexto antigo e leak não foram todas rodadas. |
| GLI-CA-016 | Parcial | 10 confirmações concorrentes passaram no SQLite; MySQL 8.4 passou em lote quanto às confirmações, salvo o teste de rollback com trigger bloqueado, retestado isoladamente. |
| GLI-CA-017 | Parcial | Reuso de idempotency key conflitante coberto na bateria SQLite/MySQL; falha/retry em múltiplas instâncias não executados. |
| GLI-CA-018 | Parcial | Rollback passou em SQLite e teste focal MySQL isolado após ajuste temporário do binlog; não repeti todos os pontos de injeção no MySQL. |
| GLI-CA-019 | Parcial | Receipt e replay exercitados; perda real de resposta/reload no browser não simulada nesta rodada. |
| GLI-CA-020 | Parcial | Replay de mensagem coberto; contagem completa de eventos/notificações em todos retries não auditada. |
| GLI-CA-021 | Parcial | Parser/rejeições de faixa e ambiguidade cobertos; datas ambíguas, timezone e unidade ausente não foram combinados em campanha integral. |
| GLI-CA-022 | Parcial | Testes cobrem normalização básica; não verifiquei pela UI valor original, conversão mmol/L e valor persistido lado a lado. |
| GLI-CA-023 | Não executado | Sem injeção instrumentada multicanal com spies de ferramenta/efeito/egress. |
| GLI-CA-024 | Parcial | Implementação determinística sem runtime/tool genérica e suites passaram; stub comprometido com tool spy não foi executado. |
| GLI-CA-025 | Não executado | Não inspecionei requests reais de worker para confirmar ausência de cookie, sessão e identidade. |
| GLI-CA-026 | Parcial | Testes unitários/integração cobrem HMAC, nonce/replay; não executei replay cross-replica Redis nesta rodada. |
| GLI-CA-027 | Não executado | Redirect desabilitado no código; egress/allowlist não instrumentados. |
| GLI-CA-028 | Parcial | Regressão de mensagens e XSS geral passou; payloads Glico de javascript/tracking sem conexão não testados explicitamente. |
| GLI-CA-029 | Parcial | FAQ determinística e estados da UI passaram; exaustão de quota simultânea sem bloquear formulário/confirm não foi executada integralmente. |
| GLI-CA-030 | Parcial | Flags desligadas produzem UI/API indisponível e testes passaram; deploy com configuração inválida/fake e egress de runtime não auditado. |
| GLI-CA-031 | Não executado | Sem marcador de mídia sintético com inspeção conjunta de FS, spool, DB, fila e logs. |
| GLI-CA-032 | Parcial | Testes cobrem liberação da reserva em sucesso/erro/timeout/cancelamento; processo real, disconnect e buffers tardios não inspecionados. |
| GLI-CA-033 | Não executado | Sem busca de marcadores em logs/APM/history/DB desta execução. |
| GLI-CA-034 | Parcial | Suite do worker valida formatos/limites; não executei corpus adversarial completo MIME spoof/EXIF/animação/truncamento. |
| GLI-CA-035 | Não executado | Worker não foi morto por fault injection durante processamento. |
| GLI-CA-036 | Parcial | TTL/replay e criptografia funcional cobertos parcialmente; inspeção de banco sem chaves, cleanup/revogação completa não feita. |
| GLI-CA-037 | Não executado | Sem restore/restart e verificação de expiração antes de servir. |
| GLI-CA-038 | Não executado | Sem prova instrumental de fornecedor externo desabilitado, retenção e egress zero. |
| GLI-CA-039 | Parcial | Quota e reservas exercitadas; concorrência distribuída em duas instâncias/Redis não executada. |
| GLI-CA-040 | Não executado | Sem crash/retry de transporte e reconciliação de reserva incerta. |
| GLI-CA-041 | Parcial | Fail-closed e timeout cobertos por testes/UI; budget/circuito/alerta sem dados clínicos em deploy não verificados. |
| GLI-CA-042 | Reprovado | Relatório de OCR real documenta 3/4 acertos, caso 1006 incorreto e corpus de quatro fotos; não satisfaz gate quantitativo/cobertura. Não reexecutei modelo nesta revisão. |
| GLI-CA-043 | Parcial | Assessment atualizado e esclarecimentos de ambiguidades descritos no relatório; avaliação pequena e sem gate E2E real suficiente. |
| GLI-CA-044 | Reprovado | Relatório ASR não cobre corpus humano mínimo nos três idiomas; exemplos sintéticos têm erro 228 e valor espúrio de fala não relacionada. |
| GLI-CA-045 | Parcial | Silêncio sintético foi rejeitado conforme relatório; ruído, música, fala humana, duração e demais casos completos não validados. |
| GLI-CA-046 | Não executado | Não medi hospedagem alvo; métricas locais nos relatórios não comprovam cold/warm, memória ou deadline de produção. |
| GLI-CA-047 | Parcial | E2E cobre texto, edição/confirm e UI; foto/áudio reais continuam desabilitados, sem ciclo real integrado completo. |
| GLI-CA-048 | Parcial | Endpoint PDF testado nos três locales e UI oferece link contextual; pedido via áudio/texto com extração de período não comprovado. |
| GLI-CA-049 | Parcial | Regressão e UI testam status/origem em outros fluxos; não percorri alteração pós-análise por todas as superfícies Glico. |
| GLI-CA-050 | Parcial | E2E mostra preparação/revisão de colaboração; destinatários/dias, ditado bem-sucedido e notificações não foram cobertos integralmente juntos. |
| GLI-CA-051 | Parcial | Consultas e listagem na UI implementadas; teste de não mutação de read-position/consentimento pelo assistente não executado. |
| GLI-CA-052 | Parcial | FAQ determinística passou em pt-BR/en-US/es; cobertura completa por papel/versão/destinos não auditada. |
| GLI-CA-053 | Parcial | Playwright Glico passou em 390/768/1440 e três locales segundo spec; inspeção visual de contraste/leitura assistiva completa não feita. |
| GLI-CA-054 | Parcial | E2E cobre teclado, permissões negadas, cancelamento e erros de mídia simulados; dispositivo/browser com captura real não exercitado. |
| GLI-CA-055 | Parcial | Bateria Glico e regressão verificaram fluxo/proveniência e rollback; export privado, ausência de payload bruto e cadeia UCI não auditados integralmente. |
| GLI-CA-056 | Parcial | SQLite vazio via regressão e MySQL 8.4 vazio até head passaram; upgrade de baseline e concorrência/migrations antigas completa não repetidos. |
| GLI-CA-057 | Parcial | Testes distinguem casos simulados e regressão/media worker; egress e resultados reais end-to-end permanecem ausentes. |
| GLI-CA-058 | Parcial | Suíte Python integral 139/1 skip; frontend 110/1 skip. Import UCI idempotente duas vezes e indicadores não foram reexecutados nesta revisão. |
| GLI-CA-059 | Parcial | Relatórios/runbook existentes e esta revisão independente; gates acima impedem revisão sem bloqueadores e aceite formal. |

Os critérios GLI-CA-060–072 pertencem à F2 e não foram executados nem avaliados funcionalmente, de acordo com `DECISOES-ARQUITETURA.md` e o escopo explícito desta revisão F1. Não se promove nenhum deles a N/A para liberar F1.

## Conclusão

**NO-GO.** A rodada corrigiu os bloqueadores funcionais e de regressão identificados em R1 e acrescentou evidência MySQL útil. Ainda faltam os gates obrigatórios de qualidade dos modelos, segurança operacional de mídia e validação na hospedagem alvo. O aceite não deve ser fechado nem OCR/ASR ativados para usuários antes de esses itens serem provados e a matriz refletir resultados aprovados.

DONE-REVISAO-R2
