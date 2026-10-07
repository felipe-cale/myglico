# MyGlico — SDD de cadastro, autenticação e proteção de dados

**Data:** 06/10/2026  
**Versão:** 1.0  
**Abordagem:** Specification-Driven Development (SDD): requisitos → desenho → implementação → validação.  
**Destino:** agente responsável pela implementação no repositório do MyGlico.  
**Estado:** especificação para execução; não representa código já implementado ou repositório inspecionado.

## 1. Instrução inicial ao agente

Implemente esta especificação no MyGlico. Antes de editar, leia as instruções do repositório, inspecione a ontologia, as entidades, o esquema de persistência, o importador UCI, as rotas, a autenticação eventualmente existente e a página inicial.

Use a arquitetura e as convenções já adotadas. Nomes de campos, contratos e rotas apresentados aqui são conceituais; adapte-os ao projeto, mantendo os comportamentos obrigatórios. Registre os arquivos reais encontrados e as decisões de adaptação.

**Alteração obrigatória da página inicial:** a página pública do MyGlico deve deixar de listar pacientes. Preserve e reorganize a explicação do MyGlico que já existe, a identidade visual e a logo atuais. Disponibilize as opções **Entrar** e **Criar conta**. No cadastro, o usuário deve escolher o papel **Paciente** ou **Médico**.

A remoção da listagem deve abranger componentes, chamadas de API, conteúdo renderizado no servidor, pré-carregamentos, estado inicial, metadados e caches públicos. Esconder o componente visual não atende ao requisito. A listagem de pacientes passa a existir somente na área autenticada e conforme os vínculos do usuário.

Não recrie o sistema, não renomeie entidades da ontologia sem necessidade, não prometa funcionalidades inexistentes no conteúdo da página e não substitua a lógica já implementada de identificação de dias atípicos.

## 2. Contexto e objetivo

O MyGlico já importa o dataset público UCI Diabetes, possui registros de pacientes e leituras e identifica dias atípicos. A nova entrega deve acrescentar contas de acesso, papéis, vínculos paciente–médico, proteção de dados no armazenamento e navegação autenticada.

Os registros UCI receberão contas de **demonstração**, mantendo sua origem histórica. Isso não significa identificar ou contactar as pessoas originais do dataset.

As entidades de domínio são **Patient** e **Doctor**, em conformidade com a ontologia existente. **UserAccount** concentra as credenciais e se relaciona com Patient e/ou Doctor. Leituras, dias atípicos, investigações e outros objetos de domínio continuam relacionados a Patient ou Doctor, conforme o modelo existente.

## 3. Escopo

### 3.1 Incluído

- Página pública informativa, sem pacientes ou dados de saúde.
- Cadastro com seleção explícita de papel.
- Login, logout e proteção de sessão.
- UserAccount vinculada a Patient, Doctor ou ambos.
- SHORTID alfanumérico de seis caracteres, independente para Patient e Doctor.
- Proteção de e-mail, nomes, CRM, UF e conteúdos pessoais e de saúde.
- Hash de senha com salt e parâmetros registrados.
- Busca exata de médico por SHORTID ou CRM + UF.
- Associação N:N paciente–médico e aplicação de permissões.
- Evolução idempotente do importador UCI para contas e médico de demonstração.
- Migração que preserve registros e referências existentes.
- Testes dos fluxos principais e das fronteiras de acesso.

### 3.2 Fora desta entrega

- ResearchParticipation.
- Entidades PatientProfile e DoctorProfile.
- Confirmação de e-mail: funcionalidade futura, sem bloquear o cadastro ou login atual.
- Biometria, upload de documentos e integração automatizada com CFM.
- Novo algoritmo de dias atípicos.
- Implementação completa do chat/investigação, caso ainda não exista. Esta entrega prepara os vínculos e as permissões; não amplia automaticamente seu escopo.
- Recuperação automática por e-mail não verificado. Se já existir, revisar para que não permita tomar uma conta por um endereço cuja propriedade não foi comprovada.

