# Estudo: do áudio (Whisper) ao número — estado da arte e auditoria do que implementamos

**Data:** 14/10/2026 · **Escopo:** qualquer domínio que transforme fala em números com Whisper, para conferir se a nossa solução segue boas práticas ou acumula gambiarras e débito técnico.

## 1. Método e limites

- Busca na web (modo aprofundado) em seis frentes: normalização inversa de texto (ITN), erros de Whisper em dígitos, bibliotecas de números por extenso, `initial_prompt`/`hotwords`, assistentes de voz de código aberto, e confirmação de valores críticos.
- Leitura das **fontes primárias** para as afirmações que sustentam recomendações (páginas das bibliotecas e o resumo do artigo de dígitos). O que veio só de resumo de busca está marcado como *secundário*.
- **Limites:** a busca é restrita aos EUA e privilegia blogs; **não encontrei nenhum repositório público de glicemia (nem de outro domínio de saúde) por voz com Whisper** que tratasse números de forma documentada. O que existe é a literatura de ITN e issues de projetos gerais. Por isso o estudo compara com *práticas*, não com um projeto equivalente.
- **Correções ao que a busca retornou:** (1) um resumo atribuía ao README do WhisperX a normalização de números por extenso; o README **não** diz isso (só avisa que numerais como "2014." ficam sem marcação de tempo). Não usei a afirmação. (2) A página do PubMed sobre erros de ditado clínico não abriu; os números dela ficam como secundários.

## 2. O que a prática encontrada recomenda

