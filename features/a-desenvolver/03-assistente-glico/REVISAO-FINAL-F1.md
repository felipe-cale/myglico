# Revisão final independente — Assistente Glico F1

**Data:** 2026-10-13  
**Branch:** `codex/glico-fase1`  
**Escopo:** SDD, contrato, decisões, matriz, relatórios prévios, implementação backend/mídia/frontend/migrações e validação executada nesta revisão.  
**Alterações nesta revisão:** somente este relatório. Não usei stash nem alterei código-fonte.

## Parecer

**NO-GO para commit como F1 concluída ou para liberação.** A fundação transacional e alguns fluxos estão implementados, mas não há evidência para os gates normativos de mídia real, MySQL 8, privacidade operacional e vários fluxos de produto. A UI atual não entrega PDF/consultas completas nem criação e resposta de investigação pela própria experiência Glico. A suíte pedida terminou em 100 passados e 8 erros UCI/PROV; frontend build passou; Playwright terminou com 105 passados e 1 ignorado.

O checkout já continha modificações e arquivos não rastreados. Os relatórios prévios também descrevem rodadas anteriores; considerei evidência executada nesta revisão apenas os comandos registrados abaixo e os resultados explicitamente reproduzíveis nos relatórios de implementação.

## Bloqueadores

1. **Escopo funcional normativo incompleto.** SDD seção 4 (linhas 46–52) e `CONTRATOS-API.md` F1.0–F1.4 exigem registro por texto/foto/áudio, consultas/PDF, colaboração e UI final. A tela [GlicoAssistantPage.jsx](/D:/work/myglico/frontend-react/src/pages/GlicoAssistantPage.jsx:190) trata visualmente leitura recente, mas os demais `answer_key`/`items` viram ajuda genérica (210); não há fluxo integrado de geração/download de PDF nem de abrir/respond­er investigação nessa tela. A mídia real também não satisfaz o gate: `RELATORIO-MIDIA-F1.md` documenta OCR padrão expirando em 4/4 casos a 20s e valor errado em um caso diagnóstico; ASR nos três idiomas/corpus requerido não foi evidenciado. **Impacto:** F1.1–F1.4 e critérios GLI-CA-042–050 não aceitos.
2. **Matriz sem aceite e gates de operação ausentes.** A matriz mantém GLI-CA-001–059 em “Não executado”. Não foi executada migração MySQL 8, avaliação de egress/APM/logs, replay HMAC entre réplicas com Redis, restore/cleanup TTL, nem a bateria adversarial e concorrente descrita. Não se pode elevar requisito documental a aprovado só porque o caminho está implementado.
3. **Comando de regressão Python falha.** Os oito erros UCI/PROV impedem a evidência de regressão total pedida e deixam GLI-CA-058 pendente. A análise de baseline abaixo indica causa fora das alterações Glico observadas, mas a falha continua bloqueando a validação do commit completo.

## Importantes

