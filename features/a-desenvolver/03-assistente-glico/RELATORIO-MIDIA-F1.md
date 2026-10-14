# RelatÃ³rio da frente de mÃ­dia Glico F1

**ResponsÃ¡vel:** CODEX-MEDIA. **Branch:** `codex/glico-fase1`. **Escopo:** worker dedicado e ferramentas de provisÃ£o/avaliaÃ§Ã£o. **Status:** infraestrutura local avanÃ§ada; F1 de mÃ­dia continua experimental e nÃ£o aprovada.

## Implementado

- Mantido o boundary privado com HMAC sobre mÃ©todo/path/timestamp/nonce/digest, janela curta e consumo atÃ´mico de nonce via interface compartilhada. O launcher dedicado usa Redis `SET NX EX` e falha fechado se o segredo ou Redis nÃ£o estiver configurado.
- Imagem: JPEG/PNG/WebP estÃ¡tica, 3 MiB, 8 MP, normalizaÃ§Ã£o EXIF em memÃ³ria, resultados OCR limitados e PaddleOCR em processo descartÃ¡vel com deadline/cancelamento. `PADDLE_PDX_MODEL_SOURCE=LOCAL` impede busca de modelos no runtime. Sem os dois diretÃ³rios locais, retorna `capability_unavailable`.
- Ãudio: novo endpoint assinado `/internal/extract/audio`; 3 MiB, no mÃ¡ximo 60 segundos, containers WAV/WebM/Matroska/MP4, uma faixa de Ã¡udio, conversÃ£o mono/16 kHz em memÃ³ria, silÃªncio curto/rejeitado, idiomas permitidos pt/en/es, saÃ­da limitada e processo faster-whisper descartÃ¡vel com deadline/cancelamento. O modelo sÃ³ carrega de diretÃ³rio local (`local_files_only=True`). TranscriÃ§Ã£o Ã© resposta temporÃ¡ria `no-store`.
- Adicionados `Dockerfile.media`, `requirements-media.txt`, launcher privado, provisionador offline pÃ³s-download e avaliador para corpus sintÃ©tico. O container nÃ£o foi publicado nem ligado a rota pÃºblica.

## ValidaÃ§Ã£o executada

**Testes de boundary:** `python -m pytest -p no:cacheprovider tests/unit/media_worker -q` â€” **11 passed** (Python 3.12.2). Incluem assinatura/replay, limites e imagens sintÃ©ticas, WAV sintÃ©tico, duraÃ§Ã£o/silÃªncio e rota ASR com transcriber fake para contrato HTTP. Isso nÃ£o substitui inferÃªncia real OCR/ASR.

**ASR real local:** faster-whisper `small`, CPU/int8, snapshot local `Systran/faster-whisper-small` revision `536b0662742c02347bc0e980a01041f333bce120`. Foi executado `scripts/media/evaluate_asr.py` com duas falas SAPI sintÃ©ticas, sem envio de Ã¡udio Ã  rede:

| Idioma | Amostras | Idioma detectado | Valor esperado â†’ reconhecido | Acerto exato do campo valor | Tempo por request (spawn + carga + inferÃªncia) | Pico RSS observado |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| pt-BR | 1 | pt | 128 â†’ 128 | 1/1 | 26,9 s (wall 27,9 s) | 750 MiB |
| en-US | 1 | en | 128 â†’ 128 | 1/1 | 24,7 s (wall 25,0 s) | 755 MiB |
| es | 0 | â€” | â€” | nÃ£o medido | â€” | â€” |

As duas amostras foram frases sintÃ©ticas curtas (â€œMinha glicose estÃ¡ em cento e vinte e oito miligramas por decilitroâ€ e equivalente em inglÃªs). Os WAVs e manifesto sintÃ©ticos locais estÃ£o em `tmp/media-f1/`. A mÃ©trica de unidade, datas e intenÃ§Ã£o nÃ£o foi avaliada. A voz SAPI es-ES nÃ£o estÃ¡ instalada neste host. Este corpus minÃºsculo nÃ£o satisfaz os 30 Ã¡udios por idioma de GLI-MED-10.

