# Instruções para implementar o Glico com vários agentes

Este arquivo pode ser entregue ao Orca como prompt inicial, junto com a SDD e a matriz. A execução é por fase; planejamento de F2 não autoriza implementá-la durante F1.

## Pedido ao Orca

Implemente a **fase 1 do assistente Glico** no MyGlico conforme `MyGlico_SDD_Assistente_Glico.md` versão 1.0, nesta pasta, usando vários agentes com coordenação explícita. Comece pela fundação segura e pelo suporte a **foto individual com PaddleOCR**. Inclua os incrementos de texto, consultas, FAQ, áudio com faster-whisper e colaboração até concluir a fase 1. A **fase 2 está especificada, mas sua implementação aguarda liberação explícita**: XLSX/CSV, templates, foto de várias leituras e gravação em lote não entram na primeira entrega.

O público inicial é UCI/dados fictícios/testers internos. Não usar dados reais em fixtures, relatos ou evidências. O nível de integridade e isolamento descrito na SDD é obrigatório desde o começo. Não substituir testes de segurança por avisos no chat.

Antes de editar, leia `AGENTS.md`, `README.md`, `README.pt-br.md`, `PRODUCT.md`, `DESIGN.md`, os SDDs 01/02 e a implementação real da autenticação, vínculos, investigações, glicemias, proveniência e PDF. Confirme branch/commit, estado sujo, trabalho de outros agentes e banco alvo. Preserve alterações preexistentes. Não resetar, excluir outputs ou alterar um worktree pertencente a outra execução.

## 1. Responsabilidade do coordenador

- Criar um backlog de F1.0 a F1.4, mapa de requisitos e ownership de arquivos antes de disparar implementações concorrentes.
- Fazer uma rodada de contratos: API, schema, enums, máquina de estados, auth/contexto, capabilidade interna, receipt, limites, retenção e erros. Registrar em `CONTRATOS-API.md` e `DECISOES-ARQUITETURA.md` dentro desta pasta.
- Registrar decisões sobre transporte interno autenticado e atomicidade; nenhum agente pode usar um commit clínico separado do receipt.
- Distribuir módulos/testes em frentes sem conflito. Integrar arquivos compartilhados por responsável único por rodada.
- Reutilizar a suíte e a infraestrutura existentes, mantendo bancos descartáveis com foreign keys. Coordenar testes de MySQL 8 além de SQLite.
- Resolver incompatibilidades entre frentes atualizando contrato e consumidores juntos. Não aceitar "o frontend já valida" como controle de backend.
- Manter capability paga desabilitada até configuração de fornecedor/retention/orçamento. Não inventar API key ou garantir benefício de AI Pro.
- Atualizar a matriz somente com resultados executados, sem sobrescrever matrizes/evidências das features 01/02.
- Encerrar uma fase apenas após integração, evidências e revisão independente da entrega inteira.

## 2. Frentes propostas

As frentes são papéis de trabalho, não exigência de manter todas simultaneamente. Adaptar quantidade aos slots disponíveis. Cada agente recebe escopo, arquivos exclusivos, requisitos e critérios de aceite da sua frente.

| Frente | Responsabilidade | Entrega | Dependências |
| --- | --- | --- | --- |
| BACKEND-CORE | Gateway, contexto, schemas, propostas, capabilidade, executor, receipt e integração com endpoints | Fluxo tipado e transacional com testes de concorrência | Contratos congelados |
| SECURITY-PLATFORM | CSRF, limites compartilhados, quotas/reservas, worker auth/replay, logging/descarte, feature flags/runbook | Controles que falham fechado, testes adversariais | Contratos de gateway/worker |
| MEDIA-OCR | PaddleOCR, preprocessing em memória, extração individual, limites de imagem e corpus sintético | Adaptador real + relatório de qualidade | Contrato ReadingExtractor |
| MEDIA-ASR | faster-whisper, modelo multilíngue, decode em memória, silêncio/duração e corpus pt/en/es | Adaptador real + relatório de qualidade | Contrato SpeechProvider |
| PRODUCT-HELP | FAQ versionada por papel/locale, intenções/regras locais, schemas de respostas e navegação | Ajuda sem fornecedor e entradas limitadas | Registro de operações/capacidades |
| FRONTEND | Chat paciente/médico, mídia, cartões, contexto, revisão, erros, accessibility e locales | UI em navegador mobile/desktop | API/erros/capacidades estáveis |
| VALIDATION | HTTP/E2E/DB/fault injection, instrumentação de egress/descarte e regressões | Matriz preenchida e evidências | Pode preparar testes após contrato; executar na integração |
| INDEPENDENT-REVIEW | Confrontar todos os requisitos/caminhos com código final e evidências | Parecer independente e lista de achados | Integração estabilizada; não ser autor principal das frentes |

