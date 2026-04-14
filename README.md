# MyGlico MVP

MVP acadêmico do MyGlico para o recorte da disciplina, usando o dataset `UCI Diabetes` como base pública para:

- ingestão e normalização em banco relacional;
- camada analítica para indicadores glicêmicos;
- proveniência com `PROV-JSON` e `PROV-TTL`;
- exportação semântica em RDF com consultas SPARQL;
- visualização simples com `FastAPI + Jinja2`.

## Arquitetura

- `FastAPI` para backend e páginas HTML.
- `SQLAlchemy 2.0 + Alembic` para persistência e migrations.
- `SQLite` por padrão para manter o container autocontido.
- `pandas + scikit-learn` para a camada analítica.
- `prov` para proveniência.
- `rdflib` para a camada semântica.

O projeto foi desenhado para crescer depois para `MySQL` ou `PostgreSQL` alterando `DATABASE_URL`.

## Estrutura

- `app/main.py`: aplicação FastAPI.
- `app/services/uci_importer.py`: download, extração e normalização do UCI Diabetes.
- `app/services/analytics.py`: cálculo de indicadores, detecção de anomalias e clusterização.
- `app/services/provenance.py`: geração de artefatos PROV.
- `app/services/semantic.py`: grafo RDF e consultas SPARQL.
- `scripts/bootstrap_db.py`: bootstrap idempotente da base.
- `alembic/versions/20260414_0001_initial.py`: migration inicial.

## Execução local

```bash
pip install .
alembic upgrade head
python scripts/bootstrap_db.py
uvicorn app.main:app --reload
```

Abra `http://127.0.0.1:8000`.

## Execução com Docker

```bash
docker build -t myglico-mvp .
docker run --rm -p 8000:8000 myglico-mvp
```

O container:

1. aplica as migrations;
2. importa o UCI Diabetes se a base estiver vazia;
3. gera analytics, artefatos de proveniência e o grafo RDF;
4. sobe a aplicação web.

## Variáveis úteis

- `MYGLICO_DATABASE_URL`: troca a URL do banco.
- `MYGLICO_DEBUG=true`: ativa modo de debug do FastAPI.

## Artefatos gerados

- `artifacts/provenance/*.json`
- `artifacts/provenance/*.ttl`
- `artifacts/semantic/*.ttl`

## Observações do recorte

- O indicador principal é baseado em medições observadas, não em CGM contínuo.
- Horários alinhados a `08:00`, `12:00`, `18:00` e `22:00` são marcados como `slot_aligned` por poderem representar tempos lógicos do log em papel.
- O MVP prioriza explicabilidade e rastreabilidade para a disciplina.
