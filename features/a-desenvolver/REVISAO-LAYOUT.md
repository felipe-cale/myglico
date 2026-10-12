# Revisão de layout das telas novas (features 01 + 02)

- **Data:** 2026-10-11.
- **Revisor:** coordenador (Claude).
- **Ambiente:** Docker MySQL (`myglico-test`), dados UCI demo.
- **Evidência:** 22 capturas Playwright (desktop 1440×900 e mobile 390×844) das telas pública, paciente e médico, mais inspeção do código de `frontend-react/src`.

**Referência do padrão:** o sistema visual original de `main` (`0920365`):
- **tokens:** `--react-blue`, `--react-green`, `--react-text`, `--react-border`, raio de 20–28 px, fundo com gradientes suaves;
- **estrutura:** `react-panel` com `react-panel__header`, `react-eyebrow` + `h2` e `react-hero`;
- **ações:** `react-button` (pílula com gradiente azul→verde) e `react-button--ghost`;
- **campos:** `react-select-field`, `react-search` e `react-filter-form` (altura 3 rem, raio 20 px);
- **apoio:** `react-badge`/`react-chip`, `react-state` (vazio/carregando/erro), `react-dialog` e `react-nav__link` (pílula, ativa com gradiente).

## 1. Arquitetura de informação (mais grave)

| # | Tela | Problema | Proposta |
|---|---|---|---|
| A1 | Visão geral, **paciente** | Continua a visão de pesquisa do MVP: "Pacientes acompanhados = 1", "Encontre um paciente em segundos", filtro por perfil, busca e paginação para **um único** paciente, e "Abrir painel do paciente" apontando para si mesmo. Não faz sentido para quem está logado como paciente. | Uma home própria do paciente: hero de boas-vindas com o nome, convite de dias atípicos, resumo do próprio período (métricas pessoais), "Meus médicos", "Meus questionamentos" e um atalho para o painel completo. Sem lista nem busca de pacientes. |
| A2 | Visão geral, **médico** | Mostra os **70 vínculos numa lista crua**, sem busca nem paginação, com "Revogar associação" em todas as linhas. A lista original de pacientes (cards, busca, filtro de perfil, paginação), que é a tela natural do médico, **não aparece** para ele, porque `GET /api/patients` exige papel de paciente. | Restaurar para o médico a lista original de pacientes, limitada aos vínculos ACTIVE (exige ajuste no backend e testes). Por cima dela: questionamentos e solicitações pendentes. A revogação sai da lista e vai para o detalhe do paciente, como ação secundária. |
| A3 | Visão geral, paciente | Ordem: o formulário de busca de médico aparece antes de qualquer conteúdo do paciente. | O conteúdo do paciente vem primeiro. "Adicionar médico" fica como ação dentro do painel "Meus médicos". |
| A4 | Detalhe do paciente, visto pelo paciente | "Voltar para a visão geral" leva à visão de pesquisa (A1). O cabeçalho mostra o código interno do dataset (`data-01`) e um texto técnico ("core clínico"). | Depende de A1. Esconder o código do dataset para o paciente e usar um texto voltado a ele. |

## 2. Fora do padrão visual

| # | Onde | Problema | Correção |
|---|---|---|---|
| B1 | Login, cadastro, busca de médico, conversa, popup de dias atípicos | `<input>` e `<textarea>` com o visual padrão do navegador (borda cinza de 1 px, sem raio, altura baixa). | Campos no padrão `react-select-field`/`react-filter-form`, com uma classe de campo única reutilizável. |
| B2 | Landing "Entrar", login, cadastro, "Buscar" e "Enviar" | Botões com estilo inline em azul chapado `#005fcc` e cantos quadrados. | `react-button`. |
| B3 | "Revogar associação" | Botão padrão do navegador. | `react-button--ghost` em tom de alerta, com confirmação. |
| B4 | Landing "Criar conta" | Gradiente com texto azul: **ilegível** (falha de contraste). | `react-button--ghost` (ou primário), com contraste AA. |
| B5 | Conversa "Encerrar" | Ação terminal com o mesmo destaque da ação primária. | Botão secundário/ghost com confirmação. "Enviar" fica como o primário. |
| B6 | Login, cadastro, Meus médicos, Questionamentos, conversa | Sem `react-panel`: conteúdo solto sobre o fundo; "Meus médicos" numa caixa cinza chapada. | `react-panel` com cabeçalho `react-eyebrow` + `h2` + descrição, igual às telas originais. |
| B7 | Conversa | Metadados (paciente, status, origem) em parágrafos soltos com espaçamento grande; "Voltar" como texto simples. | Cabeçalho em painel, com status, aguardando e origem como chips (`react-badge`), e "Voltar" como `react-button--ghost`. |
| B8 | Notificações | Dropdown quadrado e sem sombra; sino em emoji. | Painel flutuante no padrão (raio, sombra, `react-state` para vazio) e ícone consistente. |
| B9 | Topo, autenticado | "Questionamentos" e "Sair" fora do padrão `react-nav__link`, com destaques inconsistentes entre itens. | Todos os itens como `react-nav__link`, com contadores como `react-badge`. |
| B10 | Componentes novos | Cerca de 53 blocos `style={{…}}` inline, que ignoram tokens e responsividade. | Mover para classes em `styles.css` usando os tokens. |
| B11 | Estados vazios | "Nenhum questionamento encontrado." e "Nenhum vínculo encontrado." como texto simples. | `StateBlock` (`react-state`), como nas telas originais. |

## 3. Responsividade

| # | Onde | Problema |
|---|---|---|
| C1 | Conversa no mobile | Estoura a largura: "Encerrar" e "Voltar" ficam cortados e aparece rolagem horizontal. |
| C2 | Busca de médico no mobile | Campos crus empilhados com o "ou" desalinhado. |

## 4. Conteúdo e comportamento observados

| # | Onde | Problema |
|---|---|---|
| D1 | Detalhe | Pluralização errada: "1 medições". |
| D2 | Detalhe, depois de um registro manual | A janela padrão "30 dias a partir da data mais recente" passa a ser a data de hoje. O histórico UCI (1990) some, os gráficos ficam vazios e a "Média glicêmica" aparece como "-", embora exista uma leitura de 110 mg/dL no período: o indicador do dia não foi recalculado para o registro manual. **Comportamento a investigar, além de layout.** |
| D3 | Landing | Texto voltado a clínico/pesquisa ("Visualize rapidamente quem está em acompanhamento"), não à pessoa que vai se cadastrar. |

Todas as strings novas ou alteradas precisam existir em `pt-BR`, `en-US` e `es`.

## Implementação e validação

- **Concluído em 2026-10-12:** home própria para paciente e médico; lista do médico limitada aos vínculos ativos; busca de médico dentro do painel do paciente; revogação com confirmação; e telas de login, cadastro, conversa, notificações e popup alinhadas ao sistema visual.
- O detalhe mostra o período disponível, oferece atalho para o histórico completo e identifica dias que aguardam análise, sem classificá-los como estáveis.
- A navegação, mensagens, estados vazios e formulários foram traduzidos nos três idiomas. A conversa e a busca de médico foram conferidas em viewport móvel de 390×844, sem rolagem horizontal.
- **Validação:** `python -m pytest tests -q -rXx` em SQLite — 79 passaram; `npm run test:e2e` — 81 passaram e 1 foi ignorado (CSCW-CA-29, conforme registrado na suíte). Os testes E2E incluem os dois cenários responsivos.
- A migração aditiva `20261011_0012` foi aplicada no MySQL de teste para declarar `DATETIME(6)` e manter a precisão dos eventos.