O cadastro de Doctor registra uma identidade profissional declarada. Não exibir selo de verificação profissional sem um processo real de verificação. Perfis de demonstração devem ser apresentados como demonstração e não receber CRM inventado.

## 4. Requisitos funcionais

| ID | Requisito obrigatório |
| --- | --- |
| RF-01 | A página inicial pública explica o MyGlico e oferece Entrar e Criar conta. |
| RF-02 | Nenhum paciente, leitura ou histórico é carregado ou exposto na página pública. |
| RF-03 | O cadastro exige selecionar Paciente ou Médico e exibe os campos correspondentes. |
| RF-04 | Cadastro de paciente cria UserAccount e Patient de forma atômica. |
| RF-05 | Cadastro de médico cria UserAccount e Doctor de forma atômica. |
| RF-06 | O modelo suporta uma mesma UserAccount relacionada a Patient e Doctor. |
| RF-07 | O papel solicitado no cadastro não permite atribuir administrador, vincular registros alheios ou aprovar privilégios. |
| RF-08 | Login funciona com e-mail e senha sem confirmação prévia de e-mail. |
| RF-09 | Patient e Doctor possuem SHORTID próprio, único em sua tabela. |
| RF-10 | Paciente autenticado busca Doctor por SHORTID ou pelo par CRM + UF. |
| RF-11 | Resultado de busca expõe apenas o perfil profissional previsto; não expõe e-mail ou pacientes do médico. |
| RF-12 | A criação de vínculo depende de uma ação explícita e de confirmação dos envolvidos. |
| RF-13 | O médico lista somente pacientes com vínculo ativo e acesso autorizado. |
| RF-14 | O paciente consulta e modifica apenas seus próprios registros, salvo outra permissão explicitamente existente. |
| RF-15 | Logout invalida a sessão conforme a infraestrutura adotada. |
| RF-16 | A importação UCI cria contas de demonstração e relaciona os pacientes importados ao médico de demonstração. |
| RF-17 | Reexecutar o importador não duplica registros nem redefine credenciais. |

## 5. Modelo de domínio e persistência

### 5.1 UserAccount

| Campo conceitual | Regra |
| --- | --- |
| Id | Chave interna segundo a convenção do projeto. |
| EmailEncrypted | E-mail com criptografia autenticada. |
| EmailLookup | Índice protegido para login e unicidade do e-mail normalizado. |
| PasswordHash | Hash adaptativo de senha; preferir Argon2id em biblioteca mantida, ou mecanismo consolidado do framework com configuração revisada. |
| PasswordSalt | Pode estar incorporado ao formato do PasswordHash. Nunca gerar ou reutilizar um salt global. |
| AccountStatus | Controle de ativação/desativação da conta. |
| EmailVerifiedAt | Opcional e inicialmente nulo; reservado para evolução futura. |
| CreatedAt / UpdatedAt | Metadados técnicos de manutenção. |
| IsDemo | Identificação de conta de demonstração, se compatível com as convenções existentes. |

UserAccount não deve duplicar nome, CRM, leituras ou outros atributos que pertencem ao domínio.

Se o framework já produz um hash autocontido com salt, algoritmo e custo, reutilize esse formato e não crie campos redundantes.

### 5.2 Patient

- Preservar os atributos, identificadores e relacionamentos da entidade existente.
- Acrescentar UserAccountId como referência única e opcional durante a migração.
- Acrescentar ShortId com seis caracteres.
- Proteger nome e outros atributos pessoais, quando existirem.
- Preservar a identificação de origem do dataset.
- Leituras e resultados continuam referenciando PatientId.
- Ao final do provisionamento UCI, cada paciente do escopo importado deve possuir uma conta de demonstração.

### 5.3 Doctor

- Id interno.
- ShortId de seis caracteres.
- UserAccountId como referência única.
- Nome profissional criptografado.
- CRM e UF criptografados.
- Índice protegido para busca exata CRM + UF.
- Indicação de demonstração.
- Se já houver estado de verificação profissional, preservar a distinção entre declarado e verificado.