O processo `WhisperModel` do modelo small carregado diretamente levou 6,8 s e RSS 361 MiB; com inferÃªncia direta, foram 14,7 s pt / 12,9 s en e ~397 MiB RSS. O caminho real do adapter, medido acima, inclui processo filho e import/carga a cada request e Ã© a estimativa relevante para este desenho. Os nÃºmeros sÃ£o deste host (`Acer Predator PH315-52`, Windows, CPU, 31,8 GiB RAM); nÃ£o representam produÃ§Ã£o. NÃ£o foram executados modelo medium, limite de 60 s, timeout, carga concorrente ou teste de cancelamento real.

## DependÃªncias/modelos e pendÃªncias

- `faster-whisper` 1.2.1, PyAV 18.0.0 e NumPy 2.4.4 jÃ¡ estavam instalados no ambiente de desenvolvimento global; o snapshot small jÃ¡ existia no cache do usuÃ¡rio. O venv `.venv-media` foi criado isoladamente, mas o acesso ao PyPI caiu antes da instalaÃ§Ã£o de PaddleOCR/PaddlePaddle e das dependÃªncias do manifesto. NÃ£o foram baixados modelos nem instalados pesos Paddle.
- PaddleOCR real, acerto por campo/unidade, imagens legÃ­veis/ambÃ­guas e mÃ©tricas de latÃªncia/memÃ³ria permanecem **nÃ£o executados**. O provisionador requer validaÃ§Ã£o em ambiente de mÃ­dia com rede de build habilitada; runtime deve permanecer sem egress e com diretÃ³rios locais somente leitura.
- Spanish ASR, corpus mÃ­nimo MED-10, silÃªncio/ruÃ­do/mÃºsica real, Ã¡udio longo, datas/unidades por idioma, crash/disconnect, concorrÃªncia, egress instrumentado, filesystem/APM/spool, build Docker e integraÃ§Ã£o gateway permanecem pendentes. As cotas diÃ¡rias e por conta sÃ£o responsabilidade do gateway compartilhado; este worker somente limita bytes, duraÃ§Ã£o e concorrÃªncia local.
- O launcher requer `MYGLICO_MEDIA_HMAC_SECRET`, `MYGLICO_MEDIA_REPLAY_REDIS_URL`, `PADDLE_DETECTION_MODEL_DIR`, `PADDLE_RECOGNITION_MODEL_DIR` e `FASTER_WHISPER_MODEL_DIR`. Sem replay store Redis compartilhado ou modelos locais, nÃ£o deve ser exposto. Segredos/mÃ­dia nÃ£o devem ir para logs.
- Como duas frases nÃ£o aproximam a evidÃªncia requerida, **nÃ£o habilitar OCR/ASR em produÃ§Ã£o** atÃ© executar os critÃ©rios GLI-CA-042/044/045/046/031â€“038 e demonstrar os limiares e rejeiÃ§Ã£o segura descritos na SDD/Matriz.

## Addendo â€” OCR real com PaddleOCR (2026-10-13)

Esta seÃ§Ã£o substitui a pendÃªncia anterior â€œPaddleOCR real ... nÃ£o executadoâ€. O teste foi executado no host Windows/CPU com Python 3.12, ambiente isolado `.venv-media`, `requirements-media.txt` instalado pelo PyPI e pesos gratuitos oficiais provisionados sob `tmp/media-f1/models-en/`. VersÃµes efetivamente importadas: PaddlePaddle 3.2.0, PaddleOCR 3.3.2, PaddleX 3.3.13. Modelos: `PP-OCRv5_server_det` + `en_PP-OCRv5_mobile_rec`. O provisionador valida os arquivos locais; o reconhecimento usa diretÃ³rios explÃ­citos, `PADDLE_PDX_MODEL_SOURCE=LOCAL`, `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`, `HF_HUB_OFFLINE=1` e `TRANSFORMERS_OFFLINE=1`. NÃ£o houve inferÃªncia em API/provedor externo. O endpoint de worker foi chamado com HMAC, nonce novo e digest SHA-256 por imagem; replay store da avaliaÃ§Ã£o foi local em memÃ³ria (nÃ£o Redis distribuÃ­do).

