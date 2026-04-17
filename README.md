# MyGlico MVP

MVP academico do MyGlico para o recorte da disciplina, usando o dataset `UCI Diabetes` como base publica para:

- ingestao e normalizacao em banco relacional;
- camada analitica para indicadores glicemicos;
- proveniencia com `PROV-JSON` e `PROV-TTL`;
- exportacao semantica em RDF com consultas SPARQL;
- visualizacao web com `FastAPI` e uma nova camada `React`.

## Arquitetura

- `FastAPI` para API, front legado em Jinja e entrega de artefatos.
- `React + Vite` para o novo frontend principal.
- `SQLAlchemy 2.0 + Alembic` para persistencia e migrations.
- `SQLite` por padrao para manter o ambiente autocontido.
- `pandas + scikit-learn` para a camada analitica.
- `prov` para proveniencia.
- `rdflib` para a camada semantica.

O projeto foi desenhado para crescer depois para `MySQL` ou `PostgreSQL` alterando `MYGLICO_DATABASE_URL`.

## Estrutura

- `app/main.py`: aplicacao FastAPI.
- `app/api/routes.py`: rotas HTML, API e preview React buildado.
- `app/services/uci_importer.py`: download, extracao e normalizacao do UCI Diabetes.
- `app/services/analytics.py`: calculo de indicadores, deteccao de anomalias e clusterizacao.
- `app/services/provenance.py`: geracao de artefatos PROV.
- `app/services/semantic.py`: grafo RDF e consultas SPARQL.
- `frontend-react/`: nova interface React consumindo o FastAPI.
- `scripts/bootstrap_db.py`: bootstrap idempotente da base.
- `alembic/versions/20260414_0001_initial.py`: migration inicial.

## Execucao local do backend

```bash
pip install .
alembic upgrade head
python scripts/bootstrap_db.py
uvicorn app.main:app --reload
```

Abra `http://127.0.0.1:8000`.

## Execucao com Docker

### Ambiente completo de desenvolvimento

```bash
docker compose up --build
```

Portas do ambiente:

- `http://localhost:8000`: frontend React principal com hot reload.
- `http://localhost:8001`: interface legada em FastAPI + Jinja com hot reload.

No ambiente React, chamadas para `/api`, `/artifacts`, `/static` e `/health` sao encaminhadas automaticamente para o backend legado.

### Backend isolado

```bash
docker build -t myglico-mvp .
docker run --rm -p 8000:8000 myglico-mvp
```

O container do backend:

1. aplica as migrations;
2. importa o UCI Diabetes se a base estiver vazia;
3. gera analytics, artefatos de proveniencia e o grafo RDF;
4. sobe a aplicacao FastAPI.

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
