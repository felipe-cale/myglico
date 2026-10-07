# MyGlico — SDD de vínculos, colaboração CSCW e proveniência

**Data:** 06/10/2026  
**Versão:** 1.1  
**Abordagem:** Specification-Driven Development (SDD).  
**Documento complementar:** MyGlico_SDD_Cadastro_Autenticacao.md.  
**Destino:** agente responsável pela implementação no repositório do MyGlico.  
**Estado:** especificação de comportamento e execução; não representa código já implementado ou repositório inspecionado.

## 1. Instruções ao agente e dependências

Implemente as funcionalidades deste documento sobre a arquitetura existente do MyGlico e os requisitos do primeiro SDD.

Antes de editar, leia as instruções do repositório e inspecione:

- Ontologia e entidades Patient, Doctor e UserAccount.
- Associação N:N paciente–médico.
- Autenticação, criptografia e índices de busca protegidos.
- Registro de proveniência, auditoria, ontologia operacional e eventual integração RDF/PROV-O.
- Identificação de dias atípicos, IDs dos resultados, versões do processamento e importador UCI.
- Card de dias atípicos e tela de detalhamento do paciente.
- Infraestrutura de notificações, comunicação em tempo real e testes.

Preserve nomes e relacionamentos da ontologia. As entidades e campos novos apresentados são conceituais; reutilize equivalentes existentes antes de criar outros. Não criar PatientProfile, DoctorProfile ou ResearchParticipation.

Este documento detalha busca e vínculos já previstos no primeiro SDD e acrescenta a funcionalidade CSCW. Não desenvolver duas implementações concorrentes desses recursos.

**Regras obrigatórias:**

1. O paciente solicita associação com um médico.
2. A associação comum só se torna ativa após confirmação do médico.
3. Paciente ou médico podem revogar a associação unilateralmente, sem confirmação ou aprovação da outra parte.
4. Mudanças de estado precisam gerar eventos de proveniência persistidos na base.
5. Paciente e médico podem abrir questionamentos/investigações com ou sem um evento de dia atípico.
6. O card de dias atípicos abre um popup que lista os dias e permite filtrar o detalhamento do paciente.
7. A página inicial continua pública e informativa, sem listar pacientes.
8. Ao identificar um novo dia atípico, o sistema notifica o paciente e pergunta se deseja abrir uma investigação com um médico associado, sem criar a conversa automaticamente.
9. Novas mensagens geram notificações internas e contadores persistentes de mensagens não lidas para o destinatário.

A confirmação do médico refere-se ao aceite do relacionamento, não à confirmação de e-mail. A confirmação de e-mail continua futura e não deve bloquear os fluxos atuais.

## 2. Objetivo e escopo

Apoiar a contextualização colaborativa das leituras de glicemia. Um dia atípico aponta um resultado do algoritmo; os participantes usam um questionamento para registrar explicações, solicitar esclarecimentos e concluir a interação.

A aplicação deve organizar a colaboração pelos 3Cs:

| Princípio | Comportamento implementado |
| --- | --- |
| Comunicação | Mensagens em texto livre, notificações internas e indicação de mensagens não lidas. |
| Coordenação | O sistema transforma a identificação de um dia atípico em um convite ao paciente para investigar; organiza escolha do médico, vínculo, estados, destinatário, pendências de resposta, notificações e encerramento. |
| Cooperação | Construção de um registro compartilhado de contexto, relacionado ou não a um dia atípico, com autoria e histórico rastreável. |

Não apresentar o algoritmo como diagnóstico e não prometer conclusão clínica automática.

### 2.1 Incluído

- Busca exata de médico por SHORTID ou CRM + UF.
- Solicitação, confirmação, rejeição e cancelamento de associação.
- Revogação por paciente ou médico, sem aceite da contraparte.
- Proveniência dos vínculos e das ações da investigação.
- Abertura de investigação por qualquer um dos dois papéis.
- Associação opcional a um evento de dia atípico.
- Mensagens, estado de acompanhamento, não lidas e encerramento por qualquer participante.
- Convite proativo ao paciente quando o algoritmo existente identificar um novo dia atípico.
- Notificações internas persistidas, inclusive para solicitações de vínculo, dias atípicos e novas mensagens.
- Indicadores visíveis e persistentes de mensagens não lidas no menu, listagem e conversa.
- Popup de dias atípicos, lista e aplicação de filtros no detalhamento.
- Autorização, concorrência, idempotência e testes dos fluxos.

### 2.2 Fora da primeira implementação

- Compartilhar automaticamente uma investigação com todos os médicos do paciente.
- Investigação com vários médicos simultaneamente.
- Trocar destinatário de uma investigação existente.
- Reabertura de investigação encerrada.
- Edição ou exclusão silenciosa de mensagens.
- Anexos, áudio, vídeo, chamadas ou prescrições.
- Notificações externas por e-mail, SMS ou WhatsApp.
- IA para responder ao paciente, diagnosticar, censurar conteúdo ou decidir encerramento.
- Novo algoritmo de dias atípicos.
- Publicação pública do grafo de proveniência ou dos dados clínicos.

A organização pelo sistema significa estados, permissões, notificações e rastreabilidade. Não acrescentar uma moderação clínica automatizada que não foi solicitada.

## 3. Invariantes do domínio

- UserAccount autentica; Patient e Doctor representam os papéis de domínio.
- O servidor determina o Patient/Doctor da sessão. IDs e papéis enviados pelo cliente não substituem essa resolução.
- O modelo permite vários médicos por paciente e vários pacientes por médico.
- Cada investigação possui exatamente um Patient e um Doctor destinatário.
- A investigação é vinculada a uma instância de associação confirmada, identificando o período de autorização.
- O evento de dia atípico é opcional; quando informado, pertence ao mesmo Patient.
- Uma associação pendente não concede acesso às leituras, dias atípicos ou investigações do paciente.
- Ser médico associado não concede acesso às conversas de outros médicos.
- Revogar a associação interrompe novos acessos e interações do médico, preservando o histórico.
- Encerrar uma investigação não revoga a associação.
- Reassociação exige uma nova confirmação do médico e não restaura automaticamente acesso ao histórico do vínculo anterior.
- Persistência do estado e proveniência das mutações são atômicas.
- Dados pessoais e conteúdos clínicos seguem a proteção definida no primeiro SDD.
- SHORTID localiza o perfil; não é credencial ou autorização.

