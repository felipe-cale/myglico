# Relatório da frente de mídia Glico (parcial)

**Escopo desta rodada:** F1.1, boundary privado para OCR de foto individual.  
**Responsável nesta sessão:** Codex, cobrindo provisoriamente a função prevista para Antigravity. Isso não representa trabalho de Antigravity.  
**Branch observada:** `codex/glico-fase1`.  
**Estado:** implementação inicial do boundary e adaptador concluída; integração com gateway, provisionamento e validação de modelo real pendentes. Este relatório não declara F1 aprovada.

## Arquivos desta frente

- `app/media_worker/auth.py`: assinatura HMAC canônica sobre método, caminho, timestamp, nonce e digest do corpo; replay store é uma interface compartilhada obrigatória e indisponibilidade falha fechado.
- `app/media_worker/service.py`: app ASGI privado criado por factory, endpoint único de imagem, corpo binário contado em streaming, `application/octet-stream`, correlation ID aleatório, autenticação antes da inferência, resposta `no-store` e limite de concorrência por processo.
- `app/media_worker/image.py`: validação de JPEG/PNG/WebP estático, limite de bytes e pixels, normalização EXIF em memória, PaddleOCR lazy, saída limitada e inferência em processo descartável com deadline e encerramento em cancelamento.
- `tests/unit/media_worker/`: testes sintéticos para assinatura/replay, request, limites de imagem e normalização Paddle 2.x/3.x.

O worker não consulta banco clínico e o contrato não lhe envia cookie, conta, paciente, papel ou ciclo de vínculo. Ele recebe somente o corpo da imagem e um correlation ID aleatório. O gateway ainda precisa autorizar antes de enviar e revalidar a sessão/contexto depois da resposta. O módulo não escolhe valor clínico nem confirma proposta.

## Validação executada

Comando: `python -m pytest -p no:cacheprovider tests/unit/media_worker -q`  
Resultado: **9 passed**. Ambiente: Python 3.12; Pillow 12.2.0. As imagens são geradas em memória durante os testes. O extractor do teste de endpoint é um fake deliberado para testar protocolo, limites e resposta.

Verificação de disponibilidade deste ambiente: `paddleocr` e `paddle` não estão instalados; não há diretórios locais de modelos provisionados. Logo, **PaddleOCR real, corpus, qualidade por campo, latência do modelo e memória do modelo não foram executados**. Não há hashes/licenças/versões de modelo a reportar. Nenhum dado ou modelo foi baixado.

## Provisionamento exigido antes de habilitar

1. Criar imagem/ambiente de worker separado do runtime Vercel/backend e fixar versões compatíveis de Python, PaddlePaddle e PaddleOCR; registrar licença, hashes/digests de pacotes e modelos.
2. Provisionar modelos de detecção e reconhecimento em diretórios locais somente leitura e configurar `text_detection_model_dir` e `text_recognition_model_dir`. O adapter exige ambos e não deixa PaddleOCR baixar modelos durante request.
3. Bloquear egress de runtime do worker e manter o bind/listener acessível apenas pela rede privada. Segredos HMAC entram pelo secret store; rotação e replay store compartilhado são responsabilidade do deploy/gateway.
4. Configurar prazo do worker em até 20 s, timeout do gateway em até 25 s, limites de memória/CPU e supervisão de processos. `max_inflight` é limite local por processo, não substitui reserva/quota compartilhada por conta/global no gateway.
5. Executar os gates GLI-CA-031 a 043 aplicáveis e avaliação GLI-CA-042 com corpus sintético: mínimo de 30 fotos legíveis variadas, 15 ambíguas/ruins; relatório de acerto valor+unidade, cobertura, rejeições, latência fria/quente, memória e falhas. Exigir >=95% de acerto exato valor+unidade em legíveis e rejeição segura dos casos ambíguos para liberar OCR.

## Limitações e integração pendentes

- Nenhum manifest, config de deploy, gateway, rota, contrato ou quota compartilhada foi alterado nesta frente. O coordenador deve ligar o cliente de worker ao endpoint e fornecer replay store atômico (Redis/DB compartilhado) e reserva de cota antes de expor a capacidade.
- `create_media_app` recebe secret/replay store por injeção e não publica docs/OpenAPI. O deployment precisa garantir rede privada e não montar este app na superfície pública.
- Testes reais de cancelamento/desconexão, análise de spool/proxy/APM, restrição de egress, carga e isolamento do container ainda não foram executados.
- faster-whisper não foi implementado nesta entrega parcial; apesar de o pacote aparecer instalado no ambiente, modelo/corpus pt-BR/en-US/es, hard deadline e descarte ainda precisam de uma frente explícita.
- Sem o modelo Paddle local e o conjunto de avaliação, a capacidade deve permanecer desabilitada. Falhas retornam erro controlado; não há fallback externo.
