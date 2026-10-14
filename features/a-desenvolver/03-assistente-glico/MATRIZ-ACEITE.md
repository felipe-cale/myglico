# Matriz de aceite do assistente Glico

**Data:** 13/10/2026  
**SDD:** [MyGlico SDD do assistente Glico](MyGlico_SDD_Assistente_Glico.md), versão 1.0.  
**Estado inicial de todos os critérios:** não executado. **Atualizado em 14/10/2026** com a revisão independente R2 (nenhum critério Aprovado; mídia real reprovada/parcial). Esta matriz registra validação futura; não transfere aprovações das features AUT/CSCW para o Glico.

## Como preencher

Cada linha precisa de teste/cenário, comando, ambiente/commit, resultado e link para evidência sintética. Use Aprovado, Reprovado, Parcial, Não executado ou Não aplicável com justificativa. Mock não é prova de execução real de OCR/ASR. Os requisitos detalhados do SDD continuam obrigatórios mesmo quando agrupados numa linha.

F1 = fase 1 completa, incluindo seus incrementos. F2 = lotes. Critérios F1 são regressão obrigatória de F2. Bloqueador significa que a fase não pode ser liberada com o critério falhando/parcial. Qualidade de mídia tem o gate quantitativo da seção 11 e evidência distinta de segurança.

## Fundação e autorização

| ID | Fase | Requisitos | Cenário e resultado obrigatório | Camada | Bloqueador | Status | Evidência |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GLI-CA-001 | F1 | SEC-01, ARC-01 | Anônimo/sessão inválida tenta messages, image, audio e confirm: 401; nenhuma inferência, tool ou escrita | HTTP | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-002 | F1 | SEC-02, SEC-04 | Paciente A forja identidade/papel/ator e IDs de B: schemas rejeitam; A não lê/prepara/grava para B | HTTP + DB | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-003 | F1 | SEC-04, SEC-05, API-04 | Alterar conversation/proposal/attempt IDs em todas as rotas: recurso alheio e ausente têm 404 equivalente, sem leak | HTTP | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-004 | F1 | SEC-03, FUN-11 | Médico sem vínculo ou PENDING seleciona paciente: negação e nenhum contexto clínico/modelo carregado | HTTP + E2E | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-005 | F1 | SEC-05, SEC-06 | Dois médicos ACTIVE: cada um vê suas investigações; revogar/reassociar não reabre ciclo/conversa antiga | HTTP + DB | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-006 | F1 | SEC-09, SEC-24 | Revogar vínculo durante inferência ou antes de retry receipt: resultado/receipt clínico negado; sem nova escrita | Concorrência MySQL | Sim | Não executado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-007 | F1 | SEC-01, SEC-09, DAT-03 | Logout/expiração durante inferência/confirmação: acesso revalidado e serializado; sessão revogada não executa | HTTP + MySQL | Sim | Não executado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-008 | F1 | SEC-07, FUN-12 | Trocar paciente/período em abas concorrentes durante request: context_version impede resultado misturado e invalida proposta antiga | HTTP + E2E | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-009 | F1 | SEC-08, SEC-10 | Alternar contas/pacientes e inspecionar caches/contexto: nenhum dado cruzado; limpar estado ao logout/troca | E2E + instrumentação | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-010 | F1 | FUN-17 | Médico tenta glucose_single/bulk e endpoint direto: negação por papel mesmo com vínculo ACTIVE | HTTP | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-011 | F1 | SEC-12, SEC-13 | Origin adversário/nulo, token CSRF ausente/errado e header interno forjado: recusar antes de gastar/executar | HTTP adversarial | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-012 | F1 | SEC-11 | Responses/erros/poll/download Glico não cacheados; CDN não reutiliza resposta entre contas | HTTP + deploy | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |

## Confirmação e integridade