## 4. Busca de médico pelo paciente

### 4.1 Interface

Na área autenticada do paciente, disponibilizar **Meus médicos** e **Buscar médico**.

Oferecer dois modos:

- SHORTID MyGlico: seis caracteres alfanuméricos, conforme a convenção do primeiro SDD.
- CRM + UF: ambos necessários; pesquisa exata pelo índice protegido.

Exibir carregamento, resultado vazio, erro recuperável e limite de tentativas. Não incluir listagem pública de todos os médicos ou autocomplete global.

### 4.2 Resultado

Exibir apenas:

- SHORTID.
- Nome profissional autorizado para esse perfil.
- CRM e UF quando existentes.
- Indicação de médico de demonstração.
- Estado do vínculo com o paciente atual: sem vínculo, pendente ou ativo.
- Ação apropriada: Solicitar associação, Solicitação enviada ou Ver vínculo.

Não expor e-mail, UserAccountId, lista de pacientes ou outras informações internas.

Campos criptografados só são recuperados pelo backend após autenticação e autorização. A busca por CRM + UF reutiliza o índice protegido do primeiro SDD; não consulta texto em claro ou descriptografa toda a tabela.

O médico de demonstração pode ter CRM/UF nulos e deve continuar localizável pelo SHORTID.

### 4.3 Solicitação

Ao selecionar Solicitar associação, o paciente visualiza o médico e o alcance previsto do vínculo. A ação explícita do paciente já representa sua confirmação para iniciar o processo.

O backend cria uma solicitação pendente e uma notificação interna ao Doctor escolhido. Antes do aceite, o médico vê apenas os dados mínimos necessários para identificar a solicitação, como SHORTID e nome de exibição do solicitante. Não mostrar leituras ou mensagens clínicas de outros vínculos.

Busca e solicitação devem usar autorização e controle de frequência. Uma busca não cria associação.

## 5. Ciclo de vida da associação

Usar a associação existente, acrescentando um ciclo ou instância histórica se necessário. Não sobrescrever o histórico de uma revogação para representar um novo aceite.

### 5.1 Estados

| Estado conceitual | Significado | Acesso clínico pelo médico |
| --- | --- | --- |
| PENDING | Paciente solicitou; médico ainda não decidiu. | Nenhum. |
| ACTIVE | Médico confirmou a solicitação. | Somente dentro das permissões do vínculo e do recurso. |
| REJECTED | Médico recusou a solicitação. | Nenhum. |
| CANCELLED | Paciente retirou a solicitação pendente. | Nenhum. |
| REVOKED | Paciente ou médico encerrou unilateralmente o vínculo ativo. | Nenhum acesso futuro pelo vínculo. |

### 5.2 Transições

| Origem | Ação | Quem executa | Destino | Evento de proveniência |
| --- | --- | --- | --- | --- |
| Sem ciclo aberto | Solicitar | Patient | PENDING | AssociationRequested |
| PENDING | Confirmar | Doctor destinatário | ACTIVE | AssociationConfirmed |
| PENDING | Rejeitar | Doctor destinatário | REJECTED | AssociationRejected |
| PENDING | Cancelar solicitação | Patient solicitante | CANCELLED | AssociationRequestCancelled |
| ACTIVE | Revogar | Patient ou Doctor participantes | REVOKED | AssociationRevoked |
| Estado terminal | Solicitar novamente | Patient | Novo ciclo PENDING | Novo AssociationRequested |

Não permitir aceite pelo paciente, por outro médico ou por uma conta externa. Não permitir associação ativa criada pelo frontend sem a decisão do médico.

### 5.3 Revogação unilateral

Disponibilizar **Desassociar / Revogar associação** para o paciente e o médico, com linguagem clara.

- Não exigir aceite, confirmação ou aprovação da outra parte.
- Não implementar modal obrigatório como condição do processo; a ação deve ter retorno imediato e claro.
- Motivo pode ser opcional e, se informado, recebe criptografia.
- A revogação é efetiva no commit da operação.
- Retirar o paciente da lista acessível ao médico.
- Invalidar permissões em requisições seguintes e nos canais em tempo real.
- Limpar caches privados e invalidar links de leitura/download que permitiriam acesso posterior.
- Não permitir que uma notificação antiga devolva o acesso.
- Informar a contraparte por notificação interna sem dados clínicos.

Informações já vistas ou exportadas não podem ser recolhidas pela revogação. O requisito é interromper o acesso pelo sistema.

### 5.4 Histórico e investigações abertas

Decisão desta versão: ao revogar, investigações abertas naquele ciclo são **encerradas administrativamente por revogação do vínculo**.

- Manter mensagens e origem.
- Registrar o sistema como executor do encerramento e vincular causalmente a ação ao evento AssociationRevoked.
- Exibir ClosedReason equivalente a ASSOCIATION_REVOKED.
- Não apresentar esse encerramento como resolução clínica da dúvida.
- O paciente mantém acesso ao próprio histórico.
- O médico perde o acesso por aquele ciclo, inclusive ao histórico das conversas.
- Uma nova associação não reabre essas investigações nem entrega automaticamente suas mensagens ao médico.

Estado do vínculo, encerramentos decorrentes e eventos de proveniência devem ser consistentes. Para o volume desta entrega, realizar a mudança numa transação coerente. Se a infraestrutura exigir processamento assíncrono, bloquear o acesso no commit da revogação e concluir encerramentos com outbox durável e estado explícito, sem janela de autorização.

### 5.5 Demonstração UCI e registros legados

Preservar a exceção do primeiro SDD: o importador provisiona vínculos ACTIVE de demonstração, sem simular um aceite humano.

Registrar **DemoAssociationProvisioned**, com agente de software/importador, origem do dataset e correlação do lote. Não registrar AssociationConfirmed atribuído falsamente ao Doctor.

Reexecutar a importação não duplica eventos e não reativa vínculo revogado manualmente. Registros legados sem eventos podem receber evento de migração/importação com o horário real de observação. Não inventar datas ou autoria históricas.

## 6. Modelagem das investigações

Usar a entidade existente na ontologia, se houver. O nome conceitual **Investigation** apenas orienta a especificação.

### 6.1 Estrutura mínima

