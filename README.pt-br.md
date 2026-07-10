# MyGlico MVP

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**Português** | [English](README.md)

O MyGlico é um MVP acadêmico de acompanhamento glicêmico, desenvolvido como
trabalho de disciplina. Usando o dataset público `UCI Diabetes` como fonte
de dados, este repositório demonstra:

- ingestão e normalização em banco relacional;
- camada analítica para indicadores glicêmicos;
- proveniência com `PROV-JSON` e `PROV-TTL`;
- exportação semântica em RDF com consultas SPARQL;
- visualização web com uma camada `React` autocontida, traduzida em
  português (Brasil), inglês (EUA) e espanhol, incluindo um relatório
  clínico em PDF localizado por paciente.

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

O extra `full` adiciona as ferramentas de analytics e importação (numpy,
pandas, scikit-learn, alembic, uvicorn etc.) às dependências básicas da API.
Um `pip install .` simples instala apenas os pacotes exigidos pela API em
tempo de requisição — o mesmo conjunto usado pela implantação hospedada para
permanecer dentro do limite de tamanho de função da plataforma (veja
"Implantação no Vercel" abaixo).

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

## Implantação no Vercel

Para fins de demonstração, o projeto pode ser hospedado como um único
projeto Vercel que serve o frontend React e o backend FastAPI sob o mesmo
domínio, com uma instância gerenciada de MySQL como banco de dados. Esse
arranjo mantém a demonstração autocontida: frontend e API compartilham a
mesma origem (dispensando configuração de CORS), e o banco de dados é o
único serviço externo.

### Arquitetura da implantação

- `vercel.json` define o build: o frontend é compilado com Vite como saída
  estática (`frontend-react/dist`), enquanto `/api/*`, `/health` e
  `/artifacts/*` são reescritos para `api/index.py` — um adaptador fino que
  expõe a aplicação FastAPI (`app/main.py`) como função serverless. Os
  demais caminhos caem para `index.html`, preservando o roteamento
  client-side ao recarregar a página.
- `requirements.txt` (raiz do repositório) lista as dependências Python
  instaladas para a função serverless. Ele é intencionalmente mais restrito
  que o extra `full` do `pyproject.toml`, cobrindo apenas os pacotes
  alcançáveis pelo grafo de import da aplicação em tempo de requisição.
- O Root Directory do projeto no Vercel deve ser a raiz do repositório (não
  `frontend-react`), pois o build requer `api/`, `app/` e
  `requirements.txt` em conjunto.

### Dimensionamento das dependências da função serverless

O Vercel impõe um limite de 500 MB para o pacote de cada função. A stack de
analytics — `numpy`, `pandas` e `scikit-learn`, usados por
`app/services/analytics.py` para clusterização e detecção de anomalias —
leva uma instalação completa a mais de 620 MB. Como a API em execução nunca
importa esse módulo (ele é alcançado apenas pelos scripts offline de
importação e analytics), as dependências do projeto foram divididas em dois
conjuntos:

- a instalação base (`pip install .`, espelhada pelo `requirements.txt`)
  cobre apenas a API: `fastapi`, `sqlalchemy`, `pymysql`, `cryptography`,
  `pydantic-settings` e `rdflib`;
- o extra `full` (`pip install ".[full]"`) adiciona as ferramentas de
  analytics e importação usadas localmente e no Docker.

Essa divisão é suficiente para a demonstração do MVP: o painel, o detalhe do
paciente, o relatório em PDF localizado e o registro manual de glicemia
funcionam normalmente. Uma entrada manual registra o dia afetado em
`analysis_outbox`/`daily_metrics_current` por meio de
`app/services/analysis_queue.py` (SQL puro, sem dependência de ML),
sinalizando-o para reanálise em vez de recalcular os indicadores na hora.

Como trabalho futuro, caso a plataforma evolua para recalcular a camada
analítica em produção — por exemplo, após entradas manuais ou de forma
agendada —, o pipeline de analytics deve ser executado como uma implantação
separada (um worker agendado ou container executando `compute_analytics`
contra o mesmo banco), em vez de retornar à função da API, o que excederia o
limite de tamanho da plataforma.

### Configuração

A implantação requer uma única variável de ambiente:

- `MYGLICO_DATABASE_URL`: string de conexão da instância gerenciada de
  MySQL, por exemplo `mysql+pymysql://usuario:senha@host:3306/nome_do_banco`.
  Provedores como o Aiven documentam a string de conexão com um parâmetro
  `ssl-mode=REQUIRED`; como o PyMySQL não o aceita como argumento de
  conexão, `app/db/session.py` o traduz para a opção `ssl` equivalente,
  permitindo usar a string do provedor sem alterações.

### Preparação do banco de dados

As migrations e a importação do dataset são etapas pontuais de carga de
dados, executadas de uma máquina local contra o banco na nuvem, e não a
partir da função serverless:

```bash
MYGLICO_DATABASE_URL="mysql+pymysql://usuario:senha@host:3306/nome_do_banco" alembic upgrade head
MYGLICO_DATABASE_URL="mysql+pymysql://usuario:senha@host:3306/nome_do_banco" python scripts/import_uci_diabetes.py
```

### Limitações conhecidas

- O filesystem da função é somente leitura, exceto `/tmp`, que é limpo entre
  cold starts. Todas as rotas da API operam exclusivamente sobre o banco de
  dados, portanto o uso normal não é afetado; os endpoints SPARQL
  `/api/semantic/*` e arquivos em `/artifacts/*` não versionados no
  repositório, porém, não têm dados a ler nesse ambiente. Como o frontend
  não referencia nenhum dos dois, a aplicação visível ao usuário não é
  impactada.
- `rdflib` (exigido pelas rotas semânticas/SPARQL) é a maior dependência
  restante, de modo que os cold starts são mais lentos que no setup local
  com Docker/uvicorn. Novas dependências devem ser adicionadas ao
  `requirements.txt` apenas quando alcançáveis pelo grafo de import do
  `app.main` em tempo de requisição.

## Citação

Se você usar este repositório, cite-o usando o arquivo
[`CITATION.cff`](CITATION.cff) — o GitHub renderiza um botão
**"Cite this repository"** a partir dele. Um DOI (Zenodo) será adicionado
assim que um release for arquivado.

## Licença

Apache License 2.0 — veja [`LICENSE`](LICENSE). O dataset UCI Diabetes usado
como base possui seus próprios termos de uso; confirme a citação e a licença
oficiais em `archive.ics.uci.edu`.
