# MyGlico MVP

MVP academico do MyGlico para o recorte da disciplina, usando o dataset `UCI Diabetes` como base publica para:

- ingestao e normalizacao em banco relacional;
- camada analitica para indicadores glicemicos;
- proveniencia com `PROV-JSON` e `PROV-TTL`;
- exportacao semantica em RDF com consultas SPARQL;
- visualizacao web com uma camada `React` autocontida.

## Arquitetura

- `FastAPI` para API e entrega de artefatos.
- `React + Vite` para o frontend principal e autocontido.
- `SQLAlchemy 2.0 + Alembic` para persistencia e migrations.
- `MySQL` no Docker Compose e `SQLite` como fallback local autocontido.
- Core clinico limpo com `patients` e `glucose_records`.
- Camada de origem/rastreabilidade com `raw_import_records`, `glucose_record_sources` e `data_quality_issues`.
- Proveniencia transacional em banco com `provenance_events`.
- Artefatos `PROV-JSON`, `PROV-TTL` e RDF como derivados registrados em `provenance_artifacts`.
- `pandas + scikit-learn` para a camada analitica.
- `prov` para proveniencia.
- `rdflib` para a camada semantica.

## Estrutura

- `app/main.py`: aplicacao FastAPI.
- `app/api/routes.py`: rotas de API e entrega do SPA React buildado.
- `app/services/uci_importer.py`: download, extracao, registros brutos e geracao de `glucose_records`.
- `app/services/analytics.py`: metricas materializadas, indicadores, anomalias e clusterizacao.
- `app/services/manual_entry.py`: criacao transacional de paciente e glicemia manual com origem e proveniencia.
- `app/services/provenance.py`: geracao de artefatos PROV.
- `app/services/semantic.py`: grafo RDF e consultas SPARQL.
- `frontend-react/`: interface React consumindo o FastAPI, incluindo seus proprios assets em `public/`.
- `scripts/import_uci_diabetes.py`: import idempotente do dataset, analytics inicial, PROV e RDF.
- `scripts/bootstrap_db.py`: wrapper de bootstrap para uso local.
- `alembic/versions/20260414_0001_initial.py`: migration inicial.
- `alembic/versions/20260504_0002_clinical_core_uuid.py`: migration para o core UUID com origem e proveniencia.

## Execucao local do backend

```bash
pip install .
alembic upgrade head
python scripts/import_uci_diabetes.py
uvicorn app.main:app --reload
```

Abra `http://127.0.0.1:8001/health` para validar a API ou use o frontend React em desenvolvimento.

## Execucao com Docker

### Ambiente completo de desenvolvimento

```bash
docker compose up --build
```

Portas do ambiente:

- `http://localhost:8000`: frontend React principal com hot reload.
- `http://localhost:8001`: backend FastAPI, API, artefatos e SPA React buildado na raiz.
- `localhost:3307`: MySQL do ambiente exposto no host.

No ambiente React, chamadas para `/api`, `/artifacts` e `/health` sao encaminhadas automaticamente para o backend.

### Backend isolado

```bash
docker build -t myglico-mvp .
docker run --rm -p 8001:8001 myglico-mvp
```

O container do backend:

1. aplica as migrations;
2. importa o UCI Diabetes via script se a base estiver vazia;
3. gera analytics inicial, artefatos de proveniencia e o grafo RDF;
4. sobe a aplicacao FastAPI.

### Inicializar somente MySQL + importacao + proveniencia

Para subir apenas o MySQL no Docker, aplicar migrations e popular uma base vazia somente com o dataset UCI Diabetes e a proveniencia da importacao:

```bash
python scripts/init_db.py --reset-db
```

Esse script para `backend` e `frontend`, sobe somente o servico `db`, aplica `alembic upgrade head` e executa a importacao com `write_import_provenance`. Ele nao executa analytics, nao gera grafo semantico e nao sobe a aplicacao web.

A importacao local pode levar alguns minutos porque preserva cada linha bruta, normaliza registros glicemicos e grava eventos de proveniencia. A tabela `analysis_outbox` pode ser preenchida como fila para processamento futuro, mas `analysis_runs`, `daily_indicators` e `daily_metrics_current` permanecem vazias nesse recorte.

Para reutilizar o banco atual sem apagar o volume:

```bash
python scripts/init_db.py
```

## Variaveis uteis

- `MYGLICO_DATABASE_URL`: troca a URL do banco.
- `MYGLICO_DEBUG=true`: ativa modo de debug do FastAPI.
- `VITE_API_TARGET`: define o backend alvo do frontend React em desenvolvimento.

## Artefatos gerados

- `artifacts/provenance/*.json`
- `artifacts/provenance/*.ttl`
- `artifacts/semantic/*.ttl`

## Observacoes do recorte

- O indicador principal e baseado em medicoes observadas, nao em CGM continuo.
- Horarios alinhados a `08:00`, `12:00`, `18:00` e `22:00` sao marcados como `slot_aligned` por poderem representar tempos logicos do log em papel.
- O MVP prioriza explicabilidade e rastreabilidade para a disciplina.