| Campo conceitual | Regra |
| --- | --- |
| Id | Identificador interno segundo a convenção atual. |
| PatientId | Paciente ao qual pertence o contexto. |
| DoctorId | Médico destinatário único. |
| AssociationId / AssociationCycleId | Instância confirmada do vínculo que autorizou a abertura. |
| AtypicalDayEventId | Opcional; usar a entidade real do resultado/dia atípico existente. |
| SourceResultVersion / SourceSnapshot | Referência preservada à versão do resultado associado, quando aplicável. |
| TitleEncrypted | Assunto da conversa. |
| Status | OPEN ou CLOSED. |
| AwaitingRole | PATIENT ou DOCTOR enquanto aberta; vazio quando encerrada. |
| OpenedByRole | Papel de quem iniciou. |
| OpenedByDomainId | PatientId ou DoctorId do autor, conforme o papel. |
| OpenedAt | Data de servidor. |
| ClosedAt / ClosedBy / ClosedReason | Metadados do encerramento. |
| Version | Controle de concorrência e histórico de mudanças. |

Uma investigação sem evento atípico possui AtypicalDayEventId nulo. Não criar um evento falso para satisfazer uma FK.

### 6.2 Mensagem

Usar entidade existente ou uma nova entidade compatível:

- Id e InvestigationId.
- Autor resolvido pelo servidor: papel e referência a Patient ou Doctor.
- Conteúdo em texto livre criptografado.
- Data de servidor e sequência determinística na conversa.
- Identificador de idempotência, quando aplicável.
- Referência de proveniência.

A mensagem inicial faz parte da conversa e deve ser criada atomicamente com a investigação.

Na primeira versão, mensagens não são editadas nem excluídas pela interface. Uma correção é registrada por nova mensagem, preservando a anterior.

Implementar limites de tamanho compartilhados entre frontend e backend, validação de texto vazio e renderização segura. Texto livre não deve executar HTML ou scripts.

### 6.3 Leitura e não lidas

Manter posição de leitura por participante, referenciando mensagem/seqüência persistida. Não usar timestamp do navegador como única fonte.

Registrar o avanço efetivo da posição de leitura, sem gerar eventos duplicados a cada renderização. Permitir identificar mensagens não lidas e o estado de leitura quando aplicável.

Não marcar todas as mensagens como lidas ao carregar apenas a listagem de investigações.

## 7. Abertura com e sem dia atípico

### 7.1 Iniciada pelo paciente

Com evento:

1. No popup ou detalhamento do dia atípico, selecionar **Abrir questionamento**.
2. Preencher o evento de origem no formulário.
3. Selecionar um médico com vínculo ACTIVE.
4. Informar assunto e mensagem inicial.
5. Criar investigação, mensagem, proveniência e notificação interna.

Sem evento:

1. Em Questionamentos, selecionar **Novo questionamento**.
2. Escolher médico com vínculo ACTIVE.
3. Informar assunto e mensagem inicial.
4. Manter a origem como **Sem dia atípico associado**.

Se houver mais de um médico, exigir seleção explícita. Se houver apenas um, pode ser pré-selecionado, mantendo sua identificação visível. Se não houver médico associado, orientar para Buscar médico sem criar investigação órfã ou enviar a um destinatário arbitrário.

### 7.2 Iniciada pelo médico

- Selecionar um paciente com vínculo ACTIVE.
- Abrir a partir de um evento autorizado ou de Novo questionamento.
- O Doctor destinatário é o próprio médico do contexto autenticado.
- Informar assunto e mensagem inicial.
- Notificar somente o paciente da investigação.

O médico não abre investigação em nome de outro Doctor nem usa paciente sem vínculo.

### 7.3 Validações de origem

No servidor:

- O vínculo está ativo e pertence ao par Patient/Doctor.
- O paciente é o proprietário do evento informado.
- O evento está acessível ao autor e existe na versão identificada.
- O evento é um resultado real do algoritmo, não uma data arbitrária enviada pelo frontend.
- O destinatário pertence ao contexto autorizado.
- Mensagem inicial e assunto estão válidos.
- A mesma operação reenviada com chave de idempotência não cria duas investigações.

É permitido abrir investigações distintas sobre o mesmo evento quando isso for uma ação deliberada. Mostrar as já existentes para o par autorizado, evitando duplicação acidental. Não expor conversas de outro médico nesse indicador.

### 7.4 Preservação após recálculo

Uma investigação conserva a referência ao resultado que motivou sua abertura.

- Reutilizar versionamento/proveniência do algoritmo.
- Preservar entidade histórica ou snapshot protegido e suficiente do resultado, com referência ao processamento.
- Se o dia deixar de ser classificado como atípico, não apagar a conversa.
- Exibir que a origem corresponde a uma classificação anterior.
- Não reatribuir silenciosamente a conversa ao novo resultado.
- Não gerar um novo resultado clínico ou alterar a classificação por causa da conversa.

Se a base ainda não identifica cada resultado/dia, adicionar identidade estável e versão compatíveis com a ontologia; não criar uma segunda representação concorrente do algoritmo.

### 7.5 Coordenação proativa iniciada pelo sistema

A identificação de dias atípicos já existe. Integrar seu resultado ao fluxo de colaboração, sem substituir o algoritmo:

1. O processamento existente identifica e persiste um novo resultado de dia atípico.
2. O sistema registra/reutiliza a proveniência dessa identificação e cria uma notificação interna para o Patient proprietário.
3. Na área autenticada, o paciente encontra um aviso como: **Identificamos um dia atípico nas suas leituras. Você quer abrir um questionamento com um médico associado?**
4. O aviso permite **Ver o dia**, **Abrir questionamento** e **Agora não**.
5. Abrir questionamento apresenta a origem e a escolha explícita do Doctor autorizado.
6. A investigação só nasce depois que o paciente confirma o envio do assunto e da mensagem inicial.
7. O Doctor escolhido recebe a notificação da nova investigação.

A identificação automática coordena o início da possível atividade. A decisão de investigar permanece com o paciente; detectar não significa encaminhar dados automaticamente a um médico.

**Ver o dia** abre o popup/detalhe existente com a data/resultados correspondentes. **Agora não** registra que o convite foi adiado ou dispensado, sem alterar a classificação, criar uma investigação ou impedir abertura posterior pelo card.

Sem vínculo ACTIVE, explicar a necessidade de associar um médico e oferecer **Buscar médico**. Não direcionar para médico aleatório ou para todos os profissionais vinculados.

