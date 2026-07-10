# MyGlico MVP

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**Português** | [English](README.md)

MVP acadêmico do MyGlico para o recorte da disciplina, usando o dataset
`UCI Diabetes` como base pública para:

- ingestão e normalização em banco relacional;
- camada analítica para indicadores glicêmicos;
- proveniência com `PROV-JSON` e `PROV-TTL`;
- exportação semântica em RDF com consultas SPARQL;
- visualização web com uma camada `React` autocontida, traduzida em
  português (Brasil), inglês (EUA) e espanhol.

## Arquitetura

- `FastAPI` para API e entrega de artefatos.
- `React + Vite` para o frontend principal e autocontido.
- `SQLAlchemy 2.0 + Alembic` para persistência e migrations.
- `MySQL` no Docker Compose e `SQLite` como fallback local autocontido.
- Core clínico limpo com `patients` e `glucose_records`.
- Camada de origem/rastreabilidade com `raw_import_records`,
  `glucose_record_sources` e `data_quality_issues`.
- Proveniência transacional em banco com `provenance_events`.
- Artefatos `PROV-JSON`, `PROV-TTL` e RDF como derivados registrados em
  `provenance_artifacts`.
- `pandas + scikit-learn` para a camada analítica.
- `prov` para proveniência.
- `rdflib` para a camada semântica.
- `react-i18next` na interface web e um gerador de PDF traduzido "na mão"
  para o relatório clínico do paciente.

## Estrutura

- `app/main.py`: aplicação FastAPI.
- `app/api/routes.py`: rotas de API.
- `app/services/uci_importer.py`: download, extração, registros brutos e
  geração de `glucose_records`.
- `app/services/analytics.py`: métricas materializadas, indicadores,
  anomalias e clusterização.
- `app/services/manual_entry.py`: criação transacional de paciente e
  glicemia manual com origem e proveniência.
- `app/services/provenance.py`: geração de artefatos PROV.
- `app/services/semantic.py`: grafo RDF e consultas SPARQL.
- `app/services/clinical_pdf.py`: gerador do relatório PDF clínico do
  paciente, traduzido em pt-BR/en-US/es.
- `frontend-react/`: interface React consumindo o FastAPI, incluindo seus
  próprios assets em `public/` e as traduções em `src/locales/`.
- `scripts/import_uci_diabetes.py`: import idempotente do dataset, analytics
  inicial, PROV e RDF.
- `scripts/bootstrap_db.py`: wrapper de bootstrap para uso local.
- `alembic/versions/20260414_0001_initial.py`: migration inicial.
- `alembic/versions/20260504_0002_clinical_core_uuid.py`: migration para o
  core UUID com origem e proveniência.

## Execução local do backend

```bash
pip install .
alembic upgrade head
python scripts/import_uci_diabetes.py
uvicorn app.main:app --reload
```

Abra `http://127.0.0.1:8001/health` para validar a API ou use o frontend
React em desenvolvimento.

## Execução com Docker

### Ambiente completo de desenvolvimento

```bash
docker compose up --build
```

Portas do ambiente:

- `http://localhost:8000`: frontend React (Vite) com hot reload. Única forma
  de servir a interface web.
- `http://localhost:8001`: backend FastAPI, apenas API e artefatos (sem SPA).
- `localhost:3307`: MySQL do ambiente exposto no host.

No ambiente React, chamadas para `/api`, `/artifacts` e `/health` são
encaminhadas automaticamente para o backend.

### Backend isolado

```bash
docker build -t myglico-mvp .
docker run --rm -p 8001:8001 myglico-mvp
```

O container do backend:

1. aplica as migrations;
2. importa o UCI Diabetes via script se a base estiver vazia;
3. gera analytics inicial, artefatos de proveniência e o grafo RDF;
4. sobe a aplicação FastAPI.

### Inicializar somente MySQL + importação + proveniência

Para subir apenas o MySQL no Docker, aplicar migrations e popular uma base
vazia somente com o dataset UCI Diabetes e a proveniência da importação:

```bash
python scripts/init_db.py --reset-db
```

Esse script para `backend` e `frontend`, sobe somente o serviço `db`, aplica
`alembic upgrade head` e executa a importação com `write_import_provenance`.
Ele não executa analytics, não gera grafo semântico e não sobe a aplicação
web.

A importação local pode levar alguns minutos porque preserva cada linha
bruta, normaliza registros glicêmicos e grava eventos de proveniência. A
tabela `analysis_outbox` pode ser preenchida como fila para processamento
futuro, mas `analysis_runs`, `daily_indicators` e `daily_metrics_current`
permanecem vazias nesse recorte.

Para reutilizar o banco atual sem apagar o volume:

```bash
python scripts/init_db.py
```

## Variáveis úteis

- `MYGLICO_DATABASE_URL`: troca a URL do banco.
- `MYGLICO_DEBUG=true`: ativa modo de debug do FastAPI.
- `VITE_API_TARGET`: define o backend alvo do frontend React em
  desenvolvimento.

## Artefatos gerados

- `artifacts/provenance/*.json`
- `artifacts/provenance/*.ttl`
- `artifacts/semantic/*.ttl`

## Observações do recorte

- O indicador principal é baseado em medições observadas, não em CGM
  contínuo.
- Horários alinhados a `08:00`, `12:00`, `18:00` e `22:00` são marcados como
  `slot_aligned` por poderem representar tempos lógicos do log em papel.
- O MVP prioriza explicabilidade e rastreabilidade para a disciplina.

## Citação

Se você usar este repositório, cite-o usando o arquivo
[`CITATION.cff`](CITATION.cff) — o GitHub renderiza um botão
**"Cite this repository"** a partir dele. Um DOI (Zenodo) será adicionado
assim que um release for arquivado.

## Licença

Apache License 2.0 — veja [`LICENSE`](LICENSE). O dataset UCI Diabetes usado
como base possui seus próprios termos de uso; confirme a citação e a licença
oficiais em `archive.ics.uci.edu`.
