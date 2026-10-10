# Features a desenvolver

Backlog de especificações, incluído em 06/10/2026. **As duas features estão implementadas e aprovadas na auditoria integral independente (Codex, sessão nova, 2026-10-09), que confrontou toda a branch com os dois SDDs completos, e na reauditoria das correções; o código final foi aprovado por uma segunda auditoria integral independente, com um revisor novo**; ver também [AUDITORIA-INTEGRAL.md](AUDITORIA-INTEGRAL.md) e [AUDITORIA-INTEGRAL-FINAL.md](AUDITORIA-INTEGRAL-FINAL.md); ver [REVISAO-FINAL.md](REVISAO-FINAL.md) e [MATRIZ-ACEITE.md](MATRIZ-ACEITE.md) (66 Aprovado, 2 Não aplicável).

| Ordem | Feature | Especificação | Estado |
| --- | --- | --- | --- |
| 1 | Cadastro, autenticação e proteção de dados | [SDD v1.0](01-cadastro-autenticacao/MyGlico_SDD_Cadastro_Autenticacao.md) | Implementada e aprovada (auditoria integral) |
| 2 | Vínculos, colaboração CSCW e proveniência | [SDD v1.1](02-vinculos-cscw-proveniencia/MyGlico_SDD_Vinculos_CSCW_Proveniencia.md) | Implementada e aprovada (auditoria integral) |

Os SDDs foram copiados integralmente dos documentos fornecidos. As instruções internas são requisitos para a implementação futura; a solicitação atual foi apenas organizá-los no projeto e preparar a delegação ao Orca.

Busca de médico, associação e autorização são compartilhadas: implementar uma única solução. O segundo SDD detalha o ciclo dos vínculos e acrescenta as investigações; a exclusão do chat no escopo isolado do primeiro SDD não o exclui da entrega conjunta. Os nomes dos documentos complementares citados nos originais referem-se aos arquivos nas duas subpastas acima.

## Execução e validação

- [Prompt completo para o Orca](PROMPT-ORCA.md): coordenação de agentes, dependências, implementação e testes.
- Revisão independente obrigatória por agente dedicado sobre toda a entrega e os dois SDDs; o parecer futuro será salvo em `REVISAO-FINAL.md`, após implementação e validação.
- [Matriz de aceite](MATRIZ-ACEITE.md): 23 critérios AUT e 45 critérios CSCW, inicialmente não executados.
- Ler também `AGENTS.md`, `README.md` e `README.pt-br.md` na raiz. O README canônico é `README.md`.

Inspeção inicial: a base usa FastAPI, SQLAlchemy/Alembic e React/Vite. `app/models/entities.py` contém `Patient`, indicadores, resultados de análise e proveniência; não foram encontradas classes `Doctor` ou `UserAccount` nesse arquivo. O manifesto do frontend não declara uma suíte E2E. A implementação deve confirmar o estado real do checkout antes de definir contratos e migrações, sem assumir que os modelos conceituais dos SDDs já existem.

Manter aqui os planos e evidências de implementação, sem credenciais, chaves, dados clínicos reais ou capturas sensíveis. Atualizar o estado das features somente com base nos testes executados.