### 7.6 Repetição, contexto e histórico de detecção

- Identificar o convite por Patient, resultado/dia lógico e tipo de notificação, evitando repetir em cada login, refresh ou reprocessamento equivalente.
- Se o resultado já tiver uma investigação, oferecer acesso a ela ao Patient, preservando a escolha consciente de abrir outra; não disparar convites repetitivos por essa razão.
- Uma mera troca de versão técnica do algoritmo não deve produzir novo convite sobre o mesmo resultado sem regra explícita de mudança relevante.
- Não reexibir automaticamente o aviso dispensado em cada navegação. O card e a notificação/histórico continuam permitindo acesso posterior.
- Usar textos e metadados de origem que não afirmem que um resultado histórico aconteceu hoje.
- A importação UCI deve gerar um aviso consolidado ou uma ação de demonstração controlada sobre os resultados históricos, sem gerar um alerta por leitura ou uma enxurrada de notificações.
- Registrar o SoftwareAgent real responsável pela identificação/convite e as ações do Patient, sem fabricar uma resposta ou abertura automática em seu nome.

O aviso é oferecido dentro do sistema. Não exigir e-mail confirmado nem adicionar envio externo para implementar esse fluxo.

## 8. Acompanhamento e encerramento CSCW

### 8.1 Estados e coordenação

| Situação | Status | AwaitingRole |
| --- | --- | --- |
| Paciente abriu ou enviou a última mensagem | OPEN | DOCTOR |
| Médico abriu ou enviou a última mensagem | OPEN | PATIENT |
| Um participante encerrou | CLOSED | Vazio |
| Sistema encerrou por revogação | CLOSED | Vazio |

AwaitingRole é uma indicação de coordenação, não bloqueio: ambos podem acrescentar mensagens enquanto a investigação estiver aberta e o vínculo ativo.

Mensagens consecutivas do mesmo participante não alternam o responsável de forma artificial. A indicação acompanha o autor da última mensagem válida.

### 8.2 Interface

Na listagem, exibir assunto, contraparte, data, estado, indicação de quem deve responder, não lidas e presença/ausência de evento associado.

Na conversa, exibir:

- Participantes autorizados e autoria de cada mensagem.
- Estado atual.
- Referência ao dia atípico, quando existir.
- Mensagens ordenadas pela sequência persistida.
- Campo de mensagem enquanto OPEN e com vínculo ativo.
- Ação **Encerrar questionamento**, disponível a ambos os participantes.
- Histórico de abertura/encerramento e motivo administrativo, quando aplicável.

O encerramento por paciente ou médico não precisa de aceite do outro. Permitir observação final opcional, criptografada; quando houver, registrar como mensagem vinculada à operação.

Depois de CLOSED, não aceitar novas mensagens ou mudança silenciosa do estado. Nova dúvida exige nova investigação. Reabertura fica fora do escopo.

### 8.3 Cooperação e limites

As mensagens formam o registro contextual construído pelos participantes. Uma observação final pode sintetizar o entendimento, sem ser obrigatória e sem ser apresentada automaticamente como laudo ou plano terapêutico.

Não criar prazo de resposta garantido, atendimento de emergência ou diagnóstico automático no conteúdo do produto.

## 9. Card, popup e filtros de dias atípicos

### 9.1 Card existente

Preservar o cálculo e a apresentação já existentes. Acrescentar affordance acessível para **Ver dias atípicos**, abrindo popup/modal.

Definir a contagem a partir da semântica real do algoritmo. Se o card conta dias, listar dias distintos e não confundir múltiplos eventos do mesmo dia com dias diferentes.

Se já houver filtros de período no detalhamento, card e popup devem usar o mesmo escopo. A contagem deve ser coerente com a lista ou explicar quando representa todo o histórico.

### 9.2 Conteúdo do popup

Exibir, conforme os resultados já disponíveis:

- Data do dia atípico no fuso de apresentação adotado para o paciente.
- Identificador/referência do resultado.
- Motivo ou indicadores que o algoritmo realmente fornece.
- Leituras/resumo do dia quando disponíveis e autorizados.
- Ações **Ver no detalhamento**, **Selecionar para filtrar** e **Abrir questionamento**.
- Indicador de investigações do par autorizado, quando existir.

Não inventar causas, severidade, diagnóstico ou indicadores que o algoritmo não calcula.

Quando houver vários eventos num mesmo dia, agrupar pela data e preservar as referências individuais. Abrir questionamento exige escolher a origem concreta se houver ambiguidade.

### 9.3 Filtros e aplicação

- Permitir filtrar a lista do popup por período.
- Permitir selecionar um ou vários dias.
- Oferecer **Aplicar filtro no detalhamento** e **Limpar seleção**.
- A seleção deve filtrar as leituras e gráficos do detalhamento do Patient atual pelos dias exatos escolhidos.
- Para dias não consecutivos, não substituir a seleção por um intervalo que inclua os dias intermediários.
- Usar o mesmo componente/serviço de filtros da tela, sem criar dois estados divergentes.
- Preservar outros filtros compatíveis; combinar por interseção e mostrar quando essa combinação não produzir leituras.
- Se as datas selecionadas estiverem fora do período global, ajustar explicitamente o período para abranger a seleção, indicando a mudança na interface.
- Exibir chips ou indicação equivalente dos dias selecionados e uma ação para limpar o filtro de dias.
- Limpar a seleção de dias preserva os demais filtros.
- **Ver no detalhamento** aplica apenas aquele dia e leva o foco à seção correspondente.
- **Abrir questionamento** usa o evento selecionado; aplicar filtro não abre conversa.

Usar as fronteiras corretas de dia no fuso do paciente. Uma leitura perto da meia-noite não deve ser deslocada para outro dia por comparação indevida com UTC.

### 9.4 Estados e acessibilidade

- Estado vazio para ausência de dias atípicos.
- Loading, paginação quando necessária e erro com possibilidade de tentar novamente.
- Seleção preservada ao paginar ou filtrar a lista, com quantidade visível.
- Ações indisponíveis para recursos não autorizados.
- Foco inicial no popup, fechamento por teclado, retorno de foco ao card, rótulos e navegação por teclado.
- Ao revogar o vínculo, o médico não mantém popup funcional, dados em cache ou filtros que continuem buscando conteúdo do paciente.

