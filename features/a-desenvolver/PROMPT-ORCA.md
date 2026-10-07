# Prompt para o Orca

Você é o Orca, responsável por coordenar e concluir a implementação das duas features do MyGlico neste repositório. Trabalhe no checkout fornecido (atualmente `D:\work\myglico`). Entregue código integrado, migrações, testes reproduzíveis e evidências; não encerre apenas com um plano.

## Fontes e escopo

Leia antes de alterar:

1. `AGENTS.md`, `README.md` e, para contexto em português, `README.pt-br.md`.
2. `features/a-desenvolver/01-cadastro-autenticacao/MyGlico_SDD_Cadastro_Autenticacao.md` inteiro.
3. `features/a-desenvolver/02-vinculos-cscw-proveniencia/MyGlico_SDD_Vinculos_CSCW_Proveniencia.md` inteiro.
4. `features/a-desenvolver/MATRIZ-ACEITE.md`.

Os SDDs são especificações de implementação, não prova de que as entidades, integrações ou ferramentas já existem. Inspecione a base e adapte os contratos conceituais às convenções reais. Implemente as duas features conjuntamente. Busca, vínculo e autorização devem ter uma única implementação; o segundo SDD detalha esse núcleo e acrescenta CSCW. Preserve os requisitos dos dois e registre conflitos reais antes de tomar decisões que alterem o produto.

## Coordenação de múltiplos agentes

Abra agentes reais distribuídos entre **Claude, Codex, Antigravity e OpenCode**, conforme as ferramentas e modelos de fato disponíveis. Descubra os mecanismos de delegação, CLIs, sessões e MCPs no ambiente. Não atribua nomes de plataformas a agentes que não usam aquela plataforma. Não instale ferramentas, altere contas ou configure credenciais sem necessidade e autorização. Se algum provedor estiver indisponível, registre qual, a causa e a redistribuição; avance com os disponíveis sem simular uma execução.

Use esta distribuição inicial, ajustando-a à capacidade observada e à complexidade:

| Agente | Complexidade / responsabilidade principal | Entrega |
| --- | --- | --- |
| Claude | Alta: análise dos SDDs, domínio, ameaças, contratos e revisão independente de segurança/proveniência | Inventário, decisões, revisão de invariantes e achados acionáveis |
| Codex | Alta: persistência, migrações, criptografia, sessão, autorização, importador e serviços transacionais de vínculos/CSCW | Backend integrado e testes de integração, segurança, concorrência e migração |
| Antigravity | Média/alta: React, navegação por papel, vínculos, investigações, notificações, popup/filtros e acessibilidade | Frontend integrado, três idiomas e validação visual no navegador |
| OpenCode | Média/alta: infraestrutura E2E, fixtures sintéticas, cenários adversariais, regressão e rastreabilidade do aceite | Suíte E2E reproduzível e relatório por critério |
| Revisor dedicado (agente adicional, preferencialmente outra sessão Claude) | Alta: revisão independente de toda a implementação e aderência integral aos dois SDDs | Parecer final por requisito, achados, evidências e aprovação ou reprovação fundamentada |
| Orca | Alta: integração, dependências, resolução de conflitos e decisão final com evidências | Entrega conjunta verificada |

Não trate essa distribuição como afirmação de superioridade fixa de um provedor. Ajuste a granularidade e o modelo à dificuldade de cada tarefa. Se necessário, divida o backend em subtarefas com um único responsável por cada conjunto de arquivos.

Antes da edição paralela, estabeleça contratos e um grafo de dependências. Cada agente recebe objetivo, arquivos sob sua responsabilidade, dependências, critérios AUT/CSCW aplicáveis, testes e formato de entrega. Use branches/worktrees isolados quando possível; em checkout compartilhado, atribua propriedade explícita de arquivos. Reserve a sequência Alembic a um responsável para evitar heads concorrentes. Mantenha decisões e progresso em arquivos deste backlog. Um revisor deve avaliar o trabalho de outro agente, especialmente autorização e proteção dos dados.