O primeiro provisionamento encontrou um defeito reproduzÃ­vel: o script tentava `create_model()` com diretÃ³rio ainda inexistente. ApÃ³s corrigir para baixar/copiar os modelos oficiais localmente, a primeira validaÃ§Ã£o falhou porque `PaddleOCR(lang="en")` exige o nome de reconhecimento `en_PP-OCRv5_mobile_rec`; o script configurava `latin_PP-OCRv5_mobile_rec` e o adapter nÃ£o passava os nomes explÃ­citos ao PaddleOCR. O provisionador e `app/media_worker/image.py` foram ajustados dentro da frente autorizada. Rodadas anteriores que terminaram em `processing_failed` com o modelo errado foram descartadas como avaliaÃ§Ã£o de acurÃ¡cia, mas ficam aqui registradas como falhas do teste/configuraÃ§Ã£o. ApÃ³s o ajuste, a avaliaÃ§Ã£o retornou 200 nas quatro imagens sob deadline diagnÃ³stico estendido.

Comando de provisionamento (a primeira tentativa falhou como descrito; a Ãºltima passou):

```powershell
$env:PADDLE_PDX_MODEL_SOURCE='BOS'
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True'
.\.venv-media\Scripts\python.exe scripts/media/provision_models.py --output tmp/media-f1/models-en --whisper small
```

Comandos do endpoint assinado com runtime local/offline:

```powershell
$env:PADDLE_PDX_MODEL_SOURCE='LOCAL'
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
.\.venv-media\Scripts\python.exe scripts/media/evaluate_ocr_real.py --images tmp/media-f1/ocr --models tmp/media-f1/models-en --deadline-seconds 20
.\.venv-media\Scripts\python.exe scripts/media/evaluate_ocr_real.py --images tmp/media-f1/ocr --models tmp/media-f1/models-en --deadline-seconds 120
```

O deadline de 20 s Ã© o valor padrÃ£o real de `ImageLimits`/worker. Com o modelo correto, as quatro chamadas ainda retornaram HTTP 504 `processing_timeout`, sem candidatos. O processo descartÃ¡vel precisa carregar Paddle/PaddleX e os pesos a cada requisiÃ§Ã£o. Assim, o perfil atual de 20 s **nÃ£o conseguiu produzir OCR utilizÃ¡vel neste host**. A rodada de 120 s Ã© somente diagnÃ³stico de acurÃ¡cia, mantendo o mesmo adapter/endpoint/HMAC e os mesmos modelos locais; nÃ£o representa latÃªncia de produÃ§Ã£o. Valores abaixo sÃ£o respostas reais da rodada diagnÃ³stica (latÃªncia inclui spawn, carga e inferÃªncia):

| Imagem | Esperado | Texto candidato do valor / confianÃ§a | Valor exato | Unidade OCR | LatÃªncia worker | Wall por request | Pico RSS observado (pai + filhos) | Pediu esclarecimento? |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | --- |
| foto1.png (Accu-Chek Active) | 106 mg/dL | `1006` / 0.6924; hora/data tambÃ©m saiu como `08:33^ 12-11` / 0.7817 | **NÃ£o** (1006) | nÃ£o reconheceu mg/dL; saiu `my/il` | 50,156 ms | 50,577 ms | 597.0 MiB | NÃ£o. NÃ£o preserva/expÃµe ambiguidade como esclarecimento; valor foi lido errado. |
| foto2.png (On Call Plus II) | 172; sem unidade visÃ­vel | `172` / 0.9932; tambÃ©m `101` / 0.9497 e hora `6:35 Pm` / 0.8053 | **Sim** (172) | nenhuma unidade candidata (correto: ausente na tela) | 35,405 ms | 35,672 ms | 744.0 MiB | NÃ£o. Deve ser esclarecida/confirmada no fluxo de produto por faltar unidade, mas worker sÃ³ entrega candidatos. |
| foto3.png (G-Tech) | 125 mg/dL | `125` / 0.9999; data `10.10`, hora `12:30` | **Sim** | `mg/dL` / 0.9145 | 27,672 ms | 27,887 ms | 632.1 MiB | NÃ£o (leitura nÃ£o ambÃ­gua neste caso). |
| foto4.png (G-Tech Free) | 107 mg/dL | `107` / 0.9731; hora `7-04`, `11:43 AM` parcialmente segmentado | **Sim** | `mg/dL` / 1.0000 | 24,953 ms | 25,159 ms | 683.3 MiB | NÃ£o (leitura nÃ£o ambÃ­gua neste caso). |