1. **Revisão de mídia ainda requer resultado real de segurança/qualidade.** A rota atual valida headers, tira snapshot imutável de contexto e revalida sessão/contexto após o worker ([glico_routes.py](/D:/work/myglico/app/api/glico_routes.py:753), 763–773, 844–858), corrigindo o achado da revisão parcial. Porém, o resultado do OCR registrado falha no deadline padrão e escolhe `1006` no exemplo ambíguo em avaliação de 120s. Manter mídia desligada até resolver qualidade/latência e cumprir os gates.
2. **Cobertura de consulta e contrato/UI incompleta.** API responde leituras, métricas, dias atípicos, investigações e pacientes vinculados (`glico_routes.py:269-338`), mas UI só renderiza `glico.query.readings` (`GlicoAssistantPage.jsx:195-210`). Respostas válidas de outras consultas são apresentadas como ajuda genérica. Também não se vê no componente a seleção de período, pedido contextual de PDF ou interface de colaboração exigidos por FUN-05/07/08/13/14/15.
3. **Estado da conversa em troca de conta/idioma.** A página cria a conversa uma vez no mount e comentário diz que troca de idioma só relê capacidades (`GlicoAssistantPage.jsx:114-153`); verificar em browser se locale da conversa/FAQ acompanha a preferência e se logout/troca de conta limpa estado. A evidência browser histórica não cobre explicitamente esse ciclo.
4. **Migrações apenas SQLite.** 0014–0017 aplicam no SQLite do harness e as conexões ORM ligam `PRAGMA foreign_keys=ON` (`app/db/session.py:35-39`), mas MySQL 8 permanece não exercitado conforme relatórios. Critério DAT-01/TST-03 continua parcial.
5. **Reserva de job de áudio é liberada no bucket errado.** A rota reserva com `media_kind` e no `finally` chama sempre `release_media_job(..., "image")` (`glico_routes.py:798`, `882-888`), enquanto o serviço mantém buckets globais e por conta separados por tipo (`app/services/glico.py:202-244`). Se áudio estiver habilitado, após um job a reserva `audio_active`/global `audio` não é decrementada; o usuário pode ficar permanentemente sem novo job e a capacidade global pode esgotar. Corrigir chamando `media_kind` e cobrir sucesso/erro/cancelamento de imagem e áudio antes de ativar ASR.

## Menores

1. O parser determinístico é estreito e não resolve ambiguidades de data local: regex exige data ISO e horário com `:` (`glico_routes.py:195-230`); entradas sem unidade não formam proposta e HI/LO é tratado como sinal por ocorrência textual (`193-195`). Isso é conservador quanto a não gravar, mas não cumpre a experiência completa de esclarecimento/locales.
2. A resposta de `glico.query.readings` agora é apresentada, mas nome e data são concatenados em texto simples com quebras de linha (`GlicoAssistantPage.jsx:195-202`); uma lista acessível com estrutura visual melhoraria navegação assistiva.

## Segurança e privacidade — inspeção do código atual

- **Autorização/paciente/IDOR:** rotas de conversa e proposta passam por ownership; médico revalida vínculo ativo/ciclo por `authorized_conversation`/`active_context` (ex.: `glico_routes.py:391-404`, `537-551`, `624-642`). A confirmação executa efeito e receipt no mesmo fluxo transacional (579–705). Os testes de integração Glico relatados cobrem CSRF, ownership, confirmação/rollback e autorização básica. Cobertura concorrente MySQL e IDs de todas as rotas não está comprovada.
- **CSRF:** mutações chamam `_require_csrf`; proteção de origem/token está em `app/services/glico.py:40-55` (relatório anterior). Teste adversarial completo não executado neste turno.
- **Mídia/IDOR/contexto:** upload exige contexto e request UUID antes de ler o corpo; congela versão/paciente/associação/papel/owner (763–773) e revalida sessão, conta e conversa depois do worker (844–858). Limite de 3 MiB e content type são aplicados (774–795); redirects desligados e resposta limitada (813–831). Esses pontos corrigem o achado da revisão parcial.
- **HMAC/replay:** gateway assina POST/path/timestamp/nonce/digest (801–812); worker `auth.py` verifica digest/HMAC e consome nonce via ReplayStore. Launcher exige store compartilhado Redis conforme relatório de mídia. Não executei teste de replay cross-replica/redis; correção estrutural não equivale ao gate GLI-CA-026 aprovado.
- **Fail closed:** foto/áudio dependem de flag, URL, segredo com comprimento mínimo e quota global; caso contrário 503 (776–781). Defaults de configuração são desligados e quota zero (`app/core/config.py:46-53`). Sem worker/modelo/config não há fallback externo. A flag de provedor externo também não demonstra gate de configuração completo em produção.
- **Idempotência/TTL:** mensagens e mídia consultam/gravam replay cifrado por chave/digest; conflito e janela TTL constam no relatório backend. Confirmação usa chave/receipt e versões. Propostas expiram em 15 min conforme contrato/modelo. Cleanup operacional de payload e tombstone em restart/restore não foi executado.
- **Vazamento/logs:** inspeção não encontrou resposta de gateway que ecoe bytes/transcrição nem rota pública para anexos; worker limita respostas/erros tipados e informa que não persiste/loga conteúdo. Ausência de vazamento em APM, proxies, crash dump e disco precisa de instrumentação; não certificada nesta auditoria.
- **FK:** sessão SQLAlchemy ativa foreign keys em cada conexão SQLite. Fixture também executa PRAGMA ON em conexão raw (`tests/integration/conftest.py`). Não foi desativado para passar testes.

