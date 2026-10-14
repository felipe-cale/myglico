# Contratos de API do Assistente Glico (F1)

**Status:** congelado para a rodada F1.0/F1.1; revisão coordenada pelo owner do backend. **Base:** `felipe-cale/impeccable-ux` @ `e776b9bce55767fdfb58aa8533d34c58465bec8b`; branch de trabalho `codex/glico-fase1`. **Escopo:** somente F1.0–F1.4. F2 explicitamente fora.

## Backlog e dependências

| Ordem | Incremento | Entrega | Dependências |
|---|---|---|---|
| 1 | F1.0 Fundação | sessões/contexto/ciclo de vínculo, schemas, propostas versionadas, confirmação/receipt atômicos, CSRF, cotas compartilhadas, FAQ determinística, flags/runbook | Nenhuma |
| 2 | F1.1 Foto | serviço isolado + PaddleOCR real, 1 imagem/1 leitura, revisão explícita, descarte | F1.0 + contrato de worker |
| 3 | F1.2 Texto/ajuda/consulta | texto volátil, navegação/help, consultas autorizadas e PDF existente | F1.0 |
| 4 | F1.3 Áudio | serviço isolado + faster-whisper multilíngue, revisão explícita e descarte | F1.0 + F1.1/worker |
| 5 | F1.4 Colaboração/UI | perguntas e mensagens revisadas, experiência paciente/médico mobile/desktop e locales | F1.0–F1.3 |

## Endpoints

Todos sob `/api/glico`; cookie de sessão atual + CSRF nas mutações; `Cache-Control: no-store`. Identidade/role nunca vêm do request. JSON pequeno limitado. Anexos usam corpo binário `application/octet-stream` em streaming limitado; nunca multipart/UploadFile.

- `POST /conversations` `{locale, client_request_id}` → `{id, role, context, context_version, capabilities}`; paciente é derivado da sessão.
- `PATCH /conversations/{id}/context` `{version, patient_id?, period?}` → contexto novo; médico seleciona explicitamente paciente ACTIVE autorizado; invalida propostas anteriores.
- `GET /conversations/{id}` → cartões autorizados, sem transcrição/histórico bruto.
- `POST /conversations/{id}/messages` `{text, context_version, client_request_id}` → resposta tipada `help|answer|proposal|clarification`; máximo 2000 chars; texto não persiste como chat.
- `POST /conversations/{id}/extract/image` e `/extract/audio` → bytes limitados + headers de request/contexto; retornam proposta/correção. Sem echo de bytes/ocr/transcrição.
- `PATCH /proposals/{id}` `{version, context_version, fields}` → versão nova; somente campos editáveis do tipo; revalida ownership/contexto e recalcula digest.
- `POST /proposals/{id}/confirm` `{version, context_version, idempotency_key}` → receipt mínimo. Sem campos clínicos editáveis.
- `POST /proposals/{id}/cancel` `{version}` → cancelamento idempotente.
- `GET /proposals/{id}` → proposta/receipt somente após autorização atual e TTL.
- `GET /capabilities?locale=pt-BR|en-US|es` → flags e limites públicos, nunca topologia/segredos.

F2 file/template endpoints não são implementados nesta rodada.

## Schemas e estados

`ProposalKind`: `glucose_single | investigation_open | investigation_message`. `ProposalState`: `DRAFT → READY → EXECUTED|CANCELLED|EXPIRED|INVALIDATED`; READY pode ser editada para nova versão DRAFT/READY. Estados terminais não reabrem. TTL de 15 min; conteúdo terminal apagado em até 24h; tombstone/receipt mantém unicidade.

Campos comuns: UUID opaco, conversation/owner/role/patient e association cycle derivados no servidor, `version`, `context_version`, state, expiry, origin/engine normalizados, payload criptografado, digest canônico. Campo de paciente/destinatário jamais editável pelo modelo. `glucose_single` aceita apenas `0 < mg/dL <= 1000`, data/hora com timezone resolvido, unidade explícita ou confirmada pelo usuário. Mensagem final fica em proposta cifrada e só é persistida no domínio após confirmação. Não incluir conteúdo em eventos/receipt/logs.

Confirmação exige botão/ação humana autenticada, CSRF, versão/contexto exatos, autorização atual, lock da proposta e endpoint de domínio reutilizando a mesma transação. Digest inclui operação, argumentos normalizados, owner/patient/recipient/ciclo, versão/contexto e normalizador. UNIQUE(proposal_id, version) impede efeitos duplos; UNIQUE(owner_id, operation, idempotency_key) e digest incompatível retorna 409. Efeito de domínio + source/proveniência + evento/notificação + receipt + EXECUTED na mesma transação. Retry autorizado retorna receipt; vínculo/sessão revogados negam acesso.

## Autorização e erros

Paciente: somente identidade própria da sessão. Médico: paciente explicitamente escolhido, vínculo ACTIVE e ciclo atual; revalidar em toda leitura, mídia, edição e confirmação. Ausente/alheio responde 404 equivalente. Mudança de sessão, papel, paciente/período ou ciclo incrementa `context_version` e invalida propostas. Autorização precede qualquer carga de contexto/inferência.

Códigos: 401 `authentication_required`; 403 `operation_not_allowed|csrf_failed`; 404 `resource_not_found`; 409 `proposal_version_conflict|context_changed|idempotency_conflict`; 410 `proposal_expired`; 413 `payload_too_large`; 415 `unsupported_media_type`; 422 `invalid_fields|ambiguous_reading`; 429 `quota_exceeded` (+ Retry-After); 503 `capability_unavailable`; 504 `processing_timeout`. Erros sem eco de entrada sensível, stack, prompt ou detalhes do decoder.

## Worker de mídia

Gateway → worker privado por URL/configuração fixa. Autenticação HMAC sobre método/path/timestamp/nonce/body digest; TTL curto, nonce/replay store compartilhado e rotação de segredo. Worker não recebe cookies, IDs de conta/paciente, banco, ferramentas ou egress arbitrário; somente bytes e correlation ID aleatório. Gateway revalida sessão/contexto/vínculo após resposta antes de criar proposta. Corpo nunca é enfileirado ou spooled; bytes contados no stream, memória limitada, decoder fixo, processo cancelável/deadline <=20s; gateway <=25s. Sem fallback externo. Falha/cancelamento libera buffers e não cria efeito.

Limites F1: 10 req/min/conta; 1 job caro/conta; global configurável; texto 2k; imagem 3 MiB/8 MP/estática JPEG-PNG-WebP, 20 OCR/dia; áudio 3 MiB/60s/5 min ASR/dia, formatos testados; consultas 366 dias, páginas <=50 e <=200 leituras; propostas <=10 vivas. Reservas/quota em DB compartilhado ou Redis, nunca worker-local. Upload e computação ficam desabilitados se limite global/worker não configurado.

## Ownership da rodada

Codex/coordenador: `routes.py`, `entities.py`, migrações, config/deps/manifests, contratos, decisões, matriz e integrações transacionais. Claude não está conectado nesta sessão: ownership frontend pendente de transferência explícita; arquivos exclusivos quando integrado: `api.js`, `OverviewPage`, estilos, locales. Antigravity não está conectado: serviço isolado e provisionamento pendentes; módulo `services/media_worker/` reservado para proposta, sem integrar callback não autenticado. Um único owner por rodada para cada arquivo compartilhado; nenhum patch concorrente antes do contrato.