O paciente tem acesso ao próprio detalhamento. O médico só acessa o detalhamento de pacientes com vínculo ativo e dentro do escopo autorizado.

## 10. Proveniência persistida e auditabilidade

### 10.1 Reutilizar a base existente

Inspecionar o mecanismo já implementado. Estender seus eventos, atividades e relacionamentos em vez de criar um log paralelo desconectado da ontologia.

A base precisa registrar **quem fez o quê, sobre qual entidade, quando, a partir de qual estado e com qual resultado**. Log textual de aplicação e notificação visual não substituem proveniência persistida.

Se houver exportação RDF/PROV-O, manter IDs estáveis e o mapeamento existente. Se não houver integração com grafo em tempo real, persistir primeiro os eventos na base e preparar exportação/mapeamento compatível; não impor outro banco ou GraphDB sem necessidade do repositório.

### 10.2 Estrutura de evento

| Campo conceitual | Finalidade |
| --- | --- |
| EventId | Identidade estável e única do evento. |
| EventType / SchemaVersion | Tipo de ação e versão do contrato. |
| AggregateType / AggregateId | Associação, investigação, mensagem ou resultado envolvido. |
| AggregateVersion / Sequence | Ordem e versão, sem depender só do relógio. |
| PatientId / DoctorId | Participantes envolvidos quando aplicável. |
| ActorUserAccountId | Conta que autenticou a ação humana; não possui os conteúdos clínicos. |
| ActorDomainRole / ActorDomainId | Papel e entidade Patient/Doctor que executou a ação. |
| ActorKind / SoftwareAgentId | Distingue ação humana de sistema/importador. |
| OccurredAt / RecordedAt | Horários de servidor, armazenados em UTC; distinguir ocorrência de observação quando necessário. |
| CorrelationId / CausationId | Agrupa uma operação e identifica seu evento causal. |
| BeforeVersion / AfterVersion | Liga estados ou versões usados e produzidos. |
| Outcome | Resultado efetivamente persistido. |
| PayloadEncrypted / EntityReferences | Metadados protegidos e referências suficientes para reconstituir a ação. |
| IdempotencyKey | Evita duplicação causada por repetição da mesma operação, quando aplicável. |

Eventos não devem conter senha, token, chave, e-mail, CRM ou mensagem clínica em claro. Preferir referências a entidades/versionamentos em vez de duplicar o texto completo da conversa.

Metadados que identifiquem contextos clínicos precisam das mesmas restrições de acesso. Não publicar IDs relacionáveis ou grafos como se a presença de pseudônimos garantisse anonimização.

### 10.3 Eventos obrigatórios

Os nomes abaixo são conceitos de aplicação, não termos padronizados da W3C. Adaptar à nomenclatura existente preservando a semântica.

| Evento | Momento | Agente/efeito |
| --- | --- | --- |
| AssociationRequested | Solicitação persistida | Patient; produz versão PENDING. |
| AssociationConfirmed | Aceite efetivo | Doctor destinatário; produz ACTIVE. |
| AssociationRejected | Recusa efetiva | Doctor destinatário. |
| AssociationRequestCancelled | Retirada da solicitação | Patient solicitante. |
| AssociationRevoked | Revogação efetiva | Patient ou Doctor; registrar papel e versão ACTIVE anterior. |
| DemoAssociationProvisioned | Provisionamento UCI novo | Software/importador; nunca inventar aceite humano. |
| InvestigationOpened | Abertura com ou sem evento | Patient/Doctor; liga vínculo e origem opcional. |
| InvestigationMessageAdded | Mensagem persistida | Autor autenticado; referencia mensagem e nova versão. |
| InvestigationReadAdvanced | Avanço real do marcador de leitura | Participante que efetivamente leu até a posição. |
| InvestigationClosed | Encerramento pelo participante | Patient/Doctor e motivo/observação opcional. |
| InvestigationClosedByAssociationRevocation | Encerramento administrativo | SoftwareAgent; CausationId aponta para AssociationRevoked. |
| AtypicalDayDetailViewed | Consulta autorizada ao detalhe de um resultado | Ator e referência ao resultado, sem copiar dados clínicos. |
| PatientDetailFilterApplied | Aplicação efetiva de seleção de dias | Ator; Patient e referências/datas protegidas conforme o modelo. |
| AtypicalDayInvestigationPromptCreated | Convite persistido a partir de identificação real | SoftwareAgent; referencia resultado e Patient; não representa abertura de investigação. |
| AtypicalDayInvestigationPromptDeferred | Patient seleciona Agora não | Patient; preserva resultado e possibilidade de abertura posterior. |
| NotificationCreated | Notificação interna persistida | SoftwareAgent; referencia evento causal e destinatário, com conteúdo mínimo. |
| NotificationRead | Destinatário efetivamente lê/marca a notificação | Ator autenticado; não equivale à leitura da conversa. |

A leitura da lista de médicos e a abertura do popup, sozinhas, não devem produzir milhares de eventos por re-renderização. Se o projeto audita buscas/perfis, registrar ações reais deduplicadas sem critérios de busca em claro. Registros de acesso/segurança podem compartilhar infraestrutura, mas sua finalidade deve permanecer distinguível da proveniência da mudança de domínio.

Tentativas negadas são eventos de segurança com resultado negado; nunca registrar evento de domínio de sucesso para uma ação que não ocorreu.

### 10.4 Atomicidade, outbox e notificações

- Persistir mutação de domínio e evento de proveniência na mesma transação.
- Se falhar a gravação do evento, a mutação não é confirmada.
- Acrescentar notificação/outbox durável na mesma transação.
- Publicar notificações somente depois do commit.
- Usar consumidor idempotente para não duplicar alertas.
- Se RDF/grafo for outra base, sincronizar por outbox com estado de entrega e tentativas; não exigir uma transação distribuída para cada mensagem.
- A base transacional continua permitindo provar a ação enquanto a projeção externa está pendente.
- Não retornar sucesso enquanto a proveniência existir apenas em memória ou em um logger.
- Garantir que notificações/outbox já pendentes não exponham mensagens após uma revogação.

### 10.5 Mapeamento PROV-O

Quando compatível com a ontologia atual:

| Elemento do MyGlico | Representação de proveniência |
| --- | --- |
| Ação de solicitar, confirmar, revogar, enviar ou encerrar | prov:Activity. |
| Autor humano autenticado ou importador | prov:Agent / prov:SoftwareAgent, ligado ao papel de domínio. |
| Versão do vínculo, investigação, mensagem e resultado usado | prov:Entity. |
| Estado/resultado usado pela ação | prov:used da atividade para a entidade de entrada. |
| Versão ou mensagem produzida | prov:wasGeneratedBy da entidade para a atividade. |
| Autor responsável pela ação | prov:wasAssociatedWith da atividade para o agente. |
| Autoria da entidade | prov:wasAttributedTo da entidade para o agente, quando aplicável. |
| Nova versão do mesmo objeto | prov:wasRevisionOf, segundo o modelo de versionamento existente. |
| Resultado atípico utilizado para abrir conversa | prov:used; complementar com relacionamento de domínio entre investigação e resultado. |

Não inventar termos no namespace prov. Adicionar propriedades do domínio no namespace MyGlico existente, quando necessárias. Não usar prov:wasDerivedFrom automaticamente para toda referência de navegação; registrar derivação somente quando a semântica da transformação a justificar.

Não exportar conteúdo de mensagens ou identificadores pessoais em literais públicos. A projeção RDF precisa respeitar autorização e proteção do conjunto de dados.

### 10.6 Preservação e consulta

- Eventos são append-only para as credenciais da aplicação.
- Correções são novos eventos; não reescrever autoria ou relógio de registros anteriores.
- Evitar cascade delete que apague proveniência ao encerrar/revogar.
- Manter sequência e versionamento para reconstruir transições.
- Disponibilizar histórico autorizado de solicitação, confirmação, revogação, abertura, mensagens e encerramento.
- O paciente acessa o histórico de suas próprias interações.
- Médico com vínculo revogado não recupera dados clínicos por endpoints de auditoria.
- Consulta técnica de auditoria usa permissão específica, sem conceder acesso geral a médicos.
- Integridade append-only não significa inviolabilidade diante de um administrador do banco; documentar o alcance e os controles existentes.

Preservar histórico não significa retenção ilimitada. Aplicar a política do projeto e mecanismos de correção/eliminação legalmente cabíveis sem apagar silenciosamente a cadeia de eventos operacionais.

## 11. Notificações internas e mensagens não lidas

Reutilizar a infraestrutura existente. Se não existir, implementar notificações e marcadores de leitura persistidos, consultáveis na sessão seguinte.

### 11.1 Gatilhos e destinatários

| Ação | Destinatário | Efeito visível |
| --- | --- | --- |
| Identificação de novo dia atípico | Patient proprietário | Aviso/convidar a abrir questionamento e notificação interna. |
| Solicitação de associação | Doctor selecionado | Solicitação pendente e notificação. |
| Confirmação ou rejeição do vínculo | Patient solicitante | Notificação do resultado. |
| Revogação | Contraparte | Informação de vínculo revogado, sem dados clínicos. |
| Abertura de investigação | Contraparte da investigação | Nova conversa e mensagem inicial não lida. |
| Nova mensagem do Doctor | Patient da investigação | Notificação e incremento das mensagens não lidas. |
| Nova mensagem do Patient | Doctor destinatário | Notificação e incremento das mensagens não lidas. |
| Encerramento humano | Contraparte | Aviso de encerramento. |
| Encerramento por revogação | Patient | Aviso administrativo, agrupado com a revogação para evitar alertas redundantes. |

Os destinatários são resolvidos no servidor. Não enviar alertas a outros médicos associados ao mesmo paciente.

Texto de notificação deve ser mínimo, por exemplo **Você tem uma nova mensagem em um questionamento**. Conteúdo clínico só aparece depois da autorização na conversa.

### 11.2 Indicadores obrigatórios na interface

- Sino/central de notificações com quantidade de notificações ainda não lidas.
- Menu **Questionamentos** com quantidade total de mensagens não lidas do contexto autorizado.
- Cada investigação na lista com contador de suas mensagens não lidas e indicação visual.
- Na conversa, distinção entre mensagens já lidas e novas quando pertinente.
- Indicadores disponíveis para Patient e Doctor, inclusive quando a conta possui os dois papéis, respeitando o contexto selecionado.
- Contadores derivados do backend e preservados após refresh, logout/login ou uso em outro dispositivo.
- Atualização quando uma mensagem chega com a conversa fechada.
- Nenhuma mensagem enviada pelo próprio usuário conta como não lida para ele.

Quantidade de notificações e quantidade de mensagens são medidas diferentes: exibir rótulos corretos e não somar as duas como se representassem o mesmo total.

### 11.3 Leitura de notificação versus leitura de conversa

Abrir a central ou marcar um aviso como lido não deve marcar automaticamente a conversa como lida.

A posição de leitura da conversa só avança quando o conteúdo correspondente foi carregado e apresentado com sucesso, ou numa ação explícita de marcar as mensagens como lidas. O backend deve validar participante, sequência e autorização.

- Carregar a listagem não limpa os contadores de mensagens.
- Entrar numa conversa que falhou ao carregar não limpa o contador.
- Com paginação, não marcar como lidas mensagens além da posição efetivamente apresentada.
- Marcar mensagem como lida reduz o contador de forma consistente e gera InvestigationReadAdvanced.
- Marcar uma notificação como lida gera NotificationRead sem duplicações.
- Uma notificação causal de mensagem pode ser reconciliada depois da leitura efetiva dessa mensagem, respeitando o vínculo entre os dois registros.
- Leitura indica exibição/ação de leitura no sistema; não comprova entendimento clínico.

### 11.4 Persistência, entrega e atualização

- Persistir mensagem, novo estado da investigação, proveniência e notificação/outbox atomicamente.
- Atualizar a interface em tempo real se a infraestrutura já oferecer esse mecanismo.
- Na ausência dele, consultar ao entrar/retomar a janela e em intervalo configurado; os avisos devem continuar funcionando sem WebSocket.
- Falha de entrega instantânea não perde o aviso: a próxima consulta recupera notificações e contadores.
- Consumidores idempotentes evitam notificações duplicadas da mesma mensagem/operação.
- Receber uma notificação não significa que ela foi lida.
- O paciente vê que há mensagem nova mesmo sem ter aberto a conversa; o mesmo vale para o médico.

### 11.5 Revogação e autorização