## Tabela requisito × status × evidência (F1)

Status **implementado** significa caminho reconhecível no código; não significa gate de aceite aprovado. “Evidência executada” distingue execução observada nesta revisão ou relatada com comando/resultado reproduzível. Os critérios marcados não executados na matriz não são considerados aprovados.

| Requisito F1 | Status | Evidência executada / lacuna principal |
|---|---|---|
| GLI-CA-001 | Parcial | Testes de sessão nos relatórios; a suíte completa foi executada. Sem ataque de mídia/confirm abrangente. |
| GLI-CA-002 | Parcial | Ownership testado em integração Glico; vetores completos de identidade/papel/IDs não demonstrados. |
| GLI-CA-003 | Parcial | Consultas filtram owner e retornam 404; matriz adversarial de todos IDs não executada. |
| GLI-CA-004 | Parcial | Harness real tinha médico sem vínculo; seleção concorrente/PENDING sem carga não inteiramente demonstrada. |
| GLI-CA-005 | Parcial | Ciclo de vínculo usado no código; cenário de dois médicos/reassociação sem reabertura não comprovado. |
| GLI-CA-006 | Ausente como evidência | Revalidação existe; revogação concorrente MySQL não executada. |
| GLI-CA-007 | Parcial | Sessão verificada após worker; corrida logout/expiração + confirmação sem MySQL não executada. |
| GLI-CA-008 | Implementado | Snapshot e teste de contexto durante worker reportado; E2E concorrente de abas não comprovado. |
| GLI-CA-009 | Parcial | E2E histórico cobriu troca/logout geral; instrumentação de cache Glico não demonstrada. |
| GLI-CA-010 | Parcial | Papel bloqueia proposta ao médico no código; ataque direto/bulk não reportado. |
| GLI-CA-011 | Parcial | CSRF coberto em testes Glico; matriz adversarial Origin/header não executada. |
| GLI-CA-012 | Ausente como evidência | Headers no-store/CDN não verificados nesta revisão. |
| GLI-CA-013 | Parcial | Confirmação separada do endpoint; injeção adversarial em todos canais não executada. |
| GLI-CA-014 | Implementado | Edição versionada/confirm sem campos clínicos reportada em integração e E2E live. |
| GLI-CA-015 | Parcial | Checagem estado/versão/TTL/contexto no código; matriz de casos expirados não integralmente executada. |
| GLI-CA-016 | Parcial | Concorrência de confirmação em SQLite reportada; MySQL + 10 requests não executado. |
| GLI-CA-017 | Parcial | Digest/idempotência no código e retries iguais reportados; conflito concorrente MySQL não comprovado. |
| GLI-CA-018 | Parcial | Rollback de integração reportado; efeitos/source/event/receipt em MySQL sem prova. |
| GLI-CA-019 | Parcial | GET proposal/receipt existe; reload após perda de resposta não foi comprovado em E2E. |
| GLI-CA-020 | Parcial | Replays persistidos recentes; notificações/eventos duplicados não cobertos integralmente. |
| GLI-CA-021 | Parcial | Validação numérica básica existe; casos completos NaN, datas ambíguas e unidade ausente não verificados. |
| GLI-CA-022 | Parcial | Conversão mmol/L implementada (`glico_routes.py:206-215`); teste UI/commit de original e normalizado não comprovado. |
| GLI-CA-023 | Ausente como evidência | Sem campanha adversarial instrumentada de prompt/injection em OCR/ASR/notas. |
| GLI-CA-024 | Implementado | Não há runtime de LLM/tool genérica; backend determinístico. Teste de stub comprometido não executado. |
| GLI-CA-025 | Parcial | Header worker não inclui cookie/identidade clínica; instrumentação de requests não executada. |
| GLI-CA-026 | Parcial | Verificador HMAC/replay implementado; assinatura errada/path/replay entre réplicas não executado aqui. |
| GLI-CA-027 | Parcial | URL fixa configurada e redirects desligados; egress instrumentado não executado. |
| GLI-CA-028 | Parcial | React renderiza strings; teste XSS/URL/tracking não executado. |
| GLI-CA-029 | Parcial | FAQ determinística e quota em código; pedidos fora de escopo + quota/manual E2E incompleto. |
| GLI-CA-030 | Parcial | Defaults fail-closed confirmados; deploy/download/runtime e fake em produção não testados. |
| GLI-CA-031 | Parcial | Streaming limitado em memória, sem persistência intencional; marcador sintético FS/DB/log não instrumentado. |
| GLI-CA-032 | Parcial | Cancelamento frontend e cleanup no finally existem; cancel/disconnect/timeout com inspeção de processo não executados. |
| GLI-CA-033 | Ausente como evidência | Não houve inspeção de logs/APM/DB com marcadores sintéticos. |
| GLI-CA-034 | Parcial | Decoder valida conteúdo/limites; corpus MIME spoof/EXIF/animada adversarial não executado. |
| GLI-CA-035 | Ausente como evidência | Falha/kill do worker e ausência de retomada não testados. |
| GLI-CA-036 | Parcial | Payloads cifrados e TTL no modelo; cleanup/DB sem chave/scheduler não exercitados. |
| GLI-CA-037 | Ausente como evidência | Restore/restart e expiração antes de servir não validados. |
| GLI-CA-038 | Parcial | Gate sem envio externo e worker privado; egress/retention instrumentados não testados. |
| GLI-CA-039 | Parcial | Quota compartilhada em DB/migração 0016; concorrência multi-instância MySQL/Redis não executada. |
| GLI-CA-040 | Ausente como evidência | Crash/retry/reserva incerta sem fault injection. |
| GLI-CA-041 | Parcial | Gate sem configuração devolve indisponível; circuito/budget/alerta de produção ausentes de prova. |
| GLI-CA-042 | Parcial | OCR real documentado; padrão 20s expira 4/4 e acerto diagnóstico 3/4, gate não satisfeito. |
| GLI-CA-043 | Parcial | OCR diagnóstico revelou ambiguidade não resolvida; não há comportamento seguro completo de esclarecimento. |
| GLI-CA-044 | Ausente | ASR real nos três idiomas/interface cruzada não executado. |
| GLI-CA-045 | Ausente | Corpus de ruído/silêncio/idioma/áudio longo não executado. |
| GLI-CA-046 | Parcial | Métricas locais OCR existem, incompatíveis com deadline; hospedagem alvo/Vercel não medida. |
| GLI-CA-047 | Parcial | Texto → proposta → edição → confirmação demonstrado; foto/áudio real, home/pending e gate geral incompletos. |
| GLI-CA-048 | Ausente | Nenhum fluxo Glico de PDF autenticado com locale/período explícito implementado na tela. |
| GLI-CA-049 | Parcial | Atualização de métricas pendentes existe no domínio; UI Glico/stale completo não demonstrado. |
| GLI-CA-050 | Parcial | Endpoints/propostas de colaboração no backend; UI operacional de abrir/responder/ditar incompleta. |
| GLI-CA-051 | Parcial | Consulta limitada de investigações/pacientes existe; UI e posição de leitura/consentimento não provadas. |
| GLI-CA-052 | Parcial | FAQ pt/en/es determinística existe; cobertura FAQ/papel/versão/destinos da SDD não completa. |
| GLI-CA-053 | Parcial | E2E Glico reportado em 390px e idiomas; 768/1440, contraste e inspeção browser não integral. |
| GLI-CA-054 | Parcial | Spec Glico exercita estados simulados; permissões reais, cancelamento e erros de dispositivo não todos testados. |
| GLI-CA-055 | Parcial | Origem/receipt/proveniência no fluxo textual; audit de export/payload bruto/cadeia UCI não integral. |
| GLI-CA-056 | Parcial | Alembic SQLite vazio executado pelo E2E; MySQL 8 e upgrade baseline não executados. |
| GLI-CA-057 | Parcial | Suites têm doubles e teste live; ataques/egress e separação completa de gates ainda insuficientes. |
| GLI-CA-058 | Parcial | Regressão atual: 100 passed, 8 erros UCI/PROV; E2E frontend 105 passed, 1 skipped. |
| GLI-CA-059 | Parcial | Relatórios/runbook parcial e revisão aqui; faltam gates e revisão sem bloqueadores. |

