# Polar Sentinel

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24143886.svg)](https://doi.org/10.5281/zenodo.24143886)

Camada aberta de defesa contra injeção de comandos (prompt injection) em
documentos, imagens, vídeos e áudios lidos por sistemas de IA do Judiciário
brasileiro.

Fica entre o arquivo e o modelo: mede o que a pessoa vê e ouve contra o que a
máquina lê (contraste, tamanho, duração, volume), separa o que só o modelo
receberia, confere assinatura ICP-Brasil e selo de origem C2PA, redige dados
pessoais, remove canais ocultos, procura
ordens dirigidas à IA que vai ler a peça e exige aprovação humana de uso único
antes de qualquer ação irreversível. O núcleo é Python puro, sem dependências; as
leituras de arquivo usam extras opcionais. As etapas de defesa não fazem
chamada de rede. Licença Apache 2.0.

**Teste no navegador:** https://psicocarehub.github.io/polar-sentinel/ traz petições
de exemplo com os comandos que tribunais publicaram escondidos no PDF. O arquivo é
lido no seu navegador e não é enviado a nenhum servidor.

*English summary [below](#english-summary).*

## O que ele pega, medido

No corpus em que as regras foram escritas, o benchmark dá 100%. Esse número não
mede nada. O que vale é o resultado em dados que não foram escritos para o
detector:

| Medida | Versão 0.3.0 | Versão 0.4.0 |
| --- | --- | --- |
| Decisões, ementas e modelos de petição reais sinalizados por engano (4.007 documentos) | 20,3% | **0,05%** |
| Comandos reais publicados por tribunais brasileiros, pegos no texto (10) | 0 | **9** (eram 2 antes do ajuste com eles) |
| Os mesmos comandos escondidos em PDF: fonte branca, fonte de 0,8 ponto, cor do rodapé (30 arquivos) | sem inspeção | **30** |
| E-mails de ataque do LLMail-Inject (951) | 23,7% | **56,8%** |
| Conjunto cego em português jurídico: ataques pegos (60) | 13,3% | **55,0%** (intervalo de 95%: 43 a 67) |
| Conjunto cego em português jurídico: legítimos sinalizados (60) | 20,0% | **6,7%** (3 a 16) |

Na versão 0.6.0 a inspeção mede o que a pessoa vê e ouve contra o que a
máquina lê em documento, imagem, vídeo e áudio. Primeira medida é a rodada
única num conjunto escrito sem ver o código, antes de qualquer ajuste; depois
dela o conjunto vira desenvolvimento.

| Medida (0.6.0) | Primeira medida | Depois do ajuste |
| --- | --- | --- |
| Documentos: ataques pegos (40) e legítimos difíceis sinalizados (27) | **34** e **1** | 39 e 1 |
| Imagens: ataques (35) e legítimos (27) | **10** e **1** | 22 e 1 |
| Vídeo e áudio: ataques (22) e legítimos (18) | **9** e **1** | 14 e 1 |
| Documentos públicos reais nunca vistos sinalizados por engano (438 arquivos, 2.401 páginas) | **2** | 0 (0 a 0,87%) |
| Documentos reais com imagens lidas pelo OCR (210) | **0** | 0 |
| Áudio e vídeo públicos reais (25 recortes de 3 minutos) | **0** | 0 |
| Atacante que conhece o código: tentativas válidas sinalizadas | **21%** | 77%, e 1% sem nenhum aviso |
| Petições reais de entidades, partidos e imprensa sinalizadas por engano (402) | **59** (14,7%) | 10 (2,5%) |
| Petições nunca vistas, depois das correções (216) | **9** (4,2%) | não ajustado |
| Petições de outras fontes, mais primeiro grau (193) | **10** (5,2%) | não ajustado |

A Justiça brasileira já lê com IA texto e PDF de peças e a transcrição de
audiências (resumida por modelo em vários tribunais); a imagem entra pelo
OCR e o vídeo pela trilha de áudio. O levantamento, sistema por sistema, está
em [docs/pesquisa/IA-NA-JUSTICA-POR-FORMATO.md](docs/pesquisa/IA-NA-JUSTICA-POR-FORMATO.md).

Quatro coisas para ler nessas tabelas:

* **O ataque real é de forma, e forma se detecta.** Em todos os casos
  brasileiros conhecidos o comando estava invisível. A inspeção de PDF olha cor,
  tamanho e posição do texto, e libera papel timbrado e camada de OCR.
* **Em documento público quase não incomoda; em petição incomodava.** Dois
  sinalizados em 4.007 textos e nenhum em 438 documentos públicos. Petições
  reais deram 59 em 402 na primeira passada: tarja que não apaga o CPF, timbre
  coberto, linguagem de peça lida como comando. Nenhuma trazia ordem a IA.
  Corrigido, um lote nunca visto teve 9 sinalizados em 216 (4,2%), e um terceiro,
  de outras fontes, 10 em 193 (5,2%). Em petição real o falso positivo fica
  entre 3% e 9%, quase sempre texto que a máquina lê e a pessoa não vê, sem
  ordem.
* **Quem conhece as regras passa, mas quase nunca em silêncio.** O atacante
  adaptativo escapou da sinalização nos dez comandos reais; depois de três
  rodadas de regras de forma, o que escapa são ordens curtas e secas, e o
  revisor recebe o aviso de que há texto oculto.
* **Ordem em linguagem comum passa em cerca de metade das vezes.** No conjunto
  cego, ofuscação é pega em 11 de 12 casos; paráfrase dirigida à IA em 1 de 6,
  exfiltração em 0 de 3, ordem para pular a revisão em 0 de 3.

Ou seja: é uma triagem barata, determinística e explicável. **Não é garantia de
que um documento liberado está limpo.** A proteção que não depende de o detector
acertar é o portão de aprovação humana.

O 9 de 10 nos comandos reais não mede generalização: as regras foram ajustadas
com esses textos. O protocolo, os números de cada rodada e os limites da medida
estão em [docs/AVALIACAO.md](docs/AVALIACAO.md). O texto completo está em
[paper/polar-sentinel.md](paper/polar-sentinel.md).

## Por que isso importa

Em 2026 o Brasil teve os primeiros casos confirmados de injeção de comandos em
peças processuais:

* TRT-8, 3ª Vara do Trabalho de Parauapebas: ordem dirigida à IA do juízo, em
  fonte branca sobre fundo branco, em petição inicial; multa de cerca de R$ 84
  mil por ato atentatório à dignidade da justiça.
* STJ: em 20 de maio de 2026 o tribunal informou ter encontrado tentativas
  semelhantes em petições e a abertura de inquérito policial.
* CNJ: a Manifestação Técnica CNIAJ nº 1/2026 tratou do tema e deu origem a
  nota técnica dirigida aos tribunais.
* Depois vieram casos no TJSP, no TJMG, no TRT-5, no TJPB, no STF e em três
  turmas do STJ. Os comandos que os tribunais publicaram, com a fonte de cada
  um, estão em `polar_sentinel/attacks/reais.py`.

O panorama, com incidentes e referências, está em
[docs/MODELO_DE_AMEACAS.md](docs/MODELO_DE_AMEACAS.md).

## As etapas

| Etapa | O que faz | Estado neste repositório |
| --- | --- | --- |
| Inspeção de documento | Mede cada caractere de PDF e .docx contra a página renderizada; lê anotações, campos, anexos, metadados e a camada de OCR | Implementado (extra `pdf`) |
| Inspeção de imagem | Texto de baixo contraste, em pixels transparentes, revelado por redução de escala, e metadados | Implementado (extra `midia` e Tesseract) |
| Inspeção de vídeo e áudio | Legendas e quadros relâmpago, metadados, fala muito abaixo da principal, dois transcritores | Implementado (extra `midia`, ffmpeg e Tesseract) |
| Integridade e proveniência | Assinaturas de PDF contra as raízes da ICP-Brasil, alteração depois da assinatura, manifesto C2PA | Implementado (extra `autenticidade`) |
| Filtro de dados pessoais | Redige CPF, CNPJ, RG, e-mail, telefone, CEP e conta bancária | Implementado, por expressões regulares |
| Leitura segura do documento | Remove caracteres invisíveis, controles bidirecionais, tag characters, seletores de variação, comentários HTML e sequências ANSI, com trilha do que saiu | Implementado |
| Detector de comandos | Procura ordens dirigidas à IA no texto limpo e no conteúdo que estava oculto | Implementado |
| Conferência de fontes | Confere a origem declarada de um trecho | Só referência: não consulta base de jurisprudência |
| Aprovação humana | Portão de uso único, com validade e conferência de hash | Implementado |
| Registro e auditoria | Trilha por etapa no resultado do orquestrador | Padrão de referência: não há armazenamento |

O que este repositório não traz: assinatura de documentos, integrações com PJe e
eproc, classificador treinado, camada semântica com modelo, separação de vozes
no áudio e detector de "deepfake".

## Instalação

```bash
pip install polar-sentinel                       # núcleo: texto, detector, aprovação
pip install "polar-sentinel[pdf]"                # PDF e .docx
pip install "polar-sentinel[midia]"              # imagem, vídeo e áudio
pip install "polar-sentinel[autenticidade]"      # assinaturas ICP-Brasil e C2PA
pip install "polar-sentinel[completo]"           # tudo acima
```

Imagem, vídeo e áudio também pedem programas do sistema e modelos de fala:

```bash
brew install tesseract tesseract-lang ffmpeg                        # macOS
sudo apt-get install tesseract-ocr tesseract-ocr-por ffmpeg         # Debian e Ubuntu
python -m polar_sentinel.modelos     # baixa o Whisper e o Vosk pequeno de português
```

Sem o Tesseract, os quadros de vídeo e as imagens não são lidos; sem o
faster-whisper, o áudio não é transcrito; sem o modelo do Vosk, falta a
comparação entre dois transcritores. Em todos esses casos a certidão diz o que
ficou de fora ("Leitura feita sem: ...") em vez de calar.

Para desenvolver: `pip install -e ".[dev,lab,eval,completo]"`.

## Uso rápido

### Inspeção de documento (PDF e .docx)

```bash
pip install "polar-sentinel[pdf]"
python -m polar_sentinel.certidao peticao.pdf --processo 0000000-00.2026.8.26.0100 --peca "Petição inicial"
```

A certidão traz o que a Nota Técnica CNJ 2635739 pede: peça, página, natureza
técnica, medidas (contraste, tamanho, cores, posição), trecho, SHA-256 do
trecho e do arquivo, ação tomada, data e hora de Brasília e versão. Ela
descreve fatos do arquivo; não atribui autoria nem intenção.

```python
from polar_sentinel.reference.pdf_inspector import evaluate_pdf
from polar_sentinel.reference.docx_inspector import evaluate_docx

veredito = evaluate_pdf("peticao.pdf")
print(veredito.flagged, veredito.reasons, veredito.atencao)
for trecho in veredito.inspection.hidden_spans:        # o que o leitor humano não vê
    print(trecho.page, trecho.reason, trecho.medidas["contraste"], trecho.text)
texto_para_o_modelo = veredito.inspection.visible_text  # sem o trecho oculto
```

A página é renderizada com e sem o texto. Cada caractere que a extração entrega
à IA é medido contra o que de fato aparece na tela: contraste com o fundo
desenhado atrás dele, tamanho, opacidade, modo, posição. Isso acha texto
branco, minúsculo, na cor de qualquer faixa, atrás de imagem, recortado,
transparente, em modo invisível ou fora da página, e libera papel timbrado e a
camada de OCR de digitalizados (conferida com o Tesseract, quando instalado).
Fora da página, o arquivo também é lido: anotações, campos de formulário,
camadas desligadas, anexos, JavaScript, links e metadados. No .docx: texto
oculto, na cor do sombreamento, minúsculo, excluído com controle de
alterações, comentários, texto alternativo e códigos de campo.

O trecho oculto é devolvido para ser registrado nos autos, não descartado.

### Imagem, vídeo e áudio

```bash
pip install "polar-sentinel[completo]" && python -m polar_sentinel.modelos
python -m polar_sentinel.certidao prova.jpg
python -m polar_sentinel.certidao audiencia.mp4
python -m polar_sentinel.certidao depoimento.opus
```

* **Imagem:** letra quase da cor do papel ou do fundo (inclusive amarelo claro e
  fundo escuro), texto nos pixels transparentes, texto que só aparece quando a
  imagem é reduzida sem suavização para o tamanho de entrada de um modelo
  (ataque de escala) e ordem em EXIF, XMP, PNG ou comentário de JPEG. PDF
  digitalizado sem camada de texto passa a ser lido.
* **Vídeo:** metadados e capítulos, faixas de legenda, legenda que fica um
  instante na tela, quadro relâmpago entre dois cortes, texto apagado nos
  quadros e o áudio de cada faixa.
* **Áudio:** fala muito abaixo da fala principal, acelerada ou encoberta, que o
  transcritor pega e a pessoa não ouve; dois transcritores de famílias
  diferentes comparados.

### Integridade e proveniência

```bash
python -m polar_sentinel.laudo peca_assinada.pdf
python -m polar_sentinel.laudo foto.jpg
```

O laudo valida as assinaturas do PDF contra as raízes da ICP-Brasil, diz se o
conteúdo visível mudou depois de cada assinatura e mostra onde, e lê o
manifesto C2PA de fotos e vídeos. A conclusão tem três saídas: integridade
confirmada, alteração detectada ou inconclusivo. Prova integridade, não
veracidade, e não dá nota de "deepfake".

### Leitura segura

```python
from polar_sentinel import sanitize_with_audit

resultado = sanitize_with_audit(texto_do_pdf, source="peticao_upload")
print(resultado.text)                                   # texto limpo
print([(e.kind, e.count) for e in resultado.entries])   # trilha do que saiu
print(resultado.suspicious)                             # houve ocultação?
```

### Detector

```python
from polar_sentinel import detect_suspicious_patterns

score, razoes = detect_suspicious_patterns(texto)                    # documento que chega
score, razoes = detect_suspicious_patterns(resumo, stage="saida")    # texto que a ferramenta produziu
if score > 0.4:
    print("Suspeito:", razoes)
```

Na entrada, "julgo procedente" é texto normal de sentença. Na saída de uma
ferramenta de apoio, é o que a governança deve barrar.

### Portão de aprovação humana

```python
from polar_sentinel import (
    create_pending_approval, approve_pending, consume_approval, payload_hash,
)

payload = {"tribunal": "TRT-8", "pdf_sha256": "..."}
digest = payload_hash("tribunal.protocolar", payload)

pend = create_pending_approval(
    action="tribunal.protocolar", payload=payload, user_id="advogada_1"
)
assert consume_approval(pend.id, "tribunal.protocolar", digest) is False   # sem aprovação, falha
approve_pending(pend.id, user_id="advogada_1")
assert consume_approval(pend.id, "tribunal.protocolar", digest) is True    # uso único
assert consume_approval(pend.id, "tribunal.protocolar", digest) is False   # repetição falha
```

### Pipeline completo com qualquer API

```python
from polar_sentinel import SentinelPipeline
from polar_sentinel.harness.adapters import OpenAICompatibleAdapter

adapter = OpenAICompatibleAdapter(base_url="https://sua-api/v1", model="seu-modelo")
pipeline = SentinelPipeline(adapter=adapter)

resultado = pipeline.analyze_and_protect(
    document_text=texto, action="tribunal.protocolar", user_id="advogada_1"
)
print(resultado["status"], resultado["risk_score"], resultado["hitl_required"])
```

## Medir

```bash
python -m pytest -q                                           # suíte de testes
python -m polar_sentinel.benchmarks.agent_safety_bench        # corpus de desenvolvimento
python -m polar_sentinel.benchmarks.heldout_eval --casos      # validação e conjuntos cegos
python -m polar_sentinel.benchmarks.atacante_adaptativo     # atacante que conhece o código (pede Poppler)

# conjuntos públicos (ataques escritos por pessoas e textos jurídicos reais)
pip install -e ".[eval]"
python -m polar_sentinel.benchmarks.baixar_externos ~/sentinel_externos
python -m polar_sentinel.benchmarks.external_eval ~/sentinel_externos
```

Os conjuntos públicos não são redistribuídos aqui: o script os baixa do Hugging
Face. Cada um é dividido em duas metades pelo hash do texto; a de
desenvolvimento pode ser lida para corrigir regras, a de teste só recebe medida.

O conjunto cego 2 só continua valendo como medida enquanto ninguém ajustar
regras olhando para ele. Quem alterar o detector deve trazer um conjunto novo.

## Demonstração no navegador

A página https://psicocarehub.github.io/polar-sentinel/ roda o Polar Sentinel
dentro do navegador (com stlite e Pyodide) e é publicada a cada mudança em
`main`. O código está em [demo_web/](demo_web/); para montar e testar localmente:

```bash
pip install -e ".[lab]"
python demo_web/gerar_exemplos.py      # PDFs de exemplo
bash demo_web/montar.sh                # monta o site em _site/
python -m http.server --directory _site
```

## Laboratório visual e PDFs de teste

```bash
pip install -e ".[lab]"
streamlit run polar_sentinel/demo/sentinel_test_page.py       # envia PDF ou texto e mostra cada etapa
python -m polar_sentinel.attacks.generate_test_pdfs           # gera PDFs que embutem cada vetor do corpus
```

Todos os exemplos usam dados fictícios. O catálogo dos vetores está em
[docs/CATALOGO_DE_ATAQUES.md](docs/CATALOGO_DE_ATAQUES.md), e a explicação em
linguagem simples em
[docs/TIPOS_DE_ATAQUE_EXPLICADOS.md](docs/TIPOS_DE_ATAQUE_EXPLICADOS.md).

## Estrutura

```
polar_sentinel/
  reference/      etapas de defesa
  harness/        orquestrador, pipeline, adaptadores e testes de cenário
  attacks/        corpus de desenvolvimento, validação, conjuntos cegos, comandos reais e gerador de PDFs
  benchmarks/     medida no corpus, nos conjuntos cegos e em dados públicos
  demo/           laboratório visual em Streamlit
  tests/          testes unitários e orientados pelos conjuntos
docs/             documentação técnica e avaliação
paper/            texto completo
```

A documentação está indexada em [docs/README.md](docs/README.md); o mapeamento
para a Resolução CNJ nº 615/2025 está em
[docs/CONFORMIDADE_CNJ_615.md](docs/CONFORMIDADE_CNJ_615.md).

## Como contribuir

* Tribunais e escritórios: abram issues com casos de ataque, sempre anonimizados.
  Um comando real novo, com a fonte, é a contribuição que mais vale: é o único
  teste de generalização em caso real.
* Pesquisadores: tragam um conjunto cego novo ou uma camada de sentido, e meçam.
* Vulnerabilidades: use o aviso privado descrito em [SECURITY.md](SECURITY.md).

Este repositório reúne apenas vetores já descritos em literatura pública.

## Como citar

Estevam, M. A. S. (2026). *Polar Sentinel: o que um filtro determinístico de
injeção de comandos pega, e o que deixa passar, em documentos jurídicos
brasileiros*. Zenodo. https://doi.org/10.5281/zenodo.24143886 (o DOI aponta sempre para a
versão mais recente). Veja [CITATION.cff](CITATION.cff).

## English summary

Polar Sentinel is an open (Apache 2.0) defense layer against prompt injection in
documents read by AI systems in Brazilian courts. In 2026, several Brazilian
courts found petitions carrying hidden orders addressed to the AI that reads the
case file: white text on a white page, text in a 0.8 pt font, text in the color
of the footer band. Since version 0.6.0, Sentinel measures what a person sees and
hears against what the machine reads, in physical units (contrast, glyph size,
on-screen duration, speech level), across PDF and .docx, images (OCR, including
image-scaling attacks), video (flash frames, short subtitles, container
metadata) and audio (speech far below the main voice). It separates what only
the model would receive, issues a certificate in the format requested by the
Brazilian National Council of Justice, checks ICP-Brasil signatures and C2PA
provenance, and requires a single-use human approval before any irreversible
action. Brazilian courts already feed party filings and hearing transcriptions
to language models; images reach them through OCR, video through its audio.

Measured on data it was not written for (details in
[docs/AVALIACAO.md](docs/AVALIACAO.md), in Portuguese):

* **Real Brazilian legal texts:** 2 false positives in 4,007 court decisions,
  headnotes and petition templates (0.05%; the previous version flagged 20.3%).
* **Real commands published by Brazilian courts:** 9 of 10 caught in plain text
  after tuning on them (2 of 10 before), and 30 of 30 when hidden in a PDF the
  way the court reports describe.
* **LLMail-Inject attack emails:** 56.8% caught.
* **Blind set in Brazilian legal Portuguese:** 55.0% of 60 attacks caught
  (95% CI 43 to 67), with 6.7% false positives on 60 deliberately hard
  legitimate documents.
* **Blind sets, first and only run before tuning:** documents 34 of 40 attacks
  (1 of 27 legitimate flagged), images 10 of 35 (1 of 27), video and audio 9 of
  22 (1 of 18).
* **Real files with no attack:** 0 of 438 unseen public documents, 0 of 210
  documents with OCR on images, 0 of 25 public audio and video clips.
* **Adaptive attacker that knows the code:** it evaded flagging for all ten real
  commands in round one, mostly on the first query. After three rounds of
  form-based rules, 77% of its valid attempts are flagged and 1% pass with no
  warning at all; the rest raise a hidden-text warning.

The practical reading: the attack courts are actually seeing is hidden by form,
and form is cheap to detect precisely. Orders written in ordinary language, with
nothing hidden, get through about half the time, so this is triage, not a
guarantee; the human approval gate is the protection that does not depend on the
detector being right.

Try it in the browser: https://psicocarehub.github.io/polar-sentinel/ (the file
is processed locally and never uploaded). Full paper (Portuguese):
[paper/polar-sentinel.pdf](paper/polar-sentinel.pdf). Cite:
https://doi.org/10.5281/zenodo.24143886

## Licença

Apache 2.0. Veja [LICENSE](LICENSE).