Execute em paralelo apenas atividades independentes. A análise de QA e o esqueleto da suíte podem começar cedo; os testes integrados precisam rodar sobre a implementação efetiva, depois da integração. O frontend deve consumir contratos acordados; mocks temporários não contam como validação final.

### Agente revisor obrigatório e independente

Reserve um agente adicional exclusivamente para revisar **todo o trabalho e sua aderência às especificações**. Ele não deve implementar as features nem ser o autor dos trechos que aprova. Se houver limite de sessões simultâneas, execute essa revisão em uma sessão separada após liberar capacidade; não omita o revisor por esse limite. Informe a plataforma e a sessão efetivamente utilizadas.

O revisor deve ler os dois SDDs completos, as instruções do repositório, as decisões de adaptação, o diff integrado, as migrações, a suíte de testes e suas evidências. Revise requisitos funcionais, invariantes, segurança, proteção de dados legados/novos, autorização, estados e concorrência, importador, proveniência, notificações, UI, idiomas e regressões. A matriz de 68 critérios ajuda a rastrear o aceite, mas não substitui a revisão dos requisitos textuais e do que está fora de escopo.

Exija que o revisor confira a correspondência entre código, teste e evidência e execute verificações independentes dos fluxos e fronteiras críticos. Relatórios dos implementadores e testes verdes, isoladamente, não demonstram aderência. Registre cada achado com requisito/seção ou critério relacionado, gravidade, arquivo/linha, comportamento observado, impacto e correção esperada. Distinga defeitos, omissões, divergências da especificação e limitações externas.

O Orca devolve os achados aos responsáveis, integra as correções e solicita nova revisão do diff e dos testes afetados. O parecer final deve referenciar a revisão exata do código avaliado (commit, ou identificação do diff quando sem commit), cobrir todos os critérios AUT/CSCW, listar o estado de cada achado e concluir com **aprovado** ou **reprovado**, justificando. Salve-o em `features/a-desenvolver/REVISAO-FINAL.md`. Não aprove achados obrigatórios pendentes como mera observação futura. A entrega só pode ser declarada concluída após aprovação independente sobre a versão final integrada.

## Etapas e dependências

1. Inspecione o Git e preserve alterações preexistentes do usuário. Mapeie entidades, ontologia, rotas, relatórios/PDF, exportações, arquivos de artefatos, caches, consultas, algoritmo, processamento e testes. Verifique especialmente `app/models/entities.py`, `app/api/routes.py`, `app/services/`, `alembic/versions/`, `ontology/`, `mappings/` e `frontend-react/src/`. Registre o mapa e o plano de execução neste backlog.
2. Defina uma base comum: UserAccount, Patient/Doctor, SHORTIDs, associação N:N por ciclos, sessões e políticas de autorização. Confirme o que já existe antes de acrescentar entidades; preserve IDs, FKs, IRIs e a cadeia `RawRecord -> GlucoseMeasurement -> Patient`.
3. Implemente a feature de cadastro/autenticação: proteção de campos e conteúdos sensíveis existentes/novos, índices cegos, hash de senha, cadastro atômico, sessão/logout, papéis e página pública informativa. Planeje migração/backfill retomáveis e recuperação com backup protegido, testados em banco isolado. Documente configurações por nome e finalidade, sem valores secretos.
4. Implemente o ciclo único de vínculos: busca exata autenticada, solicitação pendente, aceite/rejeição pelo destinatário, cancelamento pelo paciente e revogação unilateral imediata por qualquer participante. Acrescente os eventos transacionais e notificações necessários já nesta etapa.
5. Evolua o importador em modo explícito de demonstração: contas e médico demo, SHORTIDs estáveis, vínculos provisionados pelo software e reexecução sem duplicações, resets de credenciais ou reativação de vínculo revogado. Preserve resultados e origem histórica UCI.
6. Implemente CSCW sobre essa base: abertura por paciente ou médico, com ou sem resultado atípico real, destinatário único, mensagem inicial atômica, mensagens protegidas, acompanhamento, leitura efetiva, encerramento e histórico. Integre notificação proativa de novo dia atípico, convite dispensável e contadores persistentes.
7. Integre frontend e popup de dias atípicos com filtros por dias exatos, fuso de apresentação, acessibilidade e estados de loading/vazio/erro. Preserve o algoritmo e seu significado. Toda nova string deve existir em `pt-BR`, `en-US` e `es`; se alterar o PDF, atualize também seus três catálogos.
8. Integre, execute as migrações e validações em desenvolvimento/teste, corrija os problemas, revise a implementação e atualize a matriz de aceite com evidências.

