# Testes de integração de backend (pytest)

Testes reais para os critérios que **a UI não comprova**: atomicidade/rollback,
concorrência, criptografia/AAD, idempotência, outbox, proveniência e
autorização em nível de API/banco. Eles exercitam o backend atual em processo
(`starlette.testclient.TestClient` + sessões SQLAlchemy), sem servidor, sem
rede e sem tocar no banco de desenvolvimento.

## Estado atual

Todos os testes rodam. Nenhum arquivo tem `skip` em nível de módulo. Cada
teste termina em um de três resultados:

- **pass**: o critério foi verificado por asserção;
- **`xfail(strict=True)`**: o teste exercita um defeito conhecido. O motivo
  cita o ID do achado (por exemplo, `A4` em `REVISAO-FINAL.md` ou `NEW-1`).
  Por ser *strict*, quando a correção entrar o teste vira XPASS e falha, e aí
  basta remover o marcador;
- **`pytest.skip` dentro do teste**: o critério não é verificável no código
  atual. O motivo cita o achado e informa o que foi verificado antes do skip.

Última execução (`python -m pytest tests -q -rxXs`): **51 passed, 1 skipped,
1 xfailed** (45 de integração + 8 de `tests/test_clinical_pdf.py`).

- Skip: `CSCW-CA-29`. A outbox não tem consumidor ou retry (**B4**). O teste
  verifica antes que a linha de outbox é gravada `PENDING` junto com a
  mutação e o evento.
- `CSCW-CA-32` passa. O endpoint `GET /api/patients/{id}/provenance`
  (correção de A12) já existe: o teste descobre as rotas de
  proveniência/histórico e exige 200 enquanto o vínculo está ATIVO e negação
  depois da revogação. O teste só chama `pytest.skip` (citando A12) se essas
  rotas deixarem de existir.
- **NEW-1 corrigido (2026-10-07)**: `context_label` misto é normalizado para
  valores Python `str | None`, e os cálculos toleram escalares não textuais.
  O teste de integração antes `xfail` virou teste normal e passou isoladamente
  (**1 passed**). A suíte completa ainda não foi reexecutada após esta correção.

Os achados A4 (senha demo regravada), A5 (limite de tentativas), A6
(`notes` em claro), A9 (enxurrada de convites) e A12 (endpoint de
proveniência) já estão corrigidos no backend. Os testes correspondentes
passaram a ser guardas de regressão comuns.

## Setup

```bash
pip install ".[full]" ".[test]"
python -m pytest tests/integration -q -rxXs
python -m pytest tests -q -rxXs          # inclui tests/test_clinical_pdf.py
```

`conftest.py` garante o isolamento **antes** de qualquer import de `app`:

- `MYGLICO_DATABASE_URL` é **sobrescrito** para `data/integration.db`
  (SQLite descartável, ignorado pelo padrão `data/*.db` do `.gitignore`).
  Se precisar de outro banco descartável, use `MYGLICO_INTEGRATION_DATABASE_URL`.
  Uma URL de dev/prod no shell nunca é usada. Se `app.db.session` já tiver
  sido importado com outra URL, a execução aborta.
- `MYGLICO_ENCRYPTION_KEY_V1` e `MYGLICO_LOOKUP_HMAC_KEY` são chaves hex de
  64 caracteres (`secrets.token_hex(32)`) geradas em runtime. Uma chave hex
  válida que já esteja no ambiente é reaproveitada. Nenhum segredo é
  versionado.
- `MYGLICO_PROVENANCE_DIR` e `MYGLICO_RAW_DATA_DIR` apontam para um diretório
  temporário, então o importador não escreve em `artifacts/`.
- A fixture `prepared_database` apaga o arquivo e roda `alembic upgrade head`
  uma vez por sessão.
- A fixture `world` cria atores (paciente/médico), cada um com seu próprio
  `TestClient`, cookie jar e endereço de cliente. Os e-mails são únicos em
  `@integration.myglico.invalid` e as senhas são aleatórias. Também oferece
  helpers de vínculo e investigação, seed de leituras/indicadores, contagens,
  eventos e triggers SQLite que injetam falhas (`failing_insert`).
- Uma fixture autouse zera o limitador de tentativas em memória
  (`app.core.rate_limit`, correção de A5) entre testes.
- Os critérios do importador UCI rodam `scripts/import_uci_diabetes.py
  --provision-demo-accounts` de verdade, com o download trocado por um
  fixture offline no formato UCI. Não há acesso à rede.

## Arquivos e critérios

| Arquivo | Critérios | Resultado atual |
| --- | --- | --- |
| `test_atomicity_rollback.py` | AUT-CA-05, CSCW-CA-13, CSCW-CA-28 | 4 passed |
| `test_concurrency.py` | AUT-CA-09, AUT-CA-18, CSCW-CA-03, CSCW-CA-04, CSCW-CA-30 | 5 passed |
| `test_crypto_and_secrets.py` | AUT-CA-07, AUT-CA-08, AUT-CA-22, AUT-CA-23, CSCW-CA-31 | 7 passed |
| `test_idempotency_recompute_import.py` | AUT-CA-16, AUT-CA-17, AUT-CA-21, CSCW-CA-11, CSCW-CA-12, CSCW-CA-22, CSCW-CA-34, CSCW-CA-45 | 10 passed, 1 xfailed (NEW-1) |
| `test_outbox_and_delivery.py` | CSCW-CA-19, CSCW-CA-29, CSCW-CA-43, CSCW-CA-44 | 4 passed, 1 skipped (B4) |
| `test_authorization_boundaries.py` | AUT-CA-11, AUT-CA-12, AUT-CA-13, CSCW-CA-16, CSCW-CA-17, CSCW-CA-32 | 7 passed |
| `test_provenance_events.py` | CSCW-CA-04, CSCW-CA-05, CSCW-CA-12, CSCW-CA-28, CSCW-CA-37, CSCW-CA-43 + ator humano × SoftwareAgent | 6 passed |

Contas com os dois papéis não são testadas: por decisão do produto, cada conta
é Patient **ou** Doctor. Por isso AUT-CA-19 e CSCW-CA-33 são "Não aplicável".

Junto com a suíte E2E (`frontend-react/e2e/`), os **68 critérios** da
`MATRIZ-ACEITE.md` estão referenciados.