Resultado observado: valor exato em 3/4; unidade legÃ­vel em 2/3 imagens que exibem unidade. O caso mais relevante de confusÃ£o semÃ¢ntica foi foto1: dÃ­gitos de hora/data e glicemia estÃ£o no mesmo display; o worker OCR devolveu `1006` e nÃ£o solicitou esclarecimento. O caso foto2 acertou 172, mas a unidade nÃ£o estÃ¡ visÃ­vel e nÃ£o foi gerado estado de esclarecimento. O worker Ã© deliberadamente OCR de linhas e **nÃ£o contÃ©m lÃ³gica semÃ¢ntica nem resposta de clarification**; estes resultados provam que integraÃ§Ã£o clÃ­nica precisa tratar candidatos/OCR ambÃ­guos ou campo obrigatÃ³rio ausente como esclarecimento, sem escolher silenciosamente.

Amostragem de RSS via `psutil` leu pai e filhos durante os requests; valores sÃ£o picos observados, nÃ£o limite absoluto. A latÃªncia do processo isolado ficou acima de 20 s em todos os casos (e duas acima de 45 s), incompatÃ­vel com o deadline configurado. O worker nÃ£o mantÃ©m modelo aquecido; cada requisiÃ§Ã£o cria processo descartÃ¡vel e recarrega pesos. Esse desenho de isolamento/privacy tem custo perceptÃ­vel e requer revisÃ£o de deadline/arquitetura antes de habilitar.

**ConclusÃ£o:** PaddleOCR real executou offline com modelos locais; desempenho do valor foi 3/4 neste corpus minÃºsculo e falhou no caso de display mais ambÃ­guo. A configuraÃ§Ã£o padrÃ£o de 20 s expira em 4/4. A qualidade, detecÃ§Ã£o de unidade, ambiguidade, OCR em outras cÃ¢meras e latÃªncia ainda nÃ£o satisfazem critÃ©rios de liberaÃ§Ã£o. As quatro imagens, embora fornecidas para avaliaÃ§Ã£o, nÃ£o constituem corpus suficiente para GLI-CA-042. NÃ£o habilitar OCR para usuÃ¡rios atÃ© resolver deadline, unidade/ambiguidade e ampliar corpus de avaliaÃ§Ã£o.

## Addendo â€” ASR espanhol com Piper local e faster-whisper (2026-10-13)

ApÃ³s o marco `DONE-OCR`, foi instalado Piper separado do runtime de mÃ­dia: `.venv-tts`, `piper-tts 1.8.0`, `huggingface-hub 2.2.0`. A voz Piper `es_ES-davefx-medium` foi baixada uma vez do repositÃ³rio gratuito `rhasspy/piper-voices` para `tmp/media-f1/voices/`; SHA-256 do ONNX: `6658b03b1a6c316ee4c265a9896abc1393353c2d9e1bca7d66c2c442e222a917`. Foram gerados 10 WAVs mono/22,050 Hz em `tmp/media-f1/asr-es/`, incluindo os manifestos. O Piper foi usado apenas para sintetizar exemplos de avaliaÃ§Ã£o.