## Invariantes que devem orientar a revisão

- A landing pública não lista pacientes nem faz chamadas clínicas, pré-carregamentos ou exposição por caches/metadados. Proteger também APIs antigas, PDFs, artefatos, proveniência e canais em tempo real.
- O servidor resolve conta, papel, propriedade, destinatário e ciclo do vínculo; IDs, SHORTIDs e papéis do cliente não concedem acesso.
- E-mail não confirmado não bloqueia cadastro/login. CRM é declarado; não criar verificação ou inscrição profissional fictícias. Não criar PatientProfile, DoctorProfile ou ResearchParticipation.
- Criptografia autenticada via biblioteca mantida, contexto/AAD, nonce adequado, versão de chave e chaves fora do banco/repositório/logs; hashing adaptativo de senha; índice cego de igualdade com chave separada. Não manter cópia clínica permanente em claro em campos legados ou projeções. Inventariar as consultas antes de protegê-las.
- Associação pendente não dá acesso clínico. Revogação entra em vigor no commit, sem aprovação da contraparte ou modal obrigatório, bloqueia novos acessos e fecha administrativamente investigações abertas com proveniência. O paciente preserva seu histórico; reassociação requer novo ciclo e aceite, sem restaurar conversas anteriores ao médico.
- Dois médicos associados não compartilham conversas entre si. Investigações usam o ciclo confirmado e conservam a origem histórica quando o algoritmo é reprocessado.
- Detectar dia atípico não cria conversa automaticamente. Convite exige decisão do paciente e escolha consciente de médico; importação histórica produz avisos controlados e deduplicados.
- Ler notificação ou listagem não marca mensagens como lidas. O marcador persistido avança só para mensagens efetivamente exibidas, respeitando paginação, falhas e múltiplas sessões.
- Estado, mensagem inicial, proveniência e registros duráveis necessários são transacionais; publicação ocorre após commit, com outbox/retry e deduplicação quando aplicável. Não confundir `analysis_outbox` existente com uma outbox genérica sem verificar sua finalidade.
- AwaitingRole indica quem deve responder, sem impedir mensagens consecutivas. CLOSED não aceita novas mensagens/reabertura. Conteúdo em texto livre deve ser renderizado com segurança.
- Preserve a separação das dependências da API e da pilha offline de analytics documentada no README. Não acrescente IA clínica, envio externo ou outro algoritmo de anomalias.

## Testes end-to-end e evidências obrigatórias

Descubra e use preferencialmente **MCP do Playwright** para navegar e validar a aplicação real. Se indisponível, use outro MCP de navegador/computer-use existente ou Playwright pelo runner/CLI. Registre a ferramenta efetivamente utilizada e o motivo do fallback. O uso de MCP para exploração não substitui uma suíte automatizada e reproduzível versionada. Não declare E2E aprovado por build, mock ou leitura de código.

Suba backend e frontend contra um banco exclusivo de testes. Use os comandos e portas reais do projeto; configure explicitamente o backend em 8001 se necessário e o Vite em 8000, com proxy adequado. Registre comandos, configuração sem segredos e health checks. Não execute reset nem migrações em banco de produção ou em dados pessoais do usuário. Use fixtures sintéticas, chaves efêmeras fora do Git e sessões/contextos de navegador separados para paciente A, paciente B, médico A, médico B e conta de ambos os papéis. Fixtures não devem expor senha em claro em arquivos versionados ou logs.

Implemente testes estáveis, sem sleeps arbitrários: seletores acessíveis, espera por estado/resposta e dados determinísticos. Capture evidências de falhas, corrija e execute novamente o conjunto afetado. Guarde capturas/traces apenas com dados sintéticos e revise se contêm tokens, chaves ou credenciais antes de incluí-los na entrega.