No cadastro comum de médico, solicitar nome, CRM e UF. Para o médico criado pelo importador, CRM e UF podem ser nulos; não criar uma inscrição profissional fictícia. A busca por SHORTID deve funcionar para esse perfil.

### 5.4 Cardinalidades e associação

- UserAccount → Patient: zero ou um.
- UserAccount → Doctor: zero ou um.
- Patient → UserAccount: zero ou um durante migração; um para pacientes com acesso provisionado.
- Doctor → UserAccount: um para perfis autenticáveis.
- Patient ↔ Doctor: muitos para muitos, pela associação já prevista no projeto ou por uma entidade associativa compatível com a ontologia.

Uma conta ativa de domínio deve ter pelo menos um dos papéis. Fluxos transitórios de cadastro precisam ser atômicos e não deixar contas órfãs.

A associação deve permitir estados equivalentes a pendente, ativo e revogado, além de autoria e datas das alterações. Não ligar objetos clínicos diretamente a UserAccount para substituir Patient ou Doctor.

Usar restrições de unicidade no banco para UserAccountId em cada tabela, SHORTID por tabela, e-mail por índice de busca e duplicidade de vínculo. Para CRM + UF, examinar o modelo atual de inscrições e impedir duplicidade incompatível com ele.

## 6. Proteção dos dados

### 6.1 Objetivo e alcance

Uma consulta direta ao banco, ou cópia do banco sem as chaves, não deve revelar e-mail, nome, CRM, UF ou os conteúdos pessoais/de saúde protegidos.

Chaves internas, FKs, SHORTIDs, estados e metadados estruturais podem permanecer legíveis para manter a integridade e a operação. Esses elementos revelam relações e padrões; portanto, não afirmar anonimização total.

Criptografia de disco ou TDE, sozinha, não atende ao objetivo de ocultar valores de alguém capaz de executar SELECT nas tabelas. Aplicar proteção aos campos ou payloads na camada apropriada da aplicação.

### 6.2 Dados recuperáveis

- Usar criptografia autenticada mantida pela biblioteca/framework, preferencialmente AES-GCM com chave adequada.
- Garantir nonce exclusivo por operação sob a mesma chave.
- Armazenar ciphertext, nonce, tag e versão da chave em formato definido e testado.
- Vincular o ciphertext ao contexto do registro/campo com AAD ou recurso equivalente da biblioteca, para impedir troca indevida entre registros.
- Manter chaves fora do banco de dados, frontend, código versionado e logs.
- Separar as chaves de criptografia das chaves dos índices de busca.
- Definir rotação e compatibilidade com versões anteriores.
- Descriptografar apenas no backend autorizado e pelo tempo necessário à operação.

A proteção deve contemplar novos campos e conteúdos sensíveis já armazenados, conforme o inventário do agente. Não manter cópias em claro em colunas legadas, projeções, caches, arquivos temporários ou logs.

### 6.3 Senhas

Senhas não devem receber criptografia reversível. Usar hash adaptativo com salt aleatório por senha e comparação pela biblioteca de autenticação.

O salt não precisa ser secreto. A senha em claro só existe transitoriamente na entrada e nunca deve aparecer em logs, respostas, fixtures ou arquivos versionados. Registrar o algoritmo e seus parâmetros para permitir atualização do hash.

Não usar SHA-256 puro, Base64, algoritmos próprios ou senha compartilhada global como proteção das credenciais.

### 6.4 Busca protegida

Para e-mail e CRM + UF, usar um índice cego de igualdade implementado com primitivas consolidadas e chave secreta, por exemplo HMAC com separação de finalidade.