ASR: `faster-whisper 1.2.0`, modelo `small` provisionado localmente por `scripts/media/provision_models.py`, CPU/int8 e `local_files_only=True`. SHA-256 de `model.bin`: `3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671`. ExecuÃ§Ã£o com `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, modelo em diretÃ³rio local e sem serviÃ§o/API externa. `scripts/media/evaluate_asr.py` chamou `FasterWhisperTranscriber.transcribe_async` real por amostra. A extraÃ§Ã£o numÃ©rica/unidade e a recomendaÃ§Ã£o de revisÃ£o sÃ£o cÃ¡lculos do evaluator sobre a transcriÃ§Ã£o transitÃ³ria; o adapter real sÃ³ retorna texto, idioma, tempo e engine. Ele prÃ³prio nÃ£o reconhece glicemia, unidade, data ou hora e nÃ£o tem resposta estruturada para pedir esclarecimento. NÃ£o foi armazenado texto de transcriÃ§Ã£o no relatÃ³rio; o JSON sintÃ©tico temporÃ¡rio guarda apenas campos avaliados e SHA-256 do texto.

Comandos executados:

```powershell
.\.venv-tts\Scripts\python.exe -m pip install piper-tts huggingface-hub
.\.venv-tts\Scripts\hf.exe download rhasspy/piper-voices es/es_ES/davefx/medium/es_ES-davefx-medium.onnx es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json --local-dir tmp/media-f1/voices/es_ES-davefx-medium
.\.venv-tts\Scripts\python.exe scripts/media/synthesize_piper_es.py --model tmp/media-f1/voices/es_ES-davefx-medium/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx --config tmp/media-f1/voices/es_ES-davefx-medium/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json --output tmp/media-f1/asr-es
$env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'
.\.venv-media\Scripts\python.exe scripts/media/evaluate_asr.py --model-dir tmp/media-f1/models-en/whisper --manifest tmp/media-f1/asr-es/manifest.json --output tmp/media-f1/asr-es/results.json
```

Resultados reais da execuÃ§Ã£o completa (latÃªncia do adapter inclui spawn/carga/inferÃªncia; RSS Ã© pico observado pelo evaluator somando pai/filhos; `â€”` representa campo nÃ£o devolvido por erro/ausÃªncia):

| Caso | Esperado | Idioma | Valor(s) reconhecido(s) pelo evaluator | Unidade detectada | AÃ§Ã£o recomendada pelo evaluator / aÃ§Ã£o esperada | LatÃªncia | Pico RSS |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| 01 valor 128 | 128 mg/dL | es | 128 exato | sim | revisar / revisar | 18,764 ms | 696.0 MiB |
| 02 valor 95 | 95 mg/dL | es | candidatos 90 e 5; sem valor Ãºnico | sim | esclarecer / revisar | 20,344 ms | 693.7 MiB |
| 03 valor 250 | 250 mg/dL | es | 250 exato | **nÃ£o** | esclarecer por unidade ausente / revisar | 21,610 ms | 704.5 MiB |
| 04 hoje Ã s oito e meia, 128 | 128 mg/dL | es | 128 exato apÃ³s remover expressÃ£o horÃ¡ria | sim | revisar / revisar | 19,344 ms | 724.9 MiB |
| 05 ontem Ã  noite, 95 | 95 mg/dL | es | 95 exato | **nÃ£o** | esclarecer por unidade ausente / revisar | 19,405 ms | 699.1 MiB |
| 06 valor ambÃ­guo 128 sem unidade | 128; unidade ausente | es | **228**, incorreto | nÃ£o | esclarecer / esclarecer | 20,530 ms | 714.4 MiB |
| 07 dois valores | 128 e 250; nÃ£o escolher automaticamente | es | candidatos 128 e 250 | sim | esclarecer / esclarecer | 21,125 ms | 717.9 MiB |
| 08 valor 95 sem unidade | 95; unidade ausente | es | 95 exato | nÃ£o | esclarecer / esclarecer | 20,671 ms | 735.8 MiB |
| 09 silÃªncio | nenhum | â€” | â€” | â€” | `speech_not_detected` / `no_speech` | 76 ms | 49.3 MiB |
| 10 fala nÃ£o relacionada com horÃ¡rio | rejeitar como leitura | es | encontrou `8` em â€œocho y mediaâ€ | nÃ£o | esclarecer / rejeitar | 20,828 ms | 692.1 MiB |

Resumo: o idioma foi identificado como `es` em 9/9 Ã¡udios com fala; silÃªncio foi barrado antes da inferÃªncia. O valor Ãºnico foi exato em 5/7 casos com um valor esperado (casos 02 e 06 falharam). Em fala que explicitamente disse mg/dL, a unidade apareceu em 3/5. Os dois casos sem unidade e o caso de mÃºltiplos valores resultaram em recomendaÃ§Ã£o de esclarecimento pelo evaluator; o ASR/adapter **nÃ£o pediu esclarecimento por conta prÃ³pria**, pois nÃ£o oferece esse estado. O teste de fala nÃ£o relacionada produziu o nÃºmero 8 do horÃ¡rio e teria polÃ­tica incorreta se um consumidor tratar qualquer nÃºmero transcrito como leitura. Exige classificaÃ§Ã£o determinÃ­stica de intenÃ§Ã£o e unidade no gateway antes de criar proposta.

Tempo mÃ©dio observado incluindo silÃªncio: 18.27 s; WAVs com fala ficaram entre 18.764 s e 21.610 s. Pico RSS observado em fala: 692.3â€“735.8 MiB; silÃªncio: 49.3 MiB. O adapter nÃ£o expÃµe confianÃ§a de transcriÃ§Ã£o; confianÃ§a nÃ£o medida. Embora os exemplos incluam datas/horas, este teste nÃ£o valida extraÃ§Ã£o de data/hora estruturada nem timezone. O Piper usa voz sintÃ©tica em frases curtas e limpas; isso **nÃ£o substitui corpus humano** com sotaques, gravaÃ§Ãµes reais, ruÃ­do, microfones e variaÃ§Ã£o natural. Dez amostras tambÃ©m nÃ£o satisfazem o critÃ©rio mÃ­nimo da matriz. NÃ£o habilitar ASR com base neste resultado.

## Rodada de correÃ§Ã£o â€” worker persistente, limites de plausibilidade e mediÃ§Ã£o (2026-10-13)

O OCR e o Whisper agora usam um filho persistente isolado por instÃ¢ncia/capacidade. O modelo Ã© carregado uma vez no startup do serviÃ§o e mantido aquecido entre requests; chamadas diretas do adapter iniciam e aquecem o filho no primeiro uso. Requests na mesma capacidade sÃ£o serializados. A configuraÃ§Ã£o padrÃ£o recicla apÃ³s 25 requests ou RSS acima de `GLICO_MEDIA_MAX_RSS_BYTES` (padrÃ£o 1.5 GiB); falha de processamento, timeout e cancelamento encerram o filho. Startup tem deadline separado de 120 s; deadline de inferÃªncia permanece 20 s para OCR e 45 s para ASR. `aclose()` e lifespan do app encerram os filhos no shutdown. Durante a carga fria o serviÃ§o ainda nÃ£o estÃ¡ pronto, portanto a plataforma precisa considerar esse tempo no readiness/startup do worker.

O JSON preserva os campos antigos (`candidates` OCR e `language`/`text` ASR) e acrescenta `assessment` em ambos, compatÃ­vel com consumidores que ignoram campos desconhecidos. Novos campos: `status` (`review_required` ou `needs_clarification`), `needs_clarification`, `clarification_reasons`, `candidate_value_mg_dl` (nulo se a regra falhar), `candidate_confidence`, `physiological_range_mg_dl` e `confidence_threshold`; ASR tambÃ©m expÃµe `confidence`. O backend deve ler `assessment.needs_clarification` e impedir criaÃ§Ã£o de proposta/leitura quando verdadeiro. `review_required` continua sendo apenas candidato sujeito Ã  confirmaÃ§Ã£o humana, nÃ£o uma mediÃ§Ã£o confirmada. Valores padrÃ£o configurÃ¡veis: `GLICO_MEDIA_MIN_GLUCOSE_MG_DL=20`, `GLICO_MEDIA_MAX_GLUCOSE_MG_DL=600`, `GLICO_MEDIA_MIN_OCR_CONFIDENCE=0.75`, `GLICO_MEDIA_MIN_ASR_CONFIDENCE=0.75`; o RSS configurÃ¡vel Ã© `GLICO_MEDIA_MAX_RSS_BYTES`. A confianÃ§a ASR Ã© `exp(avg_logprob)` mÃ©dia dos segmentos do Whisper, proxy nÃ£o calibrado clinicamente.

### ReavaliaÃ§Ã£o OCR assinada

Comando executado apÃ³s provisionamento, em runtime offline e pelo endpoint HMAC local (`TestClient`, replay store local em memÃ³ria):

```powershell
$env:PADDLE_PDX_MODEL_SOURCE='LOCAL'; $env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True'; $env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'
.\.venv-media\Scripts\python.exe scripts/media/evaluate_ocr_real.py --images tmp/media-f1/ocr --models tmp/media-f1/models-en --deadline-seconds 20
```

As fotos foram cada uma executadas em um filho frio (startup incluÃ­do) e duas vezes no mesmo processo aquecido. O sampler acompanhou RSS do pai e dos filhos a cada 50 ms. Resultado da execuÃ§Ã£o real: todas as respostas HTTP 200; 3/4 valores exatos. O worker solicitou esclarecimento nos dois casos que nÃ£o podem produzir valor seguro.

| Foto | Esperado | SaÃ­da OCR e confianÃ§a | Candidato esperado exato | Unidade | Esclarecimento | Frio: startup + request | Requests aquecidos | Pico RSS observado |
| --- | ---: | --- | --- | --- | --- | ---: | ---: | ---: |
| foto1.png | 106 | `1006` / 0.6924; data/hora tambÃ©m confundidas | nÃ£o (`1006`) | ausente | sim: fora de faixa, confianÃ§a baixa, unidade ausente | 20,973 + 3,274 = 24,247 ms | 1,429; 1,386 ms | 626.2 MiB |
| foto2.png | 172 | `101` / 0.9497 e `172` / 0.9932 | sim (172) | ausente na foto | sim: mÃºltiplos candidatos e unidade ausente | 21,945 + 5,947 = 27,892 ms | 3,394; 3,475 ms | 905.9 MiB |
| foto3.png | 125 | `125` / 0.9999 | sim | `mg/dL` | nÃ£o; candidato marcado para revisÃ£o humana | 22,421 + 4,258 = 26,679 ms | 2,564; 2,265 ms | 709.2 MiB |
| foto4.png | 107 | `107` / 0.9731 | sim | `mg/dL` | nÃ£o; candidato marcado para revisÃ£o humana | 20,857 + 4,625 = 25,482 ms | 2,371; 2,687 ms | 720.5 MiB |

Cold: n=4, p50 **26,679 ms**, p95 **27,892 ms** (inclui carga/readiness e request frio). Warm: n=8, p50 **2,564 ms**, p95 **3,475 ms** (requests medidos na borda HTTP assinada). Com readiness fora do request, todas as chamadas OCR quentes ficaram abaixo do deadline de 20 s neste host. Pico de RSS amostrado a cada 50 ms: **626.2â€“905.9 MiB**. O p95 usa amostra pequena e o mÃ¡ximo observado como extremo; nÃ£o Ã© estimativa de produÃ§Ã£o.

### ReavaliaÃ§Ã£o ASR espanhol

Comando executado novamente com Whisper `small`, WAVs Piper locais, modelo local e modo offline. Para cada arquivo com fala, o avaliador mediu uma carga + inferÃªncia fria e uma inferÃªncia aquecida no mesmo filho. O silÃªncio Ã© rejeitado pelo decoder antes de inferÃªncia Whisper. Valores abaixo preservam as extraÃ§Ãµes erradas; o campo `worker assessment` usa o parser conservador real do endpoint, que aceita somente tokens numÃ©ricos escritos em dÃ­gitos. NÃºmeros falados por extenso ainda nÃ£o sÃ£o interpretados como candidato confiÃ¡vel e pedem esclarecimento.

```powershell
$env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'
.\.venv-media\Scripts\python.exe scripts/media/evaluate_asr.py --model-dir tmp/media-f1/models-en/whisper --manifest tmp/media-f1/asr-es/manifest.json --output tmp/media-f1/asr-es/results-media2.json
```

Cold: n=9 Ã¡udios com fala, p50 **19,512 ms**, p95 **28,692 ms** (startup + primeira inferÃªncia). Warm: n=9, p50 **11,811 ms**, p95 **18,251 ms**. Pico RSS observado durante inferÃªncia: **623.1â€“627.3 MiB** nos Ã¡udios com fala. O silÃªncio foi rejeitado antes da inferÃªncia Whisper; os percentis excluem este caso. Esses p95s sÃ£o de apenas nove casos e nÃ£o substituem benchmark de carga.

| Caso | Esperado | Candidatos encontrados pelo avaliador / resultado | Unidade | Conf. | Worker pede esclarecimento? | Frio total | Warm | Pico RSS |
| --- | --- | --- | --- | ---: | --- | ---: | ---: | ---: |
| 01 valor 128 | 128 mg/dL | avaliador `[128]` / 128 exato; worker `[128]` | sim | 0.698 | sim: confianÃ§a abaixo de 0.75 | 19,512 ms | 11,985 ms | 624.0 MiB |
| 02 valor 95 | 95 mg/dL | avaliador `[90, 5]` / sem valor Ãºnico; worker `[90]` | sim | 0.748 | sim: confianÃ§a abaixo de 0.75; valor esperado continua errado | 19,736 ms | 11,104 ms | 625.9 MiB |
| 03 valor 250 | 250 mg/dL | avaliador `[250]` / 250 exato; worker `[250]` | nÃ£o | 0.700 | sim: unidade ausente e confianÃ§a baixa | 19,725 ms | 11,811 ms | 625.0 MiB |
| 04 hoy a las ocho y media, 128 | 128 mg/dL | avaliador `[128]` / 128 exato; worker `[128]` | sim | 0.745 | sim: confianÃ§a abaixo de 0.75 | 19,277 ms | 10,999 ms | 623.4 MiB |
| 05 ayer por la noche, 95 | 95 mg/dL | avaliador `[95]` / 95 exato; worker `[95]` | nÃ£o | 0.795 | sim: unidade ausente | 18,350 ms | 11,597 ms | 625.4 MiB |
| 06 valor ambÃ­guo 128 sem unidade | 128 | avaliador/worker `[228]` / **228 incorreto** | nÃ£o | 0.412 | sim: confianÃ§a baixa e unidade ausente | 19,287 ms | 11,138 ms | 623.1 MiB |
| 07 nÃºmeros mÃºltiplos | 128 e 250 | avaliador/worker `[128, 250]` / sem valor Ãºnico | sim | 0.681 | sim: mÃºltiplos candidatos e confianÃ§a baixa | 18,922 ms | 12,993 ms | 627.3 MiB |
| 08 valor 95 sem unidade | 95 | avaliador/worker `[95]` / 95 reconhecido, sem unidade | nÃ£o | 0.722 | sim: unidade ausente e confianÃ§a baixa | 22,391 ms | 18,251 ms | 625.4 MiB |
| 09 silÃªncio | sem fala | `speech_not_detected` | nÃ£o aplicÃ¡vel | â€” | rejeitado, sem pedido de esclarecimento | â€” | â€” | 63.4 MiB observado no processo pai; amostragem de RSS filho nÃ£o foi coletada no caminho barrado antes da inferÃªncia |
| 10 fala nÃ£o relacionada | rejeitar | avaliador `[8]`; worker encontrou `[30]` no trecho de horÃ¡rio | nÃ£o | 0.725 | sim: unidade ausente e confianÃ§a baixa; nÃ£o rejeita intenÃ§Ã£o alheia | 28,692 ms | 15,983 ms | 626.0 MiB |

O idioma foi `es` em 9/9 com fala. O avaliador extraiu exatamente o valor em 5/7 casos de valor Ãºnico; o caso 02 virou dois candidatos e o caso 06 inventou 228. Unidade apareceu em 3/5 frases cuja verdade de referÃªncia incluÃ­a unidade. Com o limiar final de 0.75, o worker pediu esclarecimento nos nove casos com fala; o silÃªncio foi rejeitado. O caso 10 ainda Ã© classificado como esclarecimento em vez de rejeiÃ§Ã£o semÃ¢ntica, e o worker capturou `30` do horÃ¡rio como candidato adicional; isso Ã© uma limitaÃ§Ã£o observada, nÃ£o mascarada. O Piper Ã© sintÃ©tico e **nÃ£o substitui corpus humano**.

O teste unitÃ¡rio final executado foi `python -m pytest -p no:cacheprovider tests/unit/media_worker -q`: **16 passed**. Cobriu os dois lados da faixa fisiolÃ³gica e estouro como 1006, confianÃ§a abaixo do limiar/indisponÃ­vel, candidatos concorrentes, unidade ausente, contrato HTTP e erros/limites anteriores. O avaliador manteve erros do OCR/ASR e nÃ£o alterou expected-values para obter acerto.


