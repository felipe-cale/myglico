# Contrato de API acordado — coordenador (para desenvolvimento paralelo)

Este contrato é a interface combinada entre o backend (codex) e o frontend
(antigravity) enquanto o backend ainda está em implementação. Nomes de rotas e
payloads são o contrato vigente; o codex pode ajustar detalhes menores por
convenção do projeto, mas deve registrar qualquer divergência relevante na
seção "Log de progresso" do BACKLOG.md para o coordenador reconciliar.

Convenção: todas as rotas autenticadas usam cookie de sessão HttpOnly (ver
BACKLOG.md, decisão 1). Respostas de erro: `{"detail": "mensagem genérica"}`
com status HTTP apropriado (400/401/403/404/409).

## Autenticação e conta (feature 01)

Cada `UserAccount` possui no máximo um papel de domínio: `Patient` ou
`Doctor`, nunca ambos. Para usar os dois papéis, a pessoa precisa de contas e
endereços de e-mail distintos. O servidor rejeita a reutilização de um e-mail
existente para registrar o segundo papel.

- `POST /api/auth/register` — body `{role: "patient"|"doctor", email,
  password, password_confirmation, display_name, crm?, uf?,
  privacy_notice_accepted}` → 201
  Every registration (patient or doctor) requires `privacy_notice_accepted:
  true` (SDD1 §8.2); the server persists the acceptance time on the account.
  Doctor registration also requires non-empty `crm` and `uf`. The UCI demo-account importer provisions its own demo doctor
  outside this public registration endpoint.
  `glucose_records.measured_at` is interpreted as naive UTC; analytics dates,
  date filters, and serialized patient event dates use `Patient.timezone`, which
  defaults to `America/Sao_Paulo`.
  `{account: {roles: ["patient"|"doctor"]}, patient?: {id, short_id,
  display_name}, doctor?: {id, short_id, name, crm, uf, is_demo,
  declared_verified}}`. Seta cookie de sessão.
- `POST /api/auth/login` — body `{email, password}` → 200 mesmo shape de
  sessão abaixo. 401 genérico em falha.
- `POST /api/auth/logout` → 204, invalida sessão no servidor e limpa cookie.
- `GET /api/auth/session` — 200 se autenticado: `{authenticated: true,
  patient?: {id, short_id, display_name}, doctor?: {id, short_id, name, crm,
  uf, is_demo, declared_verified}}`; 200 `{authenticated: false}` se não.
- `GET /api/doctors/search?short_id=` ou `?crm=&uf=` (paciente autenticado) →
  `{doctor: {short_id, name, crm, uf, is_demo, declared_verified,
  link_status: "none"|"pending"|"active"} | null}`.

## Vínculos (feature 02, seção 4-5)

- `POST /api/doctor-links` — body `{doctor_short_id}` (paciente autenticado)
  → 201 `{link: {id, status: "pending", doctor: {...}, version}}`.
- `GET /api/doctor-links` — lista vínculos do contexto atual (paciente: seus
  médicos; médico: solicitações+pacientes).
- `POST /api/doctor-links/{id}/confirm` | `/reject` (médico destinatário,
  body `{version}`) → 200 `{link: {...}}` ou 409 se versão desatualizada.
- `POST /api/doctor-links/{id}/cancel` (paciente solicitante, body `{version}`;
  versão ausente retorna 422 e versão desatualizada retorna 409).
- `POST /api/doctor-links/{id}/revoke` (qualquer participante, body
  `{reason?, version}`).

## Dias atípicos e proveniência (feature 02, seção 9)

- `GET /api/patients/{id}/atypical-days?start_date=&end_date=` → lista de
  dias com `{indicator_id, date, reason_summary, has_investigation}`.
- `GET /api/patients/{id}/atypical-day-prompts` → convites ainda não
  respondidos (`status: "created"`) do paciente logado, paginados e agrupados
  em lotes; convites adiados não voltam a ser listados.