- Definir uma política única de normalização do e-mail para cadastro e login, respeitando o comportamento já adotado no sistema.
- Normalizar UF e CRM segundo a convenção definida, sem remover características válidas de inscrição.
- Serializar CRM + UF sem ambiguidade antes de calcular o índice.
- Aplicar unicidade e resolver conflitos de forma consistente.
- Não usar hash público simples para valores de baixo espaço de possibilidades.
- Não descriptografar toda a tabela para realizar login ou busca.
- Documentar que índices de igualdade revelam repetições e que a busca pode revelar existência de perfis ao usuário autorizado.
- Limitar buscas e retornar somente campos previstos do perfil.

Busca por CRM + UF é exata; autocomplete, buscas parciais e listagem pública não fazem parte da entrega.

### 6.5 Compatibilidade com leituras e dias atípicos

Inventariar como leituras, datas, valores e resultados são consultados antes de proteger campos. Se uma consulta depende de conteúdo que passará a ser criptografado, adaptar a camada de acesso ou o processamento sem criar uma réplica permanente em claro.

O algoritmo existente recebe os valores recuperados em contexto autorizado. Preservar resultados, significado, ordenação e desempenho aceitável. Definir quais metadados técnicos são mantidos legíveis e explicar qualquer exceção.

Não prometer execução de filtros, ordenações ou agregações SQL convencionais sobre ciphertext. Proteger também resultados que revelem informações de saúde.

## 7. SHORTIDs

Patient.ShortId e Doctor.ShortId são códigos públicos de seis caracteres alfanuméricos. Preferir uma convenção sem distinção de maiúsculas/minúsculas, por exemplo A–Z e 0–9.

- Gerar com CSPRNG.
- Aplicar UNIQUE no banco em cada tabela.
- Tentar novamente em colisão, inclusive sob concorrência.
- Manter os IDs internos para FKs.
- Não usar SHORTID como token de convite, segredo de acesso ou credencial.
- Não depender de o código ser difícil de adivinhar para proteger dados.
- Preservar os códigos existentes se já houver implementação compatível.

Um usuário com ambos os papéis possui dois SHORTIDs, um em Patient e outro em Doctor.

## 8. Experiência e navegação

### 8.1 Página pública

- Reutilizar a explicação atual do MyGlico e sua identidade visual.
- Exibir Entrar e Criar conta de maneira clara.
- Explicar apenas comportamentos já disponíveis, distinguindo propostas futuras quando necessário.
- Remover lista, cartões, seletor, contagem e atalhos públicos de pacientes.
- Não chamar endpoints clínicos ao carregar a página.
- Não mostrar credenciais de demonstração publicamente.

### 8.2 Cadastro

Primeiro passo: selecionar **Paciente** ou **Médico**.

Campos comuns: e-mail e senha. Acrescentar confirmação de senha conforme a UX existente, sem persistir esse campo.

Paciente: nome de exibição e demais campos mínimos já previstos pelo domínio.

Médico: nome profissional, CRM e UF. Exibir como informação declarada enquanto não verificada.

Criar UserAccount e entidade de domínio na mesma transação. Se qualquer etapa falhar, não deixar registros parciais. Não permitir que o cliente envie IDs de Patient/Doctor existentes para se apropriar deles.

Não exigir confirmação de e-mail nesta versão. Registrar ciência do aviso de privacidade sem tratar esse registro como consentimento genérico para qualquer uso.

### 8.3 Login e sessão

- Localizar a conta pelo índice protegido do e-mail.
- Validar a senha com o mecanismo de hashing.
- Verificar estado da conta.
- Derivar papéis dos relacionamentos do servidor.
- Criar sessão conforme a arquitetura existente.
- Usar mensagens genéricas em falha de autenticação e proteção contra tentativas repetidas.
- Aplicar HTTPS e proteções apropriadas ao mecanismo escolhido: cookies seguros/HttpOnly/SameSite e CSRF quando pertinentes, ou gestão adequada dos tokens e sua revogação.
- Não confiar em papel, PatientId ou DoctorId enviados pelo frontend.

A sessão referencia UserAccountId, e o backend resolve os objetos de domínio autorizados.

### 8.4 Área autenticada