| ID | Fase | Requisitos | Cenário e resultado obrigatório | Camada | Bloqueador | Status | Evidência |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GLI-CA-013 | F1 | SEC-18, SEC-20, UX-06 | Texto/áudio/OCR/modelo contém "sim", confirmed=true ou tool confirm: nenhuma ação executada sem botão/endpoint próprio | HTTP adversarial | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-014 | F1 | SEC-20, SEC-21, SEC-22 | Alterar valor/unidade/data/destinatário/operation no confirm: rejeitar; editar cria nova versão e revisão | HTTP + E2E | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-015 | F1 | SEC-07, SEC-22 | Confirmar versão/contexto antigo, expirado ou cancelado: zero efeito, resposta adequada e sem leak | HTTP | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-016 | F1 | SEC-23, SEC-24 | Duplo clique, chaves diferentes e 10 confirmações concorrentes: um efeito/receipt; retry autorizado consistente | MySQL + E2E | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-017 | F1 | SEC-23 | Mesma idempotency key com conteúdo/operação conflitante: 409, sem segundo efeito | HTTP + MySQL | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-018 | F1 | SEC-25, SEC-26, PROV-03, ARC-02, ARC-04 | Injetar falha após insert clinical/source/event/receipt: tudo rollback, proposta não EXECUTED e retry seguro | SQLite + MySQL | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-019 | F1 | SEC-24, UX-07 | Commit seguido de perda da resposta/reload: consulta receipt, não repete; sucesso só após prova persistida | HTTP + E2E | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-020 | F1 | SEC-27 | Retry de open investigation/send message: uma mensagem/evento de sucesso e notificações esperadas sem duplicação | HTTP + DB | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-021 | F1 | SEC-28, FUN-20, FUN-22 | NaN/Infinity, 0, >1000, data ambígua, fuso divergente e unidade ausente bloqueiam READY/commit | Unit + HTTP | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-022 | F1 | SEC-28, UX-04 | Unidade mmol/L explicitamente fornecida: conversão testada, valor original/convertido visíveis e mesma normalização no commit | Unit + E2E | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |

## Prompt injection e infraestrutura

| ID | Fase | Requisitos | Cenário e resultado obrigatório | Camada | Bloqueador | Status | Evidência |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GLI-CA-023 | F1 | SEC-15, SEC-16, SEC-18, API-03 | Injection nos canais texto/OCR/ASR/notas/tool result tenta segredo, paciente alheio ou confirmação; nenhuma ferramenta/efeito/egress proibido | Adversarial instrumentado | Sim | Não executado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-024 | F1 | API-01, ARC-09, ARC-03 | Modelo stub comprometido gera SQL/Python/shell/URL/tool desconhecida/schema extra: reject; zero acesso privilegiado | HTTP + tool spy | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-025 | F1 | ARC-01, ARC-06, PRV-12, ARC-03 | Inspecionar requests de worker/modelo: sem cookie, session ID, secrets ou identidade clínica desnecessária | Contract + instrumentação | Sim | Não executado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-026 | F1 | ARC-06, ARC-07 | Worker recebe auth ausente/assinatura errada/expirada, corpo alterado, path diferente ou replay em outra réplica: rejeição sem decode | Processador integração | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-027 | F1 | SEC-13, API-01, PRV-13 | URL interna, redirect ou fallback não aprovado: nenhuma conexão fora da allowlist e nenhum envio de mídia externa | Egress instrumentado | Sim | Não executado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-028 | F1 | SEC-14 | Saída com script/HTML/link javascript/imagem de tracking: render segura, sem execução ou conexão | E2E adversarial | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-029 | F1 | SEC-17, FAQ-02, LIM-04, ARC-10 | Pedidos fora do escopo recebem redirecionamento curto; FAQ/comandos conhecidos funcionam sem LLM; cota esgotada não bloqueia manual/confirm determinístico | HTTP + E2E | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-030 | F1 | OPS-03, OPS-04, OPS-06, ARC-08 | Flags/modelos/config inválidos: fail closed; fake não disponível em produção; downloads/egress runtime restritos | Deploy + contract | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |

## Privacidade e descarte

| ID | Fase | Requisitos | Cenário e resultado obrigatório | Camada | Bloqueador | Status | Evidência |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GLI-CA-031 | F1 | PRV-01, PRV-02 | Enviar marcador sintético em imagem/áudio: nenhum arquivo/spool/row/blob/fila contém mídia; request chunked também limitado | FS/DB/log spies | Sim | Não executado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-032 | F1 | PRV-05, PRV-06 | Sucesso, exception, cancel, timeout e disconnect: buffers/tracks liberados, processo termina, sem mídia tardia em disco | Browser + processador | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-033 | F1 | PRV-01, PRV-08, LIM-05 | Marcadores de transcrição/OCR/headers não aparecem em logs/APM/history/DB; só conteúdo final revisado de mensagem pode persistir criptografado | Instrumentação + DB | Sim | Não executado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-034 | F1 | PRV-03, PRV-04 | MIME spoof, imagem gigante/animada/truncada e metadata EXIF: limitar/rejeitar, sem bypass e sem EXIF persistido | Decoder adversarial | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-035 | F1 | PRV-07 | Matar worker no processamento: nenhuma retomada por upload persistido; estado expira e usuário pode reenviar | Fault injection | Sim | Não executado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-036 | F1 | PRV-09, PRV-10, DAT-02 | Inspecionar banco sem chaves: drafts/mensagens propostas ilegíveis; TTL/cleanup/revogação removem payloads como especificado | DB + scheduler | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-037 | F1 | PRV-10, DAT-04 | Restart/restore de backup: aplicar expiry antes de servir; receipt/tombstone mantém proteção contra repetição | Integração operacional | Sim | Não executado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-038 | F1 | PRV-12, PRV-13, PRV-14 | Fornecedor externo desabilitado/não aprovado: zero envio; gate documenta propósito/retention e nenhum Files API/fallback de mídia | Contract + egress | Sim | Não executado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |

## Limites e qualidade de mídia

| ID | Fase | Requisitos | Cenário e resultado obrigatório | Camada | Bloqueador | Status | Evidência |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GLI-CA-039 | F1 | LIM-01, LIM-02 | Concorrência em duas instâncias distribui cota/reservas atomicamente; excedente recebe 429 antes de compute | MySQL/Redis + HTTP | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-040 | F1 | LIM-02, LIM-03 | Retry SDK/transport, crash e execução incerta: teto respeitado, reserva conciliada sem refund indevido/dupla cobrança | Fault injection | Sim | Não executado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-041 | F1 | LIM-01, LIM-03, LIM-06 | Budget ausente/esgotado, circuito aberto e timeout: capability paga para, worker encerra, alerta sem dados clínicos | Integração + deploy | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-042 | F1 | MED-01, MED-02, MED-09, MED-10 | PaddleOCR real em corpus de avaliação: relatório por campo/hardware; gate quantitativo e cobertura atendidos | OCR real | Sim | Reprovado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-043 | F1 | FUN-18, FUN-19, FUN-21, MED-03, MED-04 | Reflexo, vários números, HI/LO, leitura múltipla: revisão/esclarecimento; zero escolha/gravação silenciosa | OCR real + E2E | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-044 | F1 | FUN-04, MED-05, MED-06, MED-09, MED-10 | faster-whisper real nos três idiomas, interface em idioma diferente: números preservados e gate por idioma documentado | ASR real + E2E | Sim | Reprovado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-045 | F1 | MED-07, MED-08 | Silêncio/ruído/música/idioma não compreendido/áudio longo: zero registro inventado; falha orientada e limites respeitados | ASR real | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-046 | F1 | MED-09, OPS-01, OPS-02, ARC-05 | Medir cold/warm/memória e deadlines na hospedagem alvo; não extrapolar benchmarks; frontend/API Vercel sem bundle pesado | Deploy + benchmark | Sim | Não executado | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |

## Produto e regressões

| ID | Fase | Requisitos | Cenário e resultado obrigatório | Camada | Bloqueador | Status | Evidência |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GLI-CA-047 | F1 | FUN-01, FUN-02, FUN-03, UX-04, UX-09 | Paciente registra por texto/foto/áudio, corrige e confirma: um registro próprio, home atualizada e métricas pending corretas | E2E + DB | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-048 | F1 | FUN-05, FUN-13, FUN-22 | Pedido PDF por texto/áudio: paciente/período/locale explícitos; download autenticado nos três idiomas sem envio ao modelo | E2E + HTTP | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-049 | F1 | FUN-06, PROV-06 | Alterar leitura após análise: Glico, detalhe/popup/prompts distinguem stale; não afirmam flag antiga como classificação atual | HTTP + E2E | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-050 | F1 | FUN-07, FUN-08, FUN-14, FUN-16 | Paciente/médico criam questionamento e ditam mensagem: destinatário/dias/conteúdo revisados e confirmados, notificações corretas | E2E + DB | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-051 | F1 | FUN-09, FUN-15, API-02 | Consultar vínculos/não lidas não altera consentimento nem read position pelo modelo; ação humana de navegação funciona | HTTP + E2E | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-052 | F1 | FUN-10, FAQ-01, FAQ-02, FAQ-03, FAQ-04, SEC-19 | FAQ por papel/locale/versão, sem configuração privada; respostas têm destino válido, não inventam funções/causas clínicas | Unit + E2E | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-053 | F1 | UX-01, UX-02, UX-03, UX-08 | Mobile 390/768 e desktop 1440, três locales, foco/teclado/contraste: controles legíveis e sem overflow | E2E + inspeção browser | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-054 | F1 | UX-05, UX-07, UX-10 | Teclado aberto, câmera/mic negados, ouvir/cancelar, reload/timeout: estados corretos, sem gravação escondida ou sucesso falso | E2E + browser | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-055 | F1 | PROV-01, PROV-02, PROV-03, PROV-04, PROV-05 | Eventos/receipt/origem distinguem humano e software, sem conteúdo bruto e sem export público; cadeia UCI preservada | HTTP + DB + artefatos | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-056 | F1 | DAT-01, TST-03 | Migrações em vazio e upgrade baseline, SQLite FK ON e MySQL 8: constraints/locks corretos, migrations antigas intactas | SQLite + MySQL | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-057 | F1 | TST-01, TST-02, TST-05 | Suíte separa doubles e modelos reais; mídia indisponível oferece manual; ataques verificam efeitos e egress | Revisão de testes | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-058 | F1 | TST-04, seção 19 | Regressão AUT/CSCW/PDF/frontend e import UCI duas vezes quando afetado: sem duplicação e indicadores/métricas populados | Suítes existentes | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |
| GLI-CA-059 | F1 | OPS-04, OPS-05, seção 19 | Runbook, flags, cleanup externo e rollback disponíveis; revisão independente confronta toda a fase sem bloqueadores | Revisão independente | Sim | Parcial | Revisão independente R2 (2026-10-14, 82f6266): [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md) |

