# Features a desenvolver

Backlog de especificações, incluído em 06/10/2026. **As duas features estão implementadas e aprovadas na auditoria integral independente (Codex, sessão nova, 2026-10-09), que confrontou toda a branch com os dois SDDs completos, e na reauditoria das correções; o código final foi aprovado por uma segunda auditoria integral independente, com um revisor novo**; ver também [AUDITORIA-INTEGRAL.md](AUDITORIA-INTEGRAL.md) e [AUDITORIA-INTEGRAL-FINAL.md](AUDITORIA-INTEGRAL-FINAL.md); ver [REVISAO-FINAL.md](REVISAO-FINAL.md) e [MATRIZ-ACEITE.md](MATRIZ-ACEITE.md) (66 Aprovado, 2 Não aplicável).

| Ordem | Feature | Especificação | Estado |
| --- | --- | --- | --- |
| 1 | Cadastro, autenticação e proteção de dados | [SDD v1.0](01-cadastro-autenticacao/MyGlico_SDD_Cadastro_Autenticacao.md) | Implementada e aprovada (auditoria integral) |
| 2 | Vínculos, colaboração CSCW e proveniência | [SDD v1.1](02-vinculos-cscw-proveniencia/MyGlico_SDD_Vinculos_CSCW_Proveniencia.md) | Implementada e aprovada (auditoria integral) |
| 3 | Assistente Glico para pacientes e médicos | [SDD v1.0](03-assistente-glico/MyGlico_SDD_Assistente_Glico.md) | F1 implementada (backend, mídia, frontend); revisão independente R2: NO-GO por gates de mídia real/operação |

O pacote do [assistente Glico](03-assistente-glico/README.md), acrescentado em 13/10/2026, tem SDD, matriz própria e prompt de coordenação de vários agentes para o Orca. A fase 1 cobre leitura individual, OCR, áudio, FAQ e colaboração; XLSX/CSV e lotes ficam em F2. Estado em 14/10/2026: código e testes verdes (Python 139 passed/1 skipped; E2E 110 passed/1 skipped; MySQL 8.4), mas OCR/ASR reais não atingem o gate do SDD e a mídia permanece desligada; ver [REVISAO-FINAL-F1-R2.md](03-assistente-glico/REVISAO-FINAL-F1-R2.md). As aprovações e evidências abaixo pertencem às features 1 e 2 e não se aplicam à feature 3.

Os SDDs das features 1 e 2 foram copiados integralmente dos documentos fornecidos na organização inicial. A SDD da feature 3 foi elaborada a partir dos requisitos consolidados com o usuário. As instruções de implementação de cada pacote são destinadas à execução futura pelo agente responsável.

Busca de médico, associação e autorização são compartilhadas: implementar uma única solução. O segundo SDD detalha o ciclo dos vínculos e acrescenta as investigações; a exclusão do chat no escopo isolado do primeiro SDD não o exclui da entrega conjunta. Os nomes dos documentos complementares citados nos originais referem-se aos arquivos nas duas subpastas acima.

## Execução e validação

- [Prompt completo para o Orca](PROMPT-ORCA.md): coordenação de agentes, dependências, implementação e testes.
- Revisão independente obrigatória por agente dedicado sobre toda a entrega e os dois SDDs; o parecer futuro será salvo em `REVISAO-FINAL.md`, após implementação e validação.
- [Matriz de aceite](MATRIZ-ACEITE.md): 23 critérios AUT e 45 critérios CSCW, inicialmente não executados.
- Ler também `AGENTS.md`, `README.md` e `README.pt-br.md` na raiz. O README canônico é `README.md`.

Inspeção inicial: a base usa FastAPI, SQLAlchemy/Alembic e React/Vite. `app/models/entities.py` contém `Patient`, indicadores, resultados de análise e proveniência; não foram encontradas classes `Doctor` ou `UserAccount` nesse arquivo. O manifesto do frontend não declara uma suíte E2E. A implementação deve confirmar o estado real do checkout antes de definir contratos e migrações, sem assumir que os modelos conceituais dos SDDs já existem.

Manter aqui os planos e evidências de implementação, sem credenciais, chaves, dados clínicos reais ou capturas sensíveis. Atualizar o estado das features somente com base nos testes executados.