Paciente: suas leituras, dias atípicos, médicos associados e funcionalidades já existentes.

Médico: seus pacientes vinculados e apenas os recursos autorizados.

Ambos os papéis: permitir escolher o contexto Paciente ou Médico depois de entrar. Alternar contexto não pode ampliar permissões.

Logout: encerrar a sessão e limpar estado e cache privados no frontend. Proteger navegação pelo botão voltar e compartilhamento de cache entre contas.

## 9. Busca, vínculo e autorização

A busca por médico está disponível para paciente autenticado, por SHORTID ou CRM + UF. O resultado pode incluir SHORTID, nome profissional, CRM/UF quando existentes, indicação de demonstração e estado de verificação quando real.

Não retornar e-mail, UserAccountId, lista de pacientes, informações de saúde ou campos internos desnecessários.

Fluxo mínimo de vínculo: solicitação do paciente → confirmação do médico → vínculo ativo. Revogação interrompe os acessos concedidos por esse vínculo.

O importador cria vínculos ativos somente entre os registros de demonstração que ele provisiona. Não aplicar essa ativação automática a cadastros comuns.

Toda operação de API, consulta, download, mensagem e canal em tempo real deve validar conta, papel, propriedade/vínculo e escopo do recurso no servidor.

Se investigações já existirem, preservar seu destinatário: outro médico associado ao paciente não acessa automaticamente uma conversa dirigida a um colega. Encerrar investigação e revogar vínculo são ações diferentes.

Rotas antigas de lista ou detalhe de paciente devem ser protegidas. Alterar apenas a página inicial não protege a API.

## 10. Evolução do importador UCI Diabetes

### 10.1 Execução

1. Localizar a implementação e identificar a chave de origem usada por Patient.
2. Criar ou localizar uma UserAccount de demonstração para o médico.
3. Criar ou localizar o Doctor de demonstração, sem CRM real ou fictício.
4. Importar/atualizar cada Patient mantendo IDs e referências existentes.
5. Criar ou localizar uma UserAccount de demonstração vinculada ao Patient.
6. Gerar SHORTIDs quando ausentes, sem substituir os existentes.
7. Criar o vínculo ativo entre Patient e Doctor de demonstração.
8. Preservar a importação das leituras e o cálculo de dias atípicos.

E-mails de demonstração podem usar um namespace sintético reservado, por exemplo patient-<identificador>@demo.myglico.invalid. Mesmo sintéticos, seguem a proteção dos campos da conta.

As credenciais são fornecidas por configuração protegida ou geradas por mecanismo seguro e disponibilizadas em canal controlado para testes. Não armazenar senha recuperável no banco, não imprimir senhas em logs e não versionar credenciais.

### 10.2 Idempotência e isolamento

- Usar identificação de origem estável, não nome ou SHORTID, para reconhecer Patient importado.
- Identificar de forma estável o Doctor de demonstração.
- Não duplicar contas ou vínculos.
- Não redefinir senha, e-mail ou SHORTID de registros já provisionados.
- Não ligar automaticamente uma conta comum a um Patient UCI.
- Não sobrepor contas reais ou vínculos criados manualmente.
- Registrar progresso e erros sem conteúdo sensível.
- Permitir retomada após falha parcial com transações por unidade coerente.
- Executar o provisionamento de demonstração por comando/modo explícito, sem habilitá-lo em ambiente real por acidente.

## 11. Migração

Antes de implementar, mapear registros existentes, índices, FKs e consumidores das entidades. Escolher a estratégia conforme o banco e o framework encontrados.

Ordem proposta:

1. Acrescentar estrutura de contas, referências opcionais, SHORTIDs e associação, preservando a ontologia.
2. Preparar serviços de proteção e gestão de chaves.
3. Fazer backfill de SHORTIDs, resolver unicidade e validar referências.
4. Converter dados pessoais/de saúde existentes para o formato protegido, com versão e processamento retomável.
5. Provisionar contas/vínculos UCI em ambiente de demonstração.
6. Migrar os consumidores para os campos protegidos.
7. Retirar cópias antigas em claro após validar a conversão e sua recuperação.
8. Proteger endpoints e ativar a nova navegação.