SECURITY-PLATFORM pode desenhar políticas/testes e enviar patches para integração pelo BACKEND-CORE quando afetar arquivos comuns. MEDIA-OCR e MEDIA-ASR podem compartilhar estrutura do serviço, mas só um responsável altera entrypoint/config/manifests por rodada.

## 3. Arquivos compartilhados e ownership

Antes de começar, atribuir explicitamente um dono por arquivo/rodada:

- `app/api/routes.py` e novas rotas Glico: BACKEND-CORE/coordenador.
- `app/models/entities.py`, migrations e serviços transacionais existentes: BACKEND-CORE/coordenador.
- Config, `requirements.txt`, `pyproject.toml`, manifests/containers e `vercel.json`: coordenador, mediante propostas das frentes.
- Serviço de mídia: MEDIA-OCR na fundação; MEDIA-ASR entrega adaptador/testes separados, com merge coordenado.
- `frontend-react/src/api.js`, `OverviewPage.jsx`, estilos e catálogos `pt-BR`, `en-US`, `es`: FRONTEND.
- Testes independentes e ferramentas de instrumentação: VALIDATION em arquivos novos; autores mantêm testes unitários dos seus módulos.
- Matriz/evidências/contratos: coordenador integra, evitando alterações concorrentes de status.

Preferir módulos novos para Glico/worker em vez de expandir indiscriminadamente o monólito de rotas. Não criar duplicatas de autorização ou implementar nova criptografia customizada. Não adicionar scripts gerados pelo modelo a runtime do agente.

Se usar worktrees, cada um mantém seu banco/portas/secrets efêmeros e integra por commits claros. Não fazer checkout forçado em worktree de outro agente. Em checkout compartilhado, não criar commits globais com alterações de outros agentes nem disputar o mesmo arquivo. Registrar origem dos patches e convenções de commit do repositório.

## 4. Ordem de integração

### Rodada A Contratos e fundação

1. Inspecionar a baseline e confirmar os riscos listados na seção 2 da SDD.
2. Congelar contracts e plano de migrações; preparar testes de negação, CSRF, propriedade, confirmação e receipt.
3. Implementar F1.0. Testes devem provar zero escrita antes de confirmação e atomicidade mesmo com falhas.
4. Não lançar OCR/ASR que apenas chama endpoint com credencial administrativa ou conserva arquivos temporários.

### Rodada B PaddleOCR e revisão individual

1. Implementar adaptador e serviço real com modelos provisionados, processamento em memória, auth/replay e limites.
2. Integrar cartão de revisão do paciente e confirmação pelo endpoint autenticado.
3. Validar mídia real e critérios GLI-CA-031 a 043 relevantes. Saída fake não é demonstração de PaddleOCR.
4. Fotos com várias leituras recebem orientação; não importar lote escondido na interface individual.

### Rodada C Texto ajuda áudio e consultas

1. Integrar FAQ e regras locais, queries autorizadas, PDF e seleção médica.
2. Integrar faster-whisper no serviço de mídia, idiomas pt/en/es e comandos tipados.
3. Validar que troca de paciente/revogação durante inferência descarta resultado e não mistura históricos.
4. Corrigir freshness de dias atípicos nos caminhos atuais e Glico, preservando investigação histórica.

### Rodada D Colaboração e aceite de F1