- `POST /api/atypical-day-prompts/{indicator_id}/defer` — "Agora não".

## Investigações / CSCW (feature 02, seção 6-8)

- `POST /api/investigations` — body `{doctor_id|patient_id (conforme papel
  do autor), atypical_day_event_id?, title, initial_message}` → 201.
- `GET /api/investigations?status=&counterpart_id=` — lista autorizada.
- `GET /api/investigations/{id}` — detalhe + mensagens paginadas.
- `POST /api/investigations/{id}/messages` — body `{content,
  idempotency_key?}`.
- `POST /api/investigations/{id}/read` — body `{up_to_sequence}`.
- `POST /api/investigations/{id}/close` — body `{observation?, version}`.

## Notificações (feature 02, seção 11)

- `GET /api/notifications?unread_only=` → lista + `unread_count`.
- `POST /api/notifications/{id}/read`.
- `GET /api/notifications/unread-summary` → `{notifications_unread,
  messages_unread}` (contadores distintos, conforme SDD2 11.2).

## Adendo pós-revisão (correção de achados REVISAO-FINAL.md)

- **Contexto Paciente/Médico (A3) — descontinuado por decisão do produto**:
  contas com os dois papéis não são suportadas. Cada conta é ligada a Patient
  OU Doctor, nunca ambos; uma pessoa que precise dos dois papéis usa e-mails e
  contas separados. Não enviar nem interpretar `X-Context`.
- **Filtro por dias exatos (A2)**: `GET /api/patients/{id}/atypical-days` e
  o detalhamento aceitam `dates=YYYY-MM-DD,YYYY-MM-DD,...` (lista) além de
  `start_date`/`end_date`. Quando `dates` está presente, filtra exatamente
  esses dias (sem preencher o intervalo). Frontend: ao selecionar dias não
  consecutivos no popup, envia a lista; "Limpar seleção de dias" remove só
  esse parâmetro, preservando `start_date`/`end_date` dos demais filtros.
- **Convites dispensados (A7)**: `GET /api/patients/{id}/atypical-day-prompts`
  já devolve `status`; o cliente deve filtrar/exibir apenas `status=created`
  como banner ativo (`deferred` fica acessível só por histórico/card).

## i18n

Toda string nova do frontend precisa de chave em `pt-BR`, `en-US` e `es`
(`frontend-react/src/locales/*.json`), e no PDF (`STRINGS` em
`app/services/clinical_pdf.py`) se afetar relatório clínico.

## Contrato implementado - origem historica da investigacao (CSCW-CA-22)

Registrada em 2026-10-08 pelo worker de frontend. O frontend já consome este
campo (`InvestigationOrigin.jsx`) e, enquanto ele não existir, cai no texto
genérico atual.

- `GET /api/investigations` e `GET /api/investigations/{id}` acrescentam ao
  resumo da investigação:
  `origin: {indicator_id, date: "YYYY-MM-DD", analysis_run_id,
  is_current_classification: bool} | null`.
  - `null` quando `atypical_day_event_id` é nulo.
  - `date` e `analysis_run_id` vêm do indicador histórico preservado
    (`atypical_day_event_id`).
  - `is_current_classification` é `true` quando, na análise mais recente do
    paciente (a mesma fonte do card e do popup), a mesma **data** continua com
    `anomaly_flag = true`. É `false` quando a data não está mais classificada
    como atípica ou não existe na análise atual.
  - A comparação é **por data**, não por ID: os IDs dos indicadores mudam a
    cada recálculo (B9).
- UI: com `is_current_classification === false`, aparece o selo
  "Classificação anterior" e um texto dizendo que o dia era atípico na
  análise da época e não é mais (SDD2 §7.4).

- Current-analysis lookup includes completed patient-scoped runs even when no indicator rows were produced, so an empty newer execution clears older classifications. Global runs are associated with a patient through their DailyIndicator rows.