Não derrubar tabelas, recriar pacientes ou alterar IDs para acomodar a autenticação. Preservar a proveniência existente. Não apresentar como concluída a proteção se colunas antigas ainda expõem os valores.

Definir backup protegido e plano de recuperação antes da migração de dados. Não manter rollback permanente que dependa de uma cópia em claro.

## 12. Contratos conceituais

Adaptar nomes e métodos às convenções do repositório.

| Operação | Entrada principal | Regra |
| --- | --- | --- |
| Cadastro | E-mail, senha, papel e campos do domínio | Criar conta + Patient/Doctor atomicamente; não aceitar elevação de privilégios. |
| Login | E-mail e senha | Busca por índice protegido, validação de hash e criação de sessão. |
| Sessão atual | Sessão | Retornar dados mínimos e contextos autorizados. |
| Logout | Sessão | Invalidar sessão; limpar estado privado. |
| Busca de médico | SHORTID ou CRM + UF | Exigir paciente autenticado; resposta mínima e limite de tentativas. |
| Solicitar vínculo | Médico selecionado | Patient é resolvido pela sessão, não confiado ao cliente. |
| Aceitar vínculo | Solicitação | Doctor destinatário é resolvido e autorizado pelo servidor. |
| Revogar vínculo | Vínculo | Autorizar a operação e bloquear acessos subsequentes. |
| Meus pacientes | Sessão de médico | Somente vínculos ativos; resposta paginada e protegida. |
| Minhas leituras | Sessão de paciente | Somente Patient correspondente e recursos próprios. |

IDs em rotas nunca dispensam autorização. Não colocar e-mail, CRM ou conteúdo clínico em URLs sujeitas a logs se o contrato puder usar corpo protegido por TLS.

## 13. Plano de execução do agente

| Etapa | Trabalho | Evidência esperada |
| --- | --- | --- |
| T01 | Inspecionar repositório e ontologia | Mapa de entidades, rotas, importador, página inicial e convenções reais. |
| T02 | Ajustar modelo e migrações | Patient, Doctor e UserAccount coerentes; restrições e referências preservadas. |
| T03 | Implementar proteção e índices | Criptografia autenticada, hashing de senha, gestão de chaves e busca exata. |
| T04 | Implementar cadastro e sessão | Papéis, transações, login/logout, autorização no servidor. |
| T05 | Evoluir importador UCI | Contas e médico de demonstração, vínculos e idempotência. |
| T06 | Substituir entrada pública | Explicação existente, Entrar/Criar conta, ausência de dados de pacientes. |
| T07 | Implementar busca e vínculos | Perfil mínimo, solicitações, aceite/revogação e lista privada. |
| T08 | Executar migração e regressão em ambiente adequado | Dados e resultados preservados; ausência de cópias em claro indevidas. |
| T09 | Validar e documentar | Critérios de aceite, comandos usados, resultados e limitações concretas. |

Não tratar esta especificação como autorização para publicar em produção, executar migrações destrutivas ou importar demonstração em um ambiente real. Produzir primeiro a implementação revisável e executar as verificações adequadas no ambiente de desenvolvimento/teste disponível.

## 14. Critérios de aceite e testes

