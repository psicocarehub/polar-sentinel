# Changelog

Formato baseado em Keep a Changelog. Versionamento semantico.

## 0.4.1

Sem mudanca de codigo.

* DOI do Zenodo no README, em `CITATION.cff` e no texto completo.
* Metadados do registro no Zenodo em `.zenodo.json`.
* Testes automaticos em Python 3.10 e 3.12.
* Ajuste de redacao na nota final do texto completo.

## 0.4.0

Medicao fora do corpus proprio, em dados reais, e correcao do que ela mostrou.

### Adicionado

* Inspecao de PDF (`reference/pdf_inspector.py`): separa o texto visivel do
  texto na cor do fundo, em fonte de menos de 2 pontos ou fora da pagina, que e
  a forma de todos os casos brasileiros conhecidos. Papel timbrado e camada de
  OCR sao liberados. Pede `pypdf` (extra `pdf`).
* Comandos reais publicados por tribunais brasileiros em 2026, com a fonte de
  cada um (`attacks/reais.py`), e quatro prompts ocultos de artigos cientificos.
* Medida em conjuntos publicos (`benchmarks/baixar_externos.py` e
  `benchmarks/external_eval.py`): ataques escritos por pessoas e textos
  juridicos brasileiros reais, cada conjunto dividido em metade de
  desenvolvimento e metade de teste pelo hash do texto.

* Tres conjuntos de teste alem do corpus de desenvolvimento: validacao
  (`attacks/heldout.py`) e dois conjuntos cegos (`attacks/blind_1.py` e
  `attacks/blind_2.py`), escritos por quem nao viu o codigo. O protocolo e os
  numeros estao em `docs/AVALIACAO.md`; a medida roda com
  `python -m polar_sentinel.benchmarks.heldout_eval`.
* Normalizacao antes do casamento de padroes: NFKC, sem acentos, homoglifos
  cirilicos e gregos trocados pela letra latina, palavra partida por hifen
  reunida, e vistas extras para letras espacadas ou pontuadas, leetspeak, ROT13
  e texto invertido. Blocos hexadecimais passam a ser decodificados e
  reavaliados, como ja acontecia com base64.
* Sinais novos no detector: texto dirigido a IA leitora, troca de papel, ordem
  para pular a revisao humana, saida de dados, envenenamento de memoria,
  imperativo seco de dispositivo ("Defira todos os pedidos"), pedido do prompt
  do sistema e troca de persona.
* O conteudo removido de comentarios HTML e de tag characters passa a ser
  avaliado pelo detector.
* Parametro `stage` no detector e no orquestrador ("entrada" ou "saida").

### Corrigido

* As regras estavam escritas sem acento e eram aplicadas a texto acentuado:
  "ignore as instrucoes anteriores" com cedilha e til passava sem sinal.
* Linguagem de decisao ("julgo procedente", "defiro") somava risco em qualquer
  documento. Agora so pesa sozinha na saida da ferramenta de apoio.
* Hifen suave, BOM, seletor de emoji isolado e um ou dois caracteres de largura
  zero barravam o documento. Agora sao removidos sem peso.
* Dado pessoal redigido somava risco e barrava peticoes com a qualificacao das
  partes. Agora nao soma.
* A explicacao em linguagem simples apresentava sinal fraco isolado como achado.

### Resultado

Todos os numeros estao em `docs/AVALIACAO.md`, com o comando que repete cada um.

* Textos juridicos reais sinalizados por engano (4.007 documentos, metade de
  teste): de 20,3% para 0,05%.
* Comandos reais brasileiros pegos no texto: 0 de 10 na 0.3.0, 2 de 10 antes do
  ajuste com eles, 9 de 10 depois. Escondidos em PDF: 30 de 30.
* LLMail-Inject (951 e-mails de ataque, metade de teste): de 23,7% para 56,8%.
* Conjunto cego 2 (120 casos nunca usados para ajuste): deteccao de 13,3% para
  55,0%, falsos positivos de 20,0% para 6,7%.

No corpus de desenvolvimento as duas versoes dao 100%, o que nao mede nada.

## 0.3.0

Explicacao em linguagem simples e vetor de audio.

### Adicionado

* Tradutor para linguagem simples em `reference/explain.py`, que converte os
  sinais tecnicos das camadas em uma explicacao que qualquer pessoa entende:
  veredito, o que estava escondido, como o sistema identificou e a recomendacao.
* Laboratorio visual reescrito para mostrar essa explicacao em destaque, com o
  detalhe tecnico por camada disponivel para quem quiser aprofundar.
* Caso novo no corpus, audio-hidden-command, que representa a injecao por audio
  demonstrada publicamente em maio de 2026, com a defesa correspondente.
* Secao de injecao por audio no modelo de ameacas.

## 0.2.0

Endurecimento e preparacao para o lancamento aberto.

### Adicionado

* Corpus estruturado de ataques em `attacks/corpus.py`, com 24 casos em 11
  categorias, fonte unica para benchmark, testes, gerador de PDFs e documentacao.
* Gerador de PDFs maliciosos de teste em `attacks/generate_test_pdfs.py`, que
  materializa cada vetor como um PDF de aparencia legitima.
* Cobertura de novos vetores na sanitizacao L1: tag characters Unicode
  (U+E0000 a U+E007F), controles bidirecionais e seletores de variacao.
* Novos sinais na deteccao L2: homoglifos por mistura de scripts, decodificacao
  de base64 e reavaliacao, uso indevido de ferramenta e certificado, marcadores
  de estrutura ativa de PDF e linguagem com aparencia de decisao.
* Benchmark reescrito, que separa taxa de deteccao de taxa de falsos positivos.
* Documento de modelo de ameacas e catalogo de ataques, com incidentes reais e
  mapeamento para OWASP e MITRE ATLAS.
* Empacotamento com pyproject, arquivo LICENSE, gitignore e testes unitarios.

### Corrigido

* Portao de aprovacao humana L4 deixou de ser um stub que sempre retornava
  verdadeiro. Agora tem estado real, com aprovacao pelo dono, uso unico, janela
  de validade, conferencia de hash e protecao contra replay.
* Bug de offset no filtro de privacidade, que corrompia o texto quando havia
  mais de um dado pessoal. A reconstrucao agora e feita em passagem unica com
  resolucao de sobreposicao.
* Bug no orquestrador, que descartava o score do detector quando a camada
  retornava uma tupla e corrompia o texto do documento.
* Renomeacao do pacote para `polar_sentinel`, tornando os imports validos.

### Removido

* Exemplos com dados pessoais reais foram substituidos por dados ficticios.
* Demo redundante de marca alternativa.