## Fase 2

| ID | Fase | Requisitos | Cenário e resultado obrigatório | Camada | Bloqueador | Status | Evidência |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GLI-CA-060 | F2 | BAT-01, BAT-02 | XLSX/CSV com cabeçalhos pt/en/es, abas, BOM, separadores e datas diferentes: leitura ou mapeamento claro sem adivinhar | Parser + E2E | Sim | Não executado | — |
| GLI-CA-061 | F2 | BAT-03, BAT-04 | XLSM/XLSB/XLS/protegido, fórmula, link remoto, XML entities, ZIP path/ratio/entries: rejeitar/corrigir, sem execução ou fetch | Parser adversarial | Sim | Não executado | — |
| GLI-CA-062 | F2 | BAT-03, LIM-01 | ZIP bomb e excesso de bytes/linhas/células: parar antes/depois decode limitado, sem recurso ilimitado ou persistência | Processador + memória | Sim | Não executado | — |
| GLI-CA-063 | F2 | BAT-05, SEC-16, PRV-01 | Injection em célula/aba/filename: nenhuma mudança de ferramenta/identidade, nenhum envio integral ou storage | Egress + parser adversarial | Sim | Não executado | — |
| GLI-CA-064 | F2 | BAT-06 | Planilha com vários nomes/IDs: não muda paciente; bloqueia mistura e só permite linhas próprias explicitamente selecionadas | HTTP + E2E | Sim | Não executado | — |
| GLI-CA-065 | F2 | BAT-07, BAT-08, BAT-10 | Resumo mostra prontas/inválidas/excluídas/possíveis duplicatas e seleção explícita; sem perda silenciosa | E2E + parser | Sim | Não executado | — |
| GLI-CA-066 | F2 | BAT-09, MED-09 | Foto de várias leituras associa data/hora/valor por linha; casos ambíguos pedem correção/template, sem clonar horário | OCR real + E2E | Sim | Não executado | — |
| GLI-CA-067 | F2 | BAT-10, BAT-11 | Mudar linha/mapeamento/seleção ou surgir possível duplicata antes do commit: revalidar e confirmar nova versão | HTTP + concorrência | Sim | Não executado | — |
| GLI-CA-068 | F2 | BAT-12, BAT-13 | Falhar na linha N/source/event/receipt/métrica: zero linhas gravadas; tudo atômico no SQLite e MySQL | Fault injection DB | Sim | Não executado | — |
| GLI-CA-069 | F2 | BAT-12, BAT-13, SEC-23 | Reenviar/confirmar lote concorrente: um batch receipt, N registros/fontes e pending por dia sem duplicação | MySQL + HTTP | Sim | Não executado | — |
| GLI-CA-070 | F2 | BAT-14, BAT-15, UX-01 | Templates XLSX/CSV nos três idiomas, instrução e exemplo fictício: round trip válido, sem formula injection/dados de usuários | Parser + download + E2E | Sim | Não executado | — |
| GLI-CA-071 | F2 | PRV-01 a PRV-11 | Arquivo de lote em sucesso/falha/cancel: zero bytes/células não selecionadas em DB/disk/logs; TTL de draft e revisão cumpridos | Instrumentação | Sim | Não executado | — |
| GLI-CA-072 | F2 | UX-02, UX-08, seção 19 | Revisão de lote mobile/desktop em três locales, regressão completa F1 e revisor independente sem bloqueadores | E2E + revisão | Sim | Não executado | — |

## Evidências futuras

Criar relatórios por fase com comandos reais, versões, hardware/modelos, baseline/commit e limitações. Guardar apenas capturas e mídias sintéticas autorizadas. Não reutilizar nomes `REVISAO-FINAL.md` ou matrizes da feature 01/02 para registrar esta entrega; use a subpasta 03.

F3 não possui critérios de aceite nesta versão porque depende de nova autorização e escopo. Não marcar confirmações por voz, questionários estruturados ou análise agregada de vários pacientes como parte concluída de F1/F2.
