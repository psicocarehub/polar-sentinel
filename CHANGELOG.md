# Changelog

Formato baseado em Keep a Changelog. Versionamento semantico.

## 0.6.0 (12/11/2026)

Imagem, video, audio e autenticidade; atacante adaptativo e peticoes reais.

### Adicionado

* Imagem (`reference/imagem_inspector.py`): o Tesseract le a imagem como esta e
  numa vista amplificada, em que o que difere um pouco do papel em volta (mais
  claro ou mais escuro, em qualquer canal de cor) vira preto. Cada linha ganha
  contraste e tamanho medidos na imagem original. Acha letra quase da cor do
  papel ou do fundo escuro, amarelo claro sobre branco, texto nos pixels
  transparentes, texto que so aparece quando a imagem e reduzida sem
  suavizacao para tamanhos de entrada de modelo (ataque de escala, com um
  sinal barato que escolhe quais reducoes ler) e ordem em EXIF, XMP, PNG e
  comentario de JPEG.
* PDF digitalizado sem camada de texto passa a ser lido; imagens de pagina sao
  lidas na resolucao da imagem; metadados de JPEG embutido em PDF; imagens de
  `.docx`.
* Video (`reference/video_inspector.py`, ffmpeg): metadados e capitulos do
  conteiner, faixas de legenda lidas inteiras, legenda que fica menos de 0,3 s
  na tela, quadro relampago entre dois cortes (menos de 0,25 s) lido com o
  inspetor de imagem, quadros amostrados com texto apagado, faixas extras.
* Audio (`reference/audio_inspector.py`, faster-whisper e Vosk): fala 20 dB ou
  mais abaixo da fala principal sai do texto "ouvido" e e relatada; versoes
  com volume normalizado, faixa de voz isolada e audio desacelerado revelam
  fala escondida; dois transcritores de familias diferentes comparados;
  trecho com voz e sem transcricao; energia acima de 18 kHz.
* Autenticidade (`reference/autenticidade.py`, `python -m polar_sentinel.laudo`):
  assinaturas de PDF validadas pelo pyHanko contra as raizes da ICP-Brasil
  (v5, v10, v11 e v12, no pacote), nivel de modificacao depois de cada
  assinatura e diferenca visual entre a revisao assinada e a atual, com a
  regiao; assinatura legada adbe.pkcs7.sha1 com o hash conferido; manifesto
  C2PA (presenca, validade, assinante, declaracao de geracao por IA). Tres
  conclusoes: integridade confirmada, alteracao detectada, inconclusivo.
* A certidao aceita imagem, video e audio, com instantes e duracoes.
* Atacante adaptativo (`benchmarks/atacante_adaptativo.py`): conhece o codigo,
  combina dez formas de esconder texto no PDF, nove transformacoes e
  parafrases, confere com o Poppler que o ataque e extraivel e imperceptivel e
  aprende com o que escapou. As regras abaixo vieram das rodadas dele.
* PDF: a busca de ordem no texto oculto desfaz leetspeak e reune letras
  espacadas; texto invisivel de fato que forma frase (seis palavras e duas de
  ligacao) sinaliza mesmo sem ordem; texto oculto com letras soltas ou ligadas
  por hifen sinaliza, inclusive em baixo contraste; texto substituto
  (`/ActualText`) diferente dos glifos desenhados gera atencao e sinaliza com
  ordem ou frase.
* Levantamento do que a Justica brasileira le com IA, por formato
  (`docs/pesquisa/IA-NA-JUSTICA-POR-FORMATO.md`), resumido no modelo de ameacas.
