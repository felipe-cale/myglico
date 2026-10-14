# Decisões de arquitetura do Assistente Glico

**Registro inicial:** 2026-10-13. **Base:** `felipe-cale/impeccable-ux` @ `e776b9bce55767fdfb58aa8533d34c58465bec8b`. Branch de trabalho criada: `codex/glico-fase1`. Checkout já continha mudanças modificadas e não rastreadas (incluindo especificações, `.claude/`, `output/`, `outputs/`, `tmp/` e artefatos); foram preservadas sem staging.

1. **Fases:** só F1.0–F1.4. XLSX/CSV, templates, lote e leitura de várias medições ficam fora (F2 requer autorização futura).
2. **Coordenação disponível:** ferramentas desta sessão oferecem Codex e não oferecem sessões/agentes Claude ou Antigravity. Nenhuma delegação/revisão desses agentes é alegada. Backlog/contratos foram registrados antes de qualquer implementação concorrente. Revisão independente final ainda pendente.
3. **Modelo não tem autoridade:** sem credenciais, seleção de identidade, confirmação, SQL/shell/URL ou chamada genérica. Modelo pode produzir somente schema tipado; regras/FAQ e permissões ficam determinísticas no servidor.
4. **Confirmação e atomicidade:** o endpoint Glico de confirmação revalida sessão, CSRF, owner, ciclo, contexto e versão; chama a operação de domínio dentro da transação que grava efeito, origem/eventos/notificações, receipt e estado EXECUTED. Restrição única torna retries/concor­rência seguros; efeito sem receipt nunca confirma.
5. **Privacidade de mídia:** stream binário limitado em memória até worker privado autenticado; sem multipart spool, arquivo temporário, banco, fila persistente, log/APM ou backup. Sem fallback/egress externo. Worker não toca identidade clínica nem banco. Revalidar contexto após inferência.
6. **Fail closed:** flags independentes; OCR/ASR indisponíveis não impedem entrada manual, FAQ ou operações determinísticas. Limites globais exigem backend compartilhado; sem DB/Redis de quota ou configuração explícita, capacidade cara fica inativa.
7. **Modelos e qualidade:** PaddleOCR e faster-whisper são dependências pesadas e requerem provisionamento/avaliação sintética, modelo/digest/licença e isolamento. Nenhuma qualidade é presumida por mock. A fase não pode ser declarada aprovada sem os corpus/gates da SDD.
8. **Banco e migrações:** migrations novas com DDL explícito e reversível, preservando revisões antigas; SQLite FK ON e verificação MySQL 8 obrigatória.
9. **Ownership:** Codex é owner de backend/segurança e arquivos compartilhados nesta rodada. Frontend fica reservado ao Claude se disponível; mídia/infra ao Antigravity se disponível. Integração posterior deve ocorrer por patches/commits explícitos, nunca sobrescrever alterações locais.
10. **Status de aceite:** matriz só muda com evidência realmente executada. Sem MySQL 8, navegador, modelos reais e revisor novo, respectivos critérios continuam não executados/parciais e fase não aprovada.

## Modelo de linguagem opcional (Gemini) — 14/10/2026

Autorizado pelo responsável pelo produto como evolução fora do SDD original. Ativado somente se `MYGLICO_GEMINI_API_KEY` estiver definida no ambiente (nunca em arquivo versionado); sem ela o assistente permanece determinístico. `MYGLICO_GEMINI_MODEL` aceita uma lista separada por vírgula, tentada em ordem (padrão: `gemini-3.5-flash,gemini-3.1-flash-lite`); `MYGLICO_GEMINI_TIMEOUT_SECONDS` limita cada tentativa.

- O modelo só converte a fala do usuário em uma intenção estruturada (`app/services/glico_llm.py`). Recebe apenas o texto digitado e até 6 turnos curtos de histórico; nunca recebe leituras, métricas, nomes ou identificadores.
- Nada é executado pelo modelo: a intenção é mapeada para os mesmos tratadores determinísticos e propostas com revisão e confirmação. Valor numérico que não esteja no texto digitado é descartado.
- Perguntas sobre dose ou medicação são recusadas por regra determinística, antes do modelo.
- Qualquer falha, timeout ou saída inválida cai silenciosamente no assistente por palavras-chave.
- A interface informa ao usuário que o que ele digita é enviado ao Gemini (Google) quando o recurso está ativo (`capabilities.language_model`).
