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

```text
.
|-- alembic/                          # Migrations que instanciam o schema MySQL
|   `-- versions/                     # Schema inicial + core clínico UUID com proveniência
|-- app/
|   |-- main.py                       # Ponto de entrada da aplicação FastAPI
|   |-- api/routes.py                 # Rotas de API e o endpoint report.pdf
|   |-- core/                         # Configuração
|   |-- db/                           # Engine e sessão SQLAlchemy
|   |-- models/                       # Entidades relacionais (pacientes, registros, proveniência)
|   |-- schemas/                      # Schemas Pydantic
|   `-- services/
|       |-- uci_importer.py           # Importador UCI Diabetes (registros brutos + glucose_records)
|       |-- analytics.py              # Métricas materializadas, indicadores, anomalias, clusters
|       |-- manual_entry.py           # Criação transacional de paciente/glicemia manual com proveniência
|       |-- provenance.py             # Geração de artefatos PROV
|       |-- semantic.py               # Grafo RDF e consultas SPARQL
|       `-- clinical_pdf.py           # Gerador do relatório PDF do paciente (pt-BR/en-US/es)
|-- artifacts/
|   |-- provenance/                   # PROV-JSON / PROV-TTL gerados
|   `-- semantic/                     # RDF gerado (TTL)
|-- frontend-react/                   # Frontend React (Vite) consumindo o backend FastAPI
|   |-- public/                       # Assets estáticos servidos pelo frontend
|   `-- src/
|       |-- i18n.js                   # Configuração do react-i18next e resolução de idioma
|       |-- locales/                  # Catálogos de tradução (pt-BR, en-US, es)
|       |-- components/               # App shell, seletor de idioma, UI compartilhada
|       `-- pages/                    # Visão geral e detalhe do paciente
|-- mappings/
|   `-- myglico-core-r2rml-juma.ttl   # Mapeamento R2RML de MySQL para RDF
|-- ontology/
|   `-- mygv-dpo-extension.owl.ttl    # Ontologia OWL do vocabulário mygv:
`-- scripts/
    |-- import_uci_diabetes.py        # Import idempotente do dataset + analytics + PROV + RDF
    |-- init_db.py                    # Sobe MySQL, aplica migrations e importa (só proveniência)
    `-- bootstrap_db.py               # Wrapper de bootstrap para uso local
```

## Execução local do backend

```bash
pip install ".[full]"
alembic upgrade head
python scripts/import_uci_diabetes.py
uvicorn app.main:app --reload
```

`.[full]` traz as ferramentas de analytics/import (numpy, pandas,
scikit-learn, alembic, uvicorn etc.) além das dependências básicas da API.
Um `pip install .` puro instala só o que o código em tempo de execução do
`app.main` precisa — é isso que o deploy no Vercel usa, pra ficar dentro do
limite de tamanho de função (veja "Deploy no Vercel" abaixo).

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

## Deploy no Vercel

O repositório está preparado para um único projeto Vercel que serve o
frontend React e o backend FastAPI juntos, no mesmo domínio (sem precisar de
CORS):

- `vercel.json` builda `frontend-react` (Vite) como saída estática e
  redireciona `/api/*`, `/health` e `/artifacts/*` para `api/index.py`, um
  wrapper fino que importa a aplicação FastAPI real (`app/main.py`). Qualquer
  outro caminho cai para `index.html`, o que mantém o roteamento client-side
  funcionando ao dar refresh na página.
- `requirements.txt` (na raiz) lista as dependências Python do backend para
  o runtime Python do Vercel; mantenha sincronizado com o `pyproject.toml`.
- Configure o **Root Directory** do projeto no Vercel para a raiz do
  repositório (não `frontend-react`) — ele precisa de `api/`,
  `requirements.txt` e `app/` no mesmo build.

Variável de ambiente obrigatória:

- `MYGLICO_DATABASE_URL`: string de conexão do MySQL na nuvem, por exemplo
  `mysql+pymysql://usuario:senha@host:3306/nome_do_banco`. A maioria dos
  provedores de MySQL gerenciado exige TLS — confira se o seu precisa de um
  parâmetro `ssl_mode`/`ssl_ca` na string de conexão.

Antes do primeiro deploy (ou depois de mudanças de schema), rode as
migrations e o import do dataset **uma vez, da sua máquina, contra o banco
na nuvem** — são passos de carga de dados pontuais, não algo que uma
requisição serverless deveria disparar:

```bash
MYGLICO_DATABASE_URL="mysql+pymysql://usuario:senha@host:3306/nome_do_banco" alembic upgrade head
MYGLICO_DATABASE_URL="mysql+pymysql://usuario:senha@host:3306/nome_do_banco" python scripts/import_uci_diabetes.py
```

Limitações conhecidas no Vercel:

- O filesystem da função Python é somente leitura, exceto `/tmp`, que é
  zerado entre cold starts. Todas as rotas da API são leitura no banco (mais
  uma escrita no banco, para entradas manuais de glicemia), então isso não
  afeta o uso normal — mas os endpoints SPARQL `/api/semantic/*` e qualquer
  arquivo em `/artifacts/*` que não esteja versionado no repositório não vão
  ter nada pra ler em produção (o frontend não linka mais pra eles, então
  nada quebra na interface; afeta só essa superfície do backend hoje sem uso).
- `pandas`, `scikit-learn` e `rdflib` são dependências pesadas para uma
  função serverless; espere um cold start bem mais lento que o setup local
  em Docker/uvicorn, e fique de olho no limite de tamanho de função do
  Vercel se adicionar mais dependências.

## Citação

Se você usar este repositório, cite-o usando o arquivo
[`CITATION.cff`](CITATION.cff) — o GitHub renderiza um botão
**"Cite this repository"** a partir dele. Um DOI (Zenodo) será adicionado
assim que um release for arquivado.

## Licença

Apache License 2.0 — veja [`LICENSE`](LICENSE). O dataset UCI Diabetes usado
como base possui seus próprios termos de uso; confirme a citação e a licença
oficiais em `archive.ics.uci.edu`.