| ID | Cenário | Resultado obrigatório |
| --- | --- | --- |
| CA-01 | Visitante abre a página inicial | Vê a explicação atual, Entrar e Criar conta; nenhum paciente ou dado clínico é carregado. |
| CA-02 | Visitante tenta API/rota antiga de paciente | Acesso negado; não basta ocultar o frontend. |
| CA-03 | Cadastro como paciente | Cria UserAccount e Patient relacionados, com SHORTID válido. |
| CA-04 | Cadastro como médico | Cria UserAccount e Doctor relacionados; nome/CRM/UF protegidos. |
| CA-05 | Falha ao criar entidade de domínio | Transação revertida; conta órfã não permanece. |
| CA-06 | E-mail ainda não confirmado | Cadastro e login permitidos nesta versão. |
| CA-07 | Consulta direta das tabelas sem chaves | Não revela e-mail, nome, CRM, UF, senha ou conteúdo sensível protegido. |
| CA-08 | Mesma senha em duas contas | Hashes/salts distintos; senhas não recuperáveis por descriptografia. |
| CA-09 | E-mail já cadastrado ou cadastro concorrente | Unicidade preservada por índice protegido e restrição do banco. |
| CA-10 | Busca exata de médico | SHORTID e CRM + UF localizam corretamente o perfil permitido. |
| CA-11 | Usuário manipula papel ou IDs no request | Não obtém administrador nem acesso a Patient/Doctor alheio. |
| CA-12 | Paciente A tenta leituras do paciente B | Acesso negado, inclusive por alteração de URL/ID. |
| CA-13 | Médico sem vínculo tenta paciente | Acesso negado. |
| CA-14 | Vínculo revogado com sessão ainda ativa | Próxima requisição é negada; canal em tempo real deixa de entregar dados. |
| CA-15 | Dois médicos vinculados ao mesmo paciente | Conversa dirigida a um não é automaticamente visível ao outro, se esse recurso existir. |
| CA-16 | Primeira importação UCI | Cada Patient importado ganha conta e vínculo ativo com Doctor de demonstração. |
| CA-17 | Segunda importação UCI | Contagens estáveis; credenciais, SHORTIDs e IDs existentes preservados. |
| CA-18 | Colisão de SHORTID simulada | Nova geração; nenhuma duplicação ou sobrescrita. |
| CA-19 | Conta com os dois papéis | Contextos funcionam, mantendo identidade e permissões de cada papel. |
| CA-20 | Logout/troca de conta | Sessão e cache não permitem visualizar os dados do usuário anterior. |
| CA-21 | Reprocessar conjunto de referência | Dias atípicos e leituras preservam os resultados esperados anteriores à proteção. |
| CA-22 | Ciphertext alterado ou trocado de contexto | Falha segura; não retorna dados adulterados nem expõe detalhes criptográficos. |
| CA-23 | Inspeção de logs, bundle e respostas públicas | Nenhuma credencial, chave ou conteúdo clínico indevido. |

Executar testes de integração de autorização e importação, testes das primitivas por meio da biblioteca adotada, verificações de migração e uma navegação real dos fluxos. Não criar testes que apenas repitam setters ou detalhes internos sem validar comportamento.

## 15. Definição de concluído

A entrega está concluída quando os critérios aplicáveis passaram, a ontologia e os IDs existentes foram preservados, o importador é idempotente e a entrada pública não acessa dados de pacientes.

O agente deve informar:

- Arquivos alterados e comportamento implementado.
- Migrações e comandos necessários.
- Como provisionar e acessar a demonstração sem expor credenciais.
- Como configurar as chaves e sua versão, sem incluir os valores.
- Testes executados e resultados.
- Critérios ainda não atendidos e motivos concretos.

Confirmação de e-mail permanece registrada como evolução futura. Não afirmar conformidade integral com LGPD ou anonimização apenas por implementar criptografia.

## 16. Referências técnicas

Referências consultadas em 06/10/2026; revisar versões ao implementar.

- OWASP, Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP, Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP, Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP, Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- CipherSweet, searchable encryption e índices cegos: https://ciphersweet.paragonie.com/
- Charité, Development of a Trusted Third Party at a Large University Hospital, 2024: https://medinform.jmir.org/2024/1/e53075
- The Advanced Confidentiality Engine, 2025: https://pmc.ncbi.nlm.nih.gov/articles/PMC12631087/

Essas referências fundamentam as decisões de segurança. As entidades, o importador e a experiência da página inicial seguem os requisitos específicos definidos para o MyGlico.

