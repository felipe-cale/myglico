# Suíte E2E (Playwright) — MyGlico

Infraestrutura de ponta a ponta contra **backend real + frontend real** (sem
MCP, sem mock). É a entrega da task **E1** do `features/a-desenvolver/BACKLOG.md`;
os cenários estão como `test.fixme` e serão preenchidos/executados quando o
coordenador indicar que backend (B1–B5) e frontend (F1) estão integrados.

## Decisões (registradas aqui por serem só desta suíte)

| Tema | Decisão | Motivo |
| --- | --- | --- |
| Onde instalar o Playwright | devDependency de `frontend-react` (`@playwright/test`) | Convenção do Playwright: a config e o `node_modules` precisam estar no mesmo projeto; `tests/` na raiz é reservado para Python e não resolve `@playwright/test` (verificado empiricamente: `Cannot find package '@playwright/test'`). Também é o que o BACKLOG já fixou. |
| Config | `frontend-react/playwright.config.mjs` (ESM, igual ao `vite.config.mjs`) | Sem TypeScript no projeto; Playwright roda `.mjs` nativamente. |
| Especificações | `frontend-react/e2e/specs/*.spec.mjs` (1 arquivo por grupo de fluxo) | Convenção Playwright de diretório de testes vizinho à config. |
| Fixtures | `frontend-react/e2e/fixtures/` | Perfis sintéticos + cliente do contrato de API. |
| Portas | backend `127.0.0.1:8101`, Vite `localhost:8100` com proxy `/api` → `:8101` (configuráveis) | Separadas das portas de dev 8000/8001 para que um servidor de dev nunca colida nem sirva as asserções. |
| Banco de teste | SQLite descartável em `data/e2e-myglico.db` (ignorado pelo `data/*.db` do `.gitignore`), **recriado a cada execução** por `e2e/scripts/start-backend.mjs` | Nunca o banco de dev/prod. O `webServer` do Playwright força `reuseExistingServer: false` para que um servidor de dev preso na porta não sirva as asserções. |
| Chaves | `MYGLICO_ENCRYPTION_KEY_V1` / `MYGLICO_LOOKUP_HMAC_KEY` geradas por execução na config (ou via ambiente) | Chave efêmera fora do Git; como muda a cada run, o banco é recriado junto. |
| Senhas | Geradas em runtime por `fixtures/profiles.mjs` (`MYGLICO_E2E_PASSWORD` para fixar localmente) | Proibição de senha em claro em arquivo versionado ou log. |
| Esperas | Somente por estado/resposta (roles acessíveis, resposta de rede, contadores) | Proibição de `sleep` arbitrário (PROMPT-ORCA.md). |

## Como executar

```bash
pip install ".[full]" ".[test]"   # alembic/uvicorn + pytest (integração)
cd frontend-react
npm install                        # instala também @playwright/test
npx playwright install chromium    # uma vez por máquina
npx playwright test                # sobe backend (:8101) + Vite (:8100) sozinho
npx playwright test --list         # só lista (não sobe servidor) — útil para conferir cobertura
npx playwright test e2e/specs/03-search-and-link-lifecycle.spec.mjs
```

Variáveis opcionais: `MYGLICO_E2E_PASSWORD`, `MYGLICO_E2E_RUN_ID`,
`MYGLICO_ENCRYPTION_KEY_V1`, `MYGLICO_LOOKUP_HMAC_KEY`,
`MYGLICO_E2E_DATABASE_URL` / `MYGLICO_E2E_DATABASE_FILE` (para apontar a outro
banco descartável), `MYGLICO_E2E_RESET_DB=0` (manter o arquivo atual).

Relatórias/`trace`/`screenshot`/`video` caem em `e2e/.artifacts/` (ignorado).
Só dados sintéticos entram em evidência — revisar traces antes de anexar.

## Perfis sintéticos (`fixtures/profiles.mjs`)

| Perfil | Papel | Uso |
| --- | --- | --- |
| `patientA` | paciente | protagonista dos fluxos de paciente |
| `patientB` | paciente | isolamento cruzado (AUT-CA-12) |
| `doctorA` | médico | destinatário padrão de vínculos/investigações |
| `doctorB` | médico | segundo médico, negações e isolamento (AUT-CA-13/15) |
| `dualRole` | paciente **e** médico | troca de contexto (AUT-CA-19, CSCW-CA-33) |

- e-mails no domínio reservado `@e2e.myglico.invalid` (não roteável) com sufixo
  de execução; CRM/UF são dados sintéticos (`9000001/SP`, `9000002/RJ`,
  `9000003/MG`) e não representam inscrição real.
- senha aleatória por execução, só em memória; nunca logada.
- sessões: `apiSession` (contexto HTTP isolado por perfil) e `browserSession`
  (aba isolada por perfil, com login via API real quando conveniente).

`fixtures/api.mjs` fala exatamente o contrato de
`features/a-desenvolver/CONTRATOS-API.md`; `fixtures/routes.mjs` guarda as rotas
de frontend (**provisórias** — reconciliar com o router final do F1 em um só
lugar) e os endpoints legados usados nas sondagens de guarda.

## Mapa dos 10 grupos × 68 critérios

Grupos conforme `features/a-desenvolver/PROMPT-ORCA.md` ("Testes end-to-end",
itens 1–10). Critérios conforme `features/a-desenvolver/MATRIZ-ACEITE.md`.