URLs e IDs em notificações não dispensam autorização. Ao clicar numa notificação de vínculo revogado, informar indisponibilidade sem carregar conteúdo clínico não autorizado.

Notificações já enfileiradas precisam revalidar a autorização antes de expor conteúdo ou criar um novo efeito visível. O médico revogado não continua recebendo novos dados da investigação nem contadores que revelem sua atividade posterior.

O aviso mínimo da própria revogação pode permanecer acessível como registro administrativo; ele não contém mensagens, leituras ou dados clínicos.

## 12. Concorrência, repetição e segurança

- Usar versionamento/optimistic locking ou mecanismo equivalente para estados.
- Impedir duas associações PENDING/ACTIVE simultâneas para o mesmo par, conforme o modelo do ciclo.
- Duas confirmações da mesma solicitação produzem uma transição e um evento de sucesso.
- Repetir revogação já concluída não cria novo evento de sucesso nem requer aprovação.
- Aceite concorrente com cancelamento deve respeitar uma transição válida; retornar conflito ou estado atualizado.
- Envio concorrente com revogação: ordenar as operações. Mensagem só é aceita se o vínculo ainda estiver ACTIVE no momento da persistência; a revogação precisa bloquear operações posteriores.
- Envio concorrente com encerramento: não aceitar mensagem numa investigação CLOSED.
- Sequência de mensagens deve ser determinada pelo servidor.
- Filtrar endpoints, downloads, notificações, conexões em tempo real e consultas RDF por autorização.
- Manter criptografia, índices protegidos e sessões conforme o primeiro SDD.
- Não permitir leitura de investigação apenas por adivinhar Id/SHORTID.
- Não expor mensagens em logs, traces, alertas técnicos ou ferramentas de analytics.
- Não incluir conteúdo de saúde ou critérios CRM + UF em URLs que gerem logs desnecessários.

## 13. Contratos conceituais

Adaptar nomes de rotas e métodos ao projeto. O servidor resolve atores e valida recursos em todas as operações.

| Operação | Entrada | Regra principal |
| --- | --- | --- |
| Buscar médico | SHORTID ou CRM + UF | Patient autenticado; resposta mínima. |
| Solicitar associação | DoctorId selecionado | Patient da sessão; cria PENDING + evento + notificação. |
| Listar solicitações | Sessão/contexto | Apenas solicitações do próprio participante. |
| Confirmar/rejeitar | Solicitação e versão | Apenas Doctor destinatário; transição atômica. |
| Cancelar solicitação | Solicitação e versão | Apenas Patient solicitante. |
| Revogar | Vínculo e versão | Qualquer participante; sem aceite da contraparte. |
| Listar médicos/pacientes | Sessão/contexto | Escopo próprio e vínculos autorizados. |
| Abrir investigação | Contraparte, origem opcional, assunto e mensagem | Vínculo ACTIVE e origem do mesmo Patient. |
| Listar investigações | Filtros de estado, contraparte e origem | Autorizar Patient/Doctor e ciclo; não retornar conversas alheias. |
| Ler conversa | InvestigationId | Permissões atuais; paginação e marcador de leitura explícito. |
| Enviar mensagem | Conteúdo, versão/chave de repetição | OPEN + vínculo ACTIVE + autor do contexto. |
| Encerrar | InvestigationId, versão e observação opcional | Qualquer participante autorizado; não exige aceite do outro. |
| Listar dias atípicos | Patient/contexto e período | Mesma autorização do detalhamento; fonte do algoritmo existente. |
| Ver dia atípico | Resultado/versão | Pertence ao Patient e ao escopo autorizado. |
| Aplicar filtro no detalhamento | Datas/IDs selecionados | Seleção consistente e autorização do Patient. |
| Consultar histórico | Recurso/contexto | Perfil autorizado e conteúdo mínimo; sem contornar revogação. |

Falhas de autorização não devem revelar títulos, participantes ou conteúdo do recurso. Operações idempotentes retornam o estado já persistido segundo o contrato, sem novo efeito.

## 14. Plano de execução do agente

| Etapa | Trabalho | Evidência |
| --- | --- | --- |
| T01 | Inspecionar ontologia, código e primeiro SDD | Mapa dos componentes reais e das adaptações necessárias. |
| T02 | Definir estados/versionamento de associação e investigação | Transições e referências compatíveis com as entidades atuais. |
| T03 | Estender proveniência persistida e outbox | Mutações e eventos atômicos; mapeamento PROV-O quando existente. |
| T04 | Implementar busca, solicitação, confirmação e revogação | Papéis, filtros e histórico corretos. |
| T05 | Ajustar importador UCI | Proveniência de software e respeito a revogações/idempotência. |
| T06 | Implementar abertura, mensagens, leitura e encerramento | Com/sem evento atípico; destinatário único. |
| T07 | Integrar detecção, convite ao paciente e notificações/não lidas | Convite sem abertura automática; entrega pós-commit e contadores persistidos/autorizados. |
| T08 | Acrescentar popup e filtros ao card | Lista coerente com o algoritmo e integração com o detalhamento. |
| T09 | Testar concorrência, proveniência e autorização | Critérios de aceite executados e resultados registrados. |
| T10 | Documentar migração e entrega | Arquivos reais, comandos, alterações e limitações. |

Preservar dados e referências existentes nas migrações. Não executar publicação ou migração destrutiva em produção como parte automática desta especificação.

## 15. Critérios de aceite