1. Integrar abertura/mensagem de investigação com proposta revisada e confirmação.
2. Executar toda a matriz F1, suite existente e testes reais dos modelos, além de MySQL 8.
3. Registrar evidências sintéticas e relatório de modelos/recursos. Abrir achados com severidade, causa, prova e correção.
4. Revisor independente avalia o código integrado, inclusive endpoints antigos alterados e configurações de deploy.
5. Corrigir bloqueadores e reexecutar os checks afetados. Entregar F1 com status real; não passar para F2 automaticamente.

## 5. Regras de segurança inegociáveis

- Cada recurso tem owner e autorização atual; paciente próprio e médico ACTIVE no ciclo correto.
- IDs/modelo/payload não substituem sessão, papel ou consentimento. Cookie/chaves nunca entram em prompt/worker/log.
- Worker interpreta mídia sem banco clínico, sem ferramentas de mutação e sem egress arbitrário.
- Capabilidade interna curta é específica e verificada; header fabricado pelo browser não aprova nada.
- Confirmação apenas por ação humana explícita no endpoint próprio em F1/F2. Texto "sim" e saída ASR/OCR não executam.
- Efeito, source, event, receipt e estado EXECUTED são atômicos. Retry e concorrência não geram duplicatas.
- Não persistir anexo ou transcrição bruta. Verificar framework/spool, proxy, decoder, SDK, APM, logs, filas e backups.
- Inferência tem deadline/cancelamento real e cotas compartilhadas. Não deixar job consumindo CPU após request terminar.
- Sem transferência automática para Gemini/novo fornecedor em falha local. Sem ativação de serviço pago sem política e orçamento.
- Histórico/resultado do médico não fica acessível depois de revogação; reassociação não restaura ciclo antigo.
- Modelos/dependências provisionados com versão/digest/licença, sem downloads arbitrários e com runtime isolado.
- Todos os textos fixos/erros/instruções têm pt-BR, en-US e es; auth/schemas independem do locale.

## 6. Validação e evidências

Usar os comandos e harness existentes, adaptando-os às novas frentes. Instalar dependências apenas no ambiente apropriado e não inflar o runtime Vercel por default. Toda execução de banco usa alvo descartável; ler fixtures antes de configurar o ambiente.

Comandos base de referência:

```text
python -m pytest tests -q
cd frontend-react
npm run build
npx playwright test
```

Esses comandos sozinhos não provam MySQL, modelos reais, descarte, concorrência e qualidade mobile. Acrescentar cenários correspondentes e documentar o ambiente. Se houver mudança em importer/analytics/provenance, executar a importação e reimportação sobre banco descartável com dados de teste/UCI, validando indicadores/métricas e contagens.

Cada agente relata arquivos modificados, decisões, contratos afetados, testes executados, resultados, limitations e dependências pendentes. Não escrever "passou" quando houve apenas inspeção ou quando a suíte não chegou a rodar. Não publicar capturas com dados de testers reais nem segredos.

## 7. Entregáveis da fase 1

- Código/infraestrutura/documentação da fase 1 com feature flags e fallback manual.
- Contratos finais e decisões de arquitetura nesta pasta.
- `MATRIZ-ACEITE.md` com resultados reais GLI-CA-001 a GLI-CA-059; F2 permanece Não executado.
- Relatório de qualidade PaddleOCR e faster-whisper com modelos/hardware/corpus e métricas por campo/idioma.
- Evidências de SQLite/MySQL, E2E mobile/desktop/locale, adversarial, egress e ausência de persistência.
- Runbook de configuração, orçamento, worker, limpeza, observabilidade e rollback.
- Revisão independente final, achados resolvidos e limitações materiais declaradas.

Impedimento externo deve ser registrado com ação concreta para resolver; não reduzir requisito. Se faltar infraestrutura de MySQL/modelo para um check obrigatório, o status daquele critério continua Não executado ou Parcial e a fase não é declarada aprovada.

## 8. Fase 2 quando liberada

Após liberação explícita, implementar seções de lotes/templates da SDD, critérios GLI-CA-060 a 072 e regressão F1. Preservar os mesmos controles; processamento flexível não autoriza execução de fórmula/macro, upload persistente, mistura de pessoas ou confirmação de versão antiga. Gravação de lote é transacional e não N commits ao endpoint individual.