| # | Prática | Evidência (fonte) |
|---|---|---|
| 1 | **ITN é uma etapa separada, depois do ASR.** A saída do Whisper alterna entre dígitos e palavras e o usuário não controla; o normalizador do próprio Whisper existe para *comparar* transcrições, não para exibir. | [TypeWhisper #110](https://github.com/TypeWhisper/typewhisper-mac/issues/110), [speechbox #24](https://github.com/huggingface/speechbox/issues/24), [normalizadores do Whisper](https://openai-whisper.mintlify.app/api/normalizers), [artigo do Whisper](https://cdn.openai.com/papers/whisper.pdf) |
| 2 | **Regras determinísticas (regex/WFST) para o caso geral; modelos neurais só quando há ambiguidade.** Regras são auditáveis; taggers neurais (ex.: Thutmose) dão rastreabilidade palavra a palavra. | [NeMo ITN](https://github.com/NVIDIA/NeMo-text-processing), [Thutmose Tagger](https://arxiv.org/pdf/2208.00064), [Apple: ITN como rotulagem](https://machinelearning.apple.com/research/inverse-text-normal) |
| 3 | **Não escrever o dicionário de números à mão: usar biblioteca mantida.** `text2num` (MIT; pt-BR e pt-PT, es, en; modo relaxado por padrão; mantém sequências de dígitos separadas por decisão de projeto). `ovos-number-parser` (Apache-2.0; pt/es/en com extração e conversão). | [text2num](https://github.com/allo-media/text2num), [ovos-number-parser](https://github.com/OpenVoiceOS/ovos-number-parser) |
| 4 | **Dígitos são um ponto fraco conhecido do Whisper.** Um micro-modelo específico para dígitos relatou **1,8% de erro contra 5,8% do Whisper** em reconhecimento de dígitos. Mitigações: modelo especializado, viés de vocabulário, correção por LLM restrita ao N-best. | [artigo de dígitos (confirmado)](https://arxiv.org/abs/2402.01931), [WhisperBiasing](https://github.com/briansidp/whisperbiasing), [correção por LLM](https://arxiv.org/pdf/2409.09554) |
| 5 | **Não contar com `initial_prompt`/`hotwords` para números.** Limite de ~224 tokens, atuam sobretudo na primeira janela, e há relatos de eco do prompt e alucinação. | [issue do listen-to-me](https://github.com/fo0/listen-to-me/issues/293), [openai/whisper #1477](https://github.com/openai/whisper/discussions/1477), [whisper.cpp #2286](https://github.com/ggml-org/whisper.cpp/discussions/2286) *(secundário)* |
| 6 | **Para valores críticos, revisão humana mostrando valor e unidade juntos.** Em ditado clínico, erros sobrevivem mesmo à edição; a pontuação de confiança sozinha não basta. | [ED/ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1386505616300909), [PubMed](https://pubmed.ncbi.nlm.nih.gov/30370424/), [guia de ditado](https://www.veroscribe.com/blog/physician-dictation-guide) *(secundário)* |
| 7 | **Operação:** VAD para áudio curto e para evitar texto inventado no silêncio; `int8` em CPU; idioma forçado em vez de detecção. | [guias de faster-whisper](https://knightli.com/en/2026/05/01/faster-whisper-speech-to-text/), [VAD](https://theneuralbase.com/whisper/learn/intermediate/vad-filter-in-faster-whisper/) *(secundário; o ganho do idioma forçado **medimos nós**: 10 s → 5 s)* |

**Descartado com base na evidência:** NeMo ITN. É Apache-2.0 e robusto, mas depende de Pynini/OpenFst e a página oficial informa que a instalação por `pip` não é suportada em Windows/macOS; não confirmei cobertura de pt/es na página.

## 3. Nossa solução contra essas práticas

| Prática | Situação | Observação |
|---|---|---|
| 1 ITN separada do ASR | ✅ | `spoken.py` roda depois do Whisper; o gateway nunca recebe texto cru. |
| 2 Regras determinísticas, auditáveis | ✅ | Tudo é regra; cada reparo tem `name` e `why`. Sem LLM no caminho do número. |
| 3 Biblioteca mantida para o caso geral | ✅ *(desde hoje)* | Dicionários próprios (≈100 linhas, 3 idiomas) trocados por `text2num`. Fica só a camada de domínio. |
| 4 Fraqueza em dígitos | ⚠️ parcial | Mitigamos no pós-processamento ("meia", "6 a 7", "0.67"). Não usamos modelo de dígitos nem N-best. |
| 5 Sem prompt/hotwords | ✅ | Testamos e **rejeitamos com medição**: "190" virou "1,90" e "90", "de l.75". |
| 6 Revisão humana de valor+unidade | ✅ | Cartão obrigatório, transcrição exibida, unidade visível e editável, aviso de "baixa confiança". |
| 7 VAD, idioma forçado, int8 | ✅ | `vad_filter`, dica de idioma da interface (com retentativa automática se confiança baixa), `int8`. |
| Confiança no número, não na frase | ✅ | Probabilidade por palavra (`word_timestamps`) só dos tokens com dígito. |

## 4. Débitos técnicos e riscos reais (sem maquiagem)

1. **Corpus pequeno e de um só falante.** Os reparos de domínio ("meia sete" → 67, "6 a 7", "0.67") nasceram de **20 gravações de uma pessoa**. Cada um tem teste e justificativa, mas o risco de generalizar mal (outro sotaque, outro microfone) é real. *Mitigação:* o script `evaluate_real_audio.py` e o modo de captura de desenvolvimento permitem crescer o corpus. *Falta:* um corpus **consentido e versionável** (os áudios reais hoje ficam fora do git por serem voz pessoal) e uma métrica de **erro de valor** (não só WER) rodando em CI.
2. **Pisos de confiança abaixo do SDD.** O SDD exigia 0,75; hoje o áudio usa 0,5 e propõe com aviso entre 0,25 e 0,5. É decisão de produto, autorizada, mas **sem taxa de falso-aceite medida**. *Falta:* medir em corpus maior antes de levar a produção.
3. **Dependência pequena.** `text2num` tem poucas estrelas e atividade não confirmada por mim (a página não mostra a data da última release). *Mitigação:* o uso está atrás de `alpha2digit`, num único ponto; `ovos-number-parser` (Apache-2.0) é substituto direto; fixei a versão (`3.1.0`).
4. **Inferência de unidade.** A faixa 20–33 sem decimal é lida como mg/dL (padrão brasileiro); decimal ou < 20 vira mmol/L. É regra de domínio documentada em `reading.py`, protegida pela revisão do usuário, mas é suposição.
5. **Modelo.** `small` em CPU (~5 s). Acerta o corpus, mas é compromisso: `base` leu "175" no lugar de "75". Há margem de ganho em precisão com modelo maior ou GPU.
6. **Atalho legítimo, mas que merece nome:** a política de "propor com aviso" quando a confiança é baixa troca *rejeição silenciosa* por *proposta revisável*. Está no código como regra única (`assess_transcript`), não espalhada.

**O que era gambiarra e foi corrigido hoje:** regex e `if` espalhados em `service.py` (camada HTTP), dicionário próprio de números nos três idiomas, e duplicação da regra de leitura entre o worker e o script de avaliação (agora ambos chamam `assess_transcript`).

## 5. Recomendações (em ordem de retorno)

1. **Corpus de regressão consentido** (outros falantes, ruído, números altos/baixos, por extenso, decimais, en/es) + **métrica de erro de valor** em CI. É o que mais reduz o risco do item 1 e do item 2.
2. **Medir falso-aceite** dos pisos 0,5/0,25 nesse corpus e então decidir o piso de produção.
3. Avaliar **modelo de ASR maior** (ou GPU) com o mesmo corpus; comparar com um micro-modelo de dígitos *só se* o produto passar a depender de sequências longas.
4. Manter `text2num` atrás de uma função única; registrar `ovos-number-parser` como plano B.
5. Opcional: correção por LLM **restrita ao texto** (já temos o Gemini para texto), nunca ao áudio, mantendo a política de não enviar mídia a terceiros.

## 6. Onde está no código

`app/media_worker/spoken.py` (números e unidades, tabelas `RUN_WORDS`/`REPAIRS`/`UNITS`) · `reading.py` (tabela `UNIT_RULES`, `assess_transcript`) · `photo.py` · `devcapture.py` · `service.py` (só HTTP) · `scripts/media/evaluate_real_audio.py` e `evaluate_real_photos.py`.