## Os oito erros UCI e relação com Glico

O comando foi `python -m pytest tests/integration tests/unit tests/e2e -q`: **100 passed, 8 errors, 5 warnings**, 205.92s. Todos os oito erros são setup de testes em `tests/integration/test_idempotency_recompute_import.py` (AUT-CA-16/17, CSCW-CA-11/12/45 e AUT-CA-21), compartilhando a fixture `uci_import`. A causa observada é `scripts/import_uci_diabetes.py:33` → `app/services/provenance.py:111` → `prov.model.serialize`/`shutil.move`: destino vem como caminho Windows sem drive `\Users\felip\AppData\Local\Temp\myglico-integration-...\provenance\...json`, e `os.rename`/`CopyFile2` termina em `FileNotFoundError [WinError 3]`.

**Atribuição:** análise do traceback e `git show HEAD:app/services/provenance.py` mostram que a serialização de PROV já usava `document.serialize(json_path, format="json")` na base, e o setup UCI não depende dos módulos Glico. A alteração visível em `tests/integration/conftest.py` acrescenta apenas `MYGLICO_GLICO_ENABLED=true` (além de BOM/encoding); não modifica `MYGLICO_PROVENANCE_DIR` nem a lógica UCI. Portanto, os erros são **muito provavelmente preexistentes/ambientais de caminho Windows**, não causados pela feature Glico. Sem stash ou checkout de baseline não se pode afirmar reprodução contrafactual; falha permanece aberta.