* `python -m polar_sentinel.modelos` baixa o Whisper e o Vosk pequeno de
  portugues. Quando falta Tesseract, faster-whisper ou o modelo do Vosk, a
  leitura registra o que ficou de fora e a certidao mostra ("Leitura feita
  sem: ...").

### Corrigido

* A regra das seis palavras, feita para texto lido de imagem embutida, valia
  para texto de PDF na cor do fundo e nao valia para a imagem embutida.
* O faster-whisper 1.2 deixou de decodificar audio com o PyAV 19; o sinal
  agora chega ja decodificado.
* O extra `midia` pedia `vosk>=0.3.45`, versao que nao existe.
* A certidao dizia "ordem em conteudo que o leitor nao ve" tambem quando a
  ordem estava no texto visivel ou na fala audivel.
* Falsos positivos achados em 402 peticoes reais (59 na primeira passada, 29
  delas ja na 0.5.0), cada um com teste em `tests/test_peticoes_reais.py`:
  * tarja preta ou branca sobre CPF, endereco e OAB vira a atencao
    `tarja_que_nao_apaga`; ordem debaixo da tarja continua sinalizada;
  * carimbo do PJe fora da folha e nota de rodape coberta por figura viram
    atencao; timbre coberto em toda pagina conta uma vez;
  * texto sob imagem digitalizada passa pela conferencia de OCR do Tesseract;
  * link so sinaliza com ordem dirigida a IA, e `utm_source` sai do endereco;
  * o binario de assinatura ICP-Brasil deixa de ser lido como campo de
    formulario;
  * o detector de texto deixa de disparar em "[s]egundo", "burlar a lei",
    "em atencao ao sistema", linha quebrada no meio da frase, rol de pedidos
    ("b. conceda a liminar"), "/launchapp" e "TRF/4a";
  * a quebra manual do Word (U+2028) deixa de contar como caractere
    invisivel;
  * texto de imagem embutida (OCR de digitalizacao, marca d'agua, botao de
    captura de tela) precisa formar frase, e ordem em imagem de contraste
    baixo precisa ser dirigida a IA;
  * glifo repetido ("0 0 0") deixa de contar como letras soltas.

## 0.5.0

Documento completo: o que a pessoa ve contra o que a maquina le.

### Adicionado

* Inspecao pela pagina renderizada (`reference/pdf_percepcao.py`): a pagina e
  desenhada com e sem o texto, e cada caractere extraido ganha medidas fisicas
  (contraste WCAG contra o fundo realmente desenhado, tamanho, cor, opacidade,
  modo, rotacao, posicao). Acha texto atras de imagem, recortado, transparente,
  em modo invisivel e na cor de faixas que nao sao brancas, que a leitura do
  conteudo nao via. O limite de leitura sobe quando a letra e pequena. Pede
  `pypdfium2` e `numpy`; sem eles, vale a leitura antiga.
* Conferencia da camada de OCR de paginas digitalizadas com o Tesseract,
  quando instalado: linha da camada que a imagem nao confirma vira
  `ocr_divergente`.
* Estrutura do PDF (`reference/pdf_estrutura.py`): anotacoes, campos de
  formulario, camadas que abrem desligadas, arquivos anexados (PDF anexado e
  inspecionado), JavaScript, links, metadados XMP e revisoes incrementais.
* Inspecao de `.docx` (`reference/docx_inspector.py`), so com a biblioteca
  padrao: propriedade oculto no trecho e no estilo, letra na cor do
  sombreamento, do realce ou da pagina, fonte minuscula, texto excluido com
  controle de alteracoes, comentarios, texto alternativo, codigos de campo,
  XML personalizado, macros e objetos embutidos.
* Palavras partidas ("red ija", "pro vido") deixam de esconder a ordem no
  texto oculto.
* Certidao de inspecao tecnica (`python -m polar_sentinel.certidao arquivo`),
  com o que a Nota Tecnica CNJ 2635739 pede: peca, pagina, natureza, medidas,
  trecho, SHA-256 do trecho e do arquivo, acao, data e hora de Brasilia e
  versao. Descreve fatos; nao atribui autoria nem intencao.
* `benchmarks/documentos_reais.py`: falso positivo em pastas de documentos
  reais, com intervalo de Wilson. `benchmarks/fronteira.py`: grade de
  contraste e tamanho que mostra onde um comando escapa.

### Mudado

* `evaluate_pdf` devolve tambem `atencao` (texto oculto sem ordem,
  JavaScript, anexos, camadas desligadas, Unicode invisivel) e aceita
  `motor="renderizacao"` ou `motor="conteudo"`.
* O extra `pdf` passa a instalar `pypdfium2`, `numpy` e `pillow`.

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