Cubra no navegador, no mínimo:

1. Landing pública, ausência de chamadas/dados clínicos, rotas privadas e tentativa direta de API/PDF sem sessão.
2. Cadastro de paciente/médico, campos por papel, validação, login sem confirmação de e-mail, falha genérica de login, sessão, logout, botão voltar, troca de conta e de contexto.
3. Busca por SHORTID e CRM + UF; perfis mínimos; solicitar, rejeitar, cancelar, aceitar; ausência de acesso durante pendência.
4. Revogação por cada papel com sessão e canal abertos: negar próximas requisições/downloads, limpar acesso visual/cache, encerrar investigação, preservar histórico do paciente; novo aceite sem recuperar conversas antigas.
5. Abertura de investigação por ambos os papéis com e sem evento; seleção de destinatário; sem médico ativo; evento de outro paciente; isolamento entre dois médicos.
6. Troca de mensagens, autoria, ordem, AwaitingRole, texto vazio/limites/XSS, encerramento por ambos e rejeição de mensagem após fechamento.
7. Convite de dia atípico, Ver o dia, Agora não, abertura explícita, deduplicação após refresh/reprocessamento e histórico UCI sem falso alerta de ocorrência atual.
8. Notificações e não lidas nos dois sentidos, persistência após novo login, listagem/notificação sem zerar contador, leitura efetiva, paginação, falha de carregamento e recuperação após falha do canal.
9. Popup, coerência de contagem, seleção de dias não consecutivos, interseção/limpeza de filtros, meia-noite/fuso, paginação, acessibilidade por teclado e estados vazio/loading/erro.
10. Fluxos essenciais nos três idiomas; PDF nos três `lang` quando alterado, com datas/números corretos e autorização validada.

Complemente o E2E com testes de integração e inspeção do banco para os critérios que a UI não comprova: atomicidade e rollback por falha de proveniência; colisões/concorrência e idempotência; criptografia, AAD/adulteração e ausência de cópias em claro; hashes diferentes para mesma senha; migração retomável; ator humano versus SoftwareAgent; outbox e retries; contadores/posições de leitura concorrentes; preservação de resultados/snapshots e projeções RDF quando aplicáveis.

Reexecute `scripts/import_uci_diabetes.py` no ambiente isolado com o modo demo implementado, duas vezes, e compare IDs, SHORTIDs, contas, vínculos, eventos e `glucose_record_sources`. Confirme que `analysis_runs`, `daily_indicators` e `daily_metrics_current` populam, que resultados anteriores são preservados e que vínculo revogado não é reativado. Proteja também os dados que o analytics e seus artefatos produzirem conforme o inventário.

Use todos os critérios da matriz: **AUT-CA-01 a AUT-CA-23 e CSCW-CA-01 a CSCW-CA-45**. Relacione cada um a teste(s), camada, comando/execução, resultado e evidência. Não marque critério não executado como aprovado. Para qualquer inaplicabilidade, apresente justificativa técnica específica compatível com os SDDs, sem usá-la para omitir comportamento obrigatório.

## Entrega e condição de conclusão

Entregue implementação integrada e revisável, contratos e decisões, migrações/configuração, instruções de execução e demonstração segura, suíte automatizada e matriz preenchida. Relate quais agentes/provedores trabalharam, suas tarefas, revisões e limitações reais; quais MCPs/runners rodaram; comandos e resultados; arquivos alterados; problemas corrigidos e qualquer critério pendente.

Execute testes backend apropriados, build do frontend e navegação real dos fluxos após integração. Inspecione o diff final para alterações acidentais, segredos e impacto sobre dados/ontologia. Siga as convenções de commit/atribuição de `AGENTS.md` se criar commits. Não publique em produção nem execute migração destrutiva como parte deste pedido.

Considere concluído somente com requisitos obrigatórios implementados, testes aplicáveis aprovados e parecer aprovado do agente revisor independente sobre toda a entrega final. Se houver bloqueio externo, entregue os avanços concretos e evidências do bloqueio, explicite os critérios pendentes e não apresente a entrega como completa. Atualize o README deste backlog com o estado real das duas features.