## Comandos executados nesta revisão

- `git status --short --branch` → branch `codex/glico-fase1`; muitas mudanças locais e não rastreadas preservadas.
- `python -m pytest tests/integration tests/unit tests/e2e -q` → **100 passed, 8 errors, 5 warnings, 205.92s**. Erros descritos acima.
- `npm run build` em `frontend-react` → **passou**, Vite 5.4.21, 904 módulos.
- `npm run test:e2e` em `frontend-react` → **105 passed, 1 skipped** (106 total, 11.7 min). O teste ignorado é CSCW-CA-29 (publicação falha/outbox) conforme anotação do runner.
- Inspeção estática dos docs pedidos, `app/api/glico_routes.py`, `app/services/glico.py`, `app/models/glico.py`, migrações 0014–0017, `app/media_worker`, `GlicoAssistantPage.jsx`, componentes e locales.
- Não executados nesta auditoria: MySQL 8, browser dedicado a novos cenários além da suite, egress instrumentado, avaliação de modelos ou verificações adversariais operacionais.

## Conclusão

**NO-GO.** Há uma base útil e as correções de snapshot/contexto, idempotência, limites e fail-closed aparecem implementadas. A fase F1 completa não atende ainda aos requisitos funcionais e operacionais da própria SDD/matriz, e a evidência de regressão não está verde. A suite frontend geral passou com uma omissão conhecida, o que não cobre os gates de mídia real e backend operacional pendentes.