| # | Arquivo | Grupos de fluxo | Critérios |
| --- | --- | --- | --- |
| 1 | `specs/01-public-landing.spec.mjs` | Landing pública, sem chamadas/dados clínicos, rotas privadas e API/PDF direto sem sessão | AUT-CA-01, AUT-CA-02, AUT-CA-23, CSCW-CA-35 |
| 2 | `specs/02-auth-registration-session.spec.mjs` | Cadastro por papel, validação, login sem confirmação, sessão, logout, botão voltar, troca de conta/contexto | AUT-CA-03, AUT-CA-04, AUT-CA-05, AUT-CA-06, AUT-CA-08, AUT-CA-09, AUT-CA-11, AUT-CA-19, AUT-CA-20 |
| 3 | `specs/03-search-and-link-lifecycle.spec.mjs` | Busca por SHORTID e CRM+UF, perfil mínimo, solicitar/rejeitar/cancelar/aceitar, sem acesso em pendência | AUT-CA-10, CSCW-CA-01, CSCW-CA-02, CSCW-CA-03, CSCW-CA-04, CSCW-CA-05 |
| 4 | `specs/04-revocation.spec.mjs` | Revogação por cada papel com sessão/canal abertos, encerramento administrativo, histórico, novo aceite | AUT-CA-14, CSCW-CA-06, CSCW-CA-07, CSCW-CA-08, CSCW-CA-09, CSCW-CA-10, CSCW-CA-32 |
| 5 | `specs/05-investigation-opening.spec.mjs` | Abertura pelos dois papéis com/sem evento, destinatário, sem médico ativo, evento alheio, isolamento | CSCW-CA-13, CSCW-CA-14, CSCW-CA-15, CSCW-CA-16, CSCW-CA-17, AUT-CA-12, AUT-CA-13, AUT-CA-15 |
| 6 | `specs/06-messaging-and-closure.spec.mjs` | Troca de mensagens, autoria, ordem, AwaitingRole, vazio/limites/XSS, encerramento, pós-CLOSED | CSCW-CA-18, CSCW-CA-20, CSCW-CA-21, CSCW-CA-22, CSCW-CA-30, CSCW-CA-33, AUT-CA-15 (sec.) |
| 7 | `specs/07-atypical-day-invitation.spec.mjs` | Convite, Ver o dia/Agora não, abertura explícita, deduplicação, histórico UCI | CSCW-CA-36, CSCW-CA-37, CSCW-CA-38, CSCW-CA-45 |
| 8 | `specs/08-notifications-and-unread.spec.mjs` | Notificações/não lidas nos dois sentidos, persistência, leitura efetiva, paginação, falha/recuperação | CSCW-CA-19, CSCW-CA-29, CSCW-CA-39, CSCW-CA-40, CSCW-CA-41, CSCW-CA-42, CSCW-CA-43, CSCW-CA-44 |
| 9 | `specs/09-atypical-popup-filters.spec.mjs` | Popup, contagem, dias não consecutivos, interseção/limpeza, meia-noite/fuso, paginação, acessibilidade, estados | CSCW-CA-23, CSCW-CA-24, CSCW-CA-25, CSCW-CA-26, CSCW-CA-27 |
| 10 | `specs/10-i18n-and-pdf.spec.mjs` | Três idiomas essenciais, PDF nos três `lang` com datas/números e autorização | AUT-CA-01, AUT-CA-12, AUT-CA-23, CSCW-CA-35 (todos os `lang`) |

Critérios que **a UI não comprova** ficam em `tests/integration/` (pytest):
AUT-CA-07, AUT-CA-16, AUT-CA-17, AUT-CA-18, AUT-CA-21, AUT-CA-22,
CSCW-CA-11, CSCW-CA-12, CSCW-CA-28, CSCW-CA-31, CSCW-CA-34 — além das versões
de banco/logs dos demais. Com as duas suítes, os **68 critérios** estão
referenciados (ver `tests/integration/README.md`).

## Estado atual (2026-10-07)

- 75 cenários em 10 arquivos, **nenhum `test.fixme`**. Última execução completa:
  72 passaram, 2 falhas esperadas (`test.fail`, achados N1 e A10 residual em
  `09-*`), 1 skip (CSCW-CA-29, outbox sem consumidor — B4).
- Infraestrutura corrigida (REVISAO-FINAL.md A16): portas dedicadas 8100/8101
  (`MYGLICO_E2E_FRONTEND_PORT`/`MYGLICO_E2E_BACKEND_PORT`), proxy para
  `127.0.0.1` (o `localhost` resolvia para ::1 → 500), frontend em `localhost`
  (cookie `Secure`), healthcheck de `/health` **através do proxy**, locale
  `pt-BR` fixo e textos lidos de `src/locales` (`fixtures/i18n.mjs`),
  `apiSession.registerAccount/login/logout`, perfis únicos por teste,
  `X-Forwarded-For` sintético por sessão (limites por IP do A5) e
  `scripts/seed_atypical_days.py` (análise real para gerar dias atípicos).
- Perfil dual-role removido (decisão de produto: um papel por conta).
- Resultados por critério: `features/a-desenvolver/MATRIZ-ACEITE.md`.
