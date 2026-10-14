# Assistente Glico

Pacote de especificação para implementar o assistente MyGlico de pacientes e médicos em fases, com revisão humana e endpoints autenticados.

**Versão:** 1.0, 13/10/2026.  
**Estado (14/10/2026):** F1 implementada; aceite NO-GO (ver [REVISAO-FINAL-F1-R2.md](REVISAO-FINAL-F1-R2.md)). Pendentes: corpus humano de OCR/ASR, egress/privacidade instrumentados e hospedagem alvo; mídia desligada por padrão.

| Arquivo | Finalidade |
| --- | --- |
| [SDD](MyGlico_SDD_Assistente_Glico.md) | Requisitos, fases, arquitetura, segurança, privacidade, contratos, dados e validação |
| [Matriz de aceite](MATRIZ-ACEITE.md) | 72 critérios com status inicial Não executado |
| [Prompt para o Orca](PROMPT-ORCA.md) | Coordenação de vários agentes, ownership, dependências, integração e revisão independente |

A fase 1 entrega fundação segura, foto individual com PaddleOCR, texto, FAQ, consultas, áudio multilíngue com faster-whisper e colaboração. A fase 2 acrescenta XLSX/CSV, templates, foto com múltiplas leituras e importação em lote. Os controles de segurança não são adiados para F2.

Para entregar ao Orca, disponibilizar os quatro arquivos e usar `PROMPT-ORCA.md` como instrução inicial. A implementação de F2 depende de liberação explícita posterior. Os documentos não iniciam agentes nem autorizam implantação ou serviços pagos.