| ID | Cenário | Resultado obrigatório |
| --- | --- | --- |
| CA-01 | Patient busca por SHORTID ou CRM + UF | Perfil correto e mínimo, sem acesso público ou dados de terceiros. |
| CA-02 | Patient solicita associação | PENDING + evento e notificação; nenhum acesso clínico antes do aceite. |
| CA-03 | Outro médico tenta confirmar | Acesso negado; estado não muda. |
| CA-04 | Doctor destinatário confirma | ACTIVE + evento com autoria/tempo/versionamento corretos. |
| CA-05 | Rejeitar/cancelar pendência | Estado terminal coerente e proveniência persistida. |
| CA-06 | Patient revoga | REVOKED imediatamente, sem confirmação do médico. |
| CA-07 | Doctor revoga | REVOKED imediatamente, sem confirmação do paciente. |
| CA-08 | Sessão/tempo real permanecem abertos após revogação | Médico deixa de acessar recursos; notificações antigas não restauram acesso. |
| CA-09 | Investigação aberta no vínculo revogado | Encerramento administrativo rastreável; histórico preservado para Patient. |
| CA-10 | Nova associação depois de revogação | Exige novo aceite e não restaura automaticamente conversas antigas. |
| CA-11 | Reimportação UCI | Não duplica eventos nem reativa vínculo revogado. |
| CA-12 | Vínculo UCI provisionado | Agente software/importador; não representa aceite humano fictício. |
| CA-13 | Patient abre com dia atípico | Origem real, Doctor selecionado e mensagem inicial persistidos atomicamente. |
| CA-14 | Patient abre sem dia atípico | Abertura funciona com origem nula; nenhum evento artificial. |
| CA-15 | Doctor abre com ou sem dia atípico | Apenas próprio contexto e paciente com vínculo ACTIVE. |
| CA-16 | Evento pertence a outro Patient | Abertura negada, sem vazamento de dados. |
| CA-17 | Paciente possui vários médicos | Escolha explícita de destinatário e isolamento das conversas. |
| CA-18 | Mensagem enviada | Conteúdo protegido, autor do servidor, ordem e proveniência corretas. |
| CA-19 | Leitura efetiva e repetida | Marcador avança; não duplica eventos por renderização. |
| CA-20 | Patient ou Doctor encerra | CLOSED e autoria corretos, sem aceite da contraparte. |
| CA-21 | Enviar depois de CLOSED | Operação negada; histórico intacto. |
| CA-22 | Recálculo remove classificação atípica | Investigação conserva origem histórica e mensagens. |
| CA-23 | Clique no card de dias atípicos | Popup com lista correspondente à contagem/escopo explicado. |
| CA-24 | Seleção de dias não consecutivos | Detalhamento mostra somente os dias selecionados, não o intervalo inteiro. |
| CA-25 | Outros filtros aplicados | Composição e limpeza coerentes, com indicação visual e estado único. |
| CA-26 | Leitura próxima de meia-noite | Pertence ao dia correto no fuso de apresentação. |
| CA-27 | Ausência de dias/erro/loading | Interface acessível e estado apropriado, sem inventar resultados. |
| CA-28 | Falha ao gravar proveniência | Mutação de domínio revertida; não há sucesso sem evento. |
| CA-29 | Falha de publicação da notificação/grafo | Evento e outbox duráveis permitem retry; sem duplicidade de efeitos. |
| CA-30 | Confirmar/revogar/enviar em concorrência | Transições válidas, sem mensagens posteriores ao encerramento/revogação. |
| CA-31 | Inspeção do banco e logs | Conteúdos sensíveis protegidos, sem credenciais ou mensagens em claro. |
| CA-32 | Consulta de proveniência por médico revogado | Não contorna a autorização nem devolve histórico clínico. |
| CA-33 | Usuário atua como Patient e Doctor | Autor, contexto e permissões do papel correto em cada operação. |
| CA-34 | Repetição de requisição com idempotência | Um efeito e um conjunto de eventos de sucesso. |
| CA-35 | Regressão da página inicial | Continua informativa, com login/cadastro e sem pacientes públicos. |
| CA-36 | Algoritmo persiste novo dia atípico | Patient recebe convite e notificação, com proveniência da origem; nenhuma investigação automática. |
| CA-37 | Patient escolhe Agora não | Convite adiado/dispensado e evento persistido; não repete em cada refresh, e abertura manual continua possível. |
| CA-38 | Patient aceita convite com vários médicos | Origem preservada, seleção explícita e notificação somente ao Doctor escolhido após envio. |
| CA-39 | Doctor envia mensagem e Patient não abre conversa | Patient vê notificação e contador de mensagem não lida, inclusive após novo login. |
| CA-40 | Patient envia mensagem e Doctor não abre conversa | Doctor vê notificação e contador simétricos. |
| CA-41 | Usuário lê só a notificação ou abre a listagem | Contador de mensagens permanece até leitura efetiva da conversa. |
| CA-42 | Conversa falha ou mensagens estão em páginas não apresentadas | Não marcar como lidas mensagens não exibidas. |
| CA-43 | Mensagem é efetivamente apresentada | Marcador avança, contador atualiza e proveniência registra sem repetição. |
| CA-44 | Canal em tempo real falha | Persistência e consulta posterior recuperam avisos e contadores. |
| CA-45 | Importação/reprocessamento histórico UCI | Aviso consolidado/controlado e deduplicado, sem datas falsas ou enxurrada de convites. |

Testar fluxos de ponta a ponta, integrações transacionais, consultas de autorização e corridas de estados. Para proveniência, validar registros e relações gerados no banco; verificar a projeção RDF quando fizer parte da arquitetura encontrada.

## 16. Definição de concluído

O agente deve entregar implementação revisável, migrações compatíveis e evidências dos critérios de aceite.

Relatar:

- Arquivos e entidades reais alterados.
- Ajustes da ontologia e do mapeamento de proveniência, quando necessários.
- Migrações, configuração e comandos executados.
- Como testar buscas, associações, revogação, investigação e popup.
- Evidência de atomicidade, autoria e preservação do histórico.
- Resultados dos testes e limites não resolvidos.
- Estado da sincronização RDF/outbox, se existente.

Não apresentar log de aplicação, notificação ou timestamp isolado como cumprimento integral de proveniência. Não afirmar que o sistema diagnostica ou que toda investigação encerrada foi clinicamente resolvida.

## 17. Histórico de revisão

### Versão 1.1

- Explicitada a coordenação proativa: resultado de dia atípico → aviso ao Patient → decisão de abrir → seleção de Doctor → investigação.
- Notificações e contadores de mensagens não lidas tornados obrigatórios e persistentes para ambos os papéis.
- Separada leitura de notificação de leitura de conversa.
- Acrescentados eventos de proveniência e critérios CA-36 a CA-45.

## 18. Referências

Consultadas em 06/10/2026. Usar os requisitos específicos deste documento para as decisões de produto.

- Documento base: MyGlico_SDD_Cadastro_Autenticacao.md.
- W3C, PROV-O: The PROV Ontology: https://www.w3.org/TR/prov-o/
- OWASP, Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP, Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP, Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html

PROV-O fundamenta a representação de entidade, atividade e agente. Os estados de vínculo, regras de revogação, investigação e UX são decisões desta especificação para o MyGlico.
