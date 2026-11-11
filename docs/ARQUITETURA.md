# Arquitetura do Polar Sentinel

Este documento descreve a organizacao do codigo e o fluxo de dados, para quem
vai ler, estender ou integrar o harness.

## Fluxo de dados

```
documento bruto (PDF, DOCX, OCR, web)
   |
   v
[L1] sanitizacao deterministica  ->  texto limpo + trilha de auditoria
   |
   v
[L0] filtro de privacidade        ->  PII redigida antes do modelo
   |
   v
[L2] deteccao adversarial         ->  score de risco + razoes
   |
   v
[L3] proveniencia                 ->  origem e integridade dos trechos
   |
   v
[L4] governanca da saida          ->  least agency + aprovacao humana
   |
   v
[L5] observabilidade              ->  trilha auditavel por evento
```

O orquestrador encadeia L0, L1 e L2 e consolida o resultado. O pipeline adiciona
o portao L4 e, opcionalmente, chama um modelo via adapter quando nao ha gate
humano pendente.

## Modulos

### reference

Implementacoes de referencia, limpas e sem dependencias externas.

* `sanitizer.py`, L1. Remove invisiveis, controles bidirecionais, tag
  characters, seletores de variacao, comentarios HTML e ANSI, normaliza para NFC
  e devolve a trilha de auditoria.
* `privacy_filter.py`, L0. Redige dados pessoais. Usa regex brasileira por
  padrao e, de forma opcional, um modelo de classificacao de tokens. A
  reconstrucao do texto resolve sobreposicoes e preserva offsets.
* `injection_detector.py`, L2. Detector explicavel que devolve uma tupla com
  score e razoes. Cobre override canonico, escape de delimitador, homoglifos,
  base64, uso indevido de ferramenta, estrutura ativa de PDF e aparencia de
  decisao.
* `provenance.py`, L3. Verifica origem e integridade de trechos contra fontes
  confiaveis e hashes.
* `hitl_approval.py`, L4. Portao de aprovacao humana com estado real, uso unico,
  janela de validade e conferencia de hash.

### harness

* `orchestration.py`. O `DefenseOrchestrator` encadeia camadas, normaliza
  retornos heterogeneos e consolida score, bloqueio e trilha.
* `sentinel_pipeline.py`. O `SentinelPipeline` aplica o orquestrador, decide
  sobre o gate humano e integra qualquer adapter.
* `adapters.py`. Interface de modelo. Inclui um mock para testes e um adapter
  compativel com APIs no estilo OpenAI.
* `test_judicial_safety.py`. Cenarios de ponta a ponta.

### attacks

* `corpus.py`. Catalogo estruturado de vetores, fonte unica de verdade.
* `generate_test_pdfs.py`. Gera PDFs de teste a partir do corpus.
* `samples/`. PDFs gerados, com um indice.

### benchmarks

* `agent_safety_bench.py`. Mede deteccao e falsos positivos sobre o corpus.

### demo

* `sentinel_test_page.py`. Laboratorio visual em Streamlit.

### tests

* `test_corpus_defense.py`. Garante que todo ataque e barrado e todo benigno
  passa, e valida os PDFs gerados.

## Decisoes de projeto

* Falhar com seguranca. Em duvida, segregar e encaminhar a revisao, nunca deixar
  passar.
* Nada e descartado em silencio. Toda remocao gera trilha.
* Defesa em profundidade. Varias camadas votam, porque nenhuma defesa isolada e
  suficiente.
* Agnostico de modelo. Qualquer API entra por um adapter.
* Sem dados reais no repositorio. Todos os exemplos usam dados ficticios.
