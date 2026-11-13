"""Polar Sentinel: inspecao de PDF (texto que o leitor humano nao ve).

Em todos os casos brasileiros conhecidos de 2026, o comando estava escondido
pela FORMA: fonte branca sobre fundo branco, fonte de menos de 1 ponto, texto
na cor da faixa do rodape. A extracao de texto comum joga fora a cor e o
tamanho, e o comando chega ao modelo misturado ao texto legitimo. Este modulo
le o conteudo da pagina e separa o que esta visivel do que esta oculto.

Um trecho conta como oculto quando:

    cor_do_fundo      a cor do texto e praticamente a cor do que esta atras dele
                      (a pagina branca, ou um retangulo pintado antes)
    fonte_minuscula   o tamanho efetivo da fonte e menor que 2 pontos
    fora_da_pagina    o texto esta posicionado fora da area da pagina

Texto branco sobre faixa escura (papel timbrado) nao e oculto: o fundo naquele
ponto e a faixa. Camada de texto invisivel de OCR (modo de renderizacao 3) e o
proprio texto de um documento digitalizado e segue como texto visivel.

A decisao fica em `evaluate_pdf`: fonte minuscula com texto de verdade sempre
sinaliza; texto na cor do fundo ou fora da pagina sinaliza quando traz uma
ordem (imperativo, mencao a IA ou qualquer sinal do detector). O trecho oculto
e devolvido para ser registrado nos autos, nunca descartado.

Com pypdfium2 e numpy instalados, a inspecao passa a medir a pagina
renderizada (reference/pdf_percepcao.py): o fundo deixa de ser adivinhado, e
texto atras de imagem, recortado, transparente ou em modo invisivel tambem e
achado. Sem eles, vale a leitura do conteudo descrita acima, que nao ve fundo
feito de imagem nem texto atras de outro objeto. Nos dois casos, anotacoes,
campos de formulario, camadas desligadas, arquivos embutidos, JavaScript e
metadados sao lidos por reference/pdf_estrutura.py.

Precisa de pypdf (pip install pypdf).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from polar_sentinel.reference.injection_detector import (
    _AI_TERM,
    _IMPERATIVE,
    _collapse,
    _join_spaced,
    _undo_leet,
    detect_suspicious_patterns,
    fold,
)
from polar_sentinel.reference.pdf_estrutura import Achado, inspecionar_estrutura
from polar_sentinel.reference.sanitizer import sanitize_with_audit

Color = Tuple[float, float, float]

_WHITE: Color = (1.0, 1.0, 1.0)
_BLACK: Color = (0.0, 0.0, 0.0)

# Diferenca maxima, por componente, para duas cores contarem como a mesma.
_SAME_COLOR = 0.1
# Abaixo deste tamanho efetivo, em pontos, ninguem le.
_MIN_READABLE_PT = 2.0
# Letras a partir das quais um trecho em fonte minuscula deixa de ser residuo.
_MIN_LETTERS = 12
# Formas em que a pessoa nao ve o texto de jeito nenhum (o baixo contraste ainda
# se le de perto; a camada de OCR nao confirmada pode ser so erro de leitura).
INVISIVEL_DE_FATO = frozenset(
    {"cor_do_fundo", "coberto_ou_recortado", "transparente", "modo_invisivel", "fora_da_pagina"}
)
# Texto invisivel de fato que forma frase sinaliza mesmo sem ordem reconhecida.
# O atacante adaptativo escapava da regra de ordem trocando letras por digitos
# ("d3f1r4"); uma contagem de caracteres pegava, mas tambem pegava referencia
# interna de escritorio em branco ("REF-INT: PASTA 2026-0412 | CLIENTE ..."),
# que e pratica real. Frase (palavras de ligacao) separa as duas coisas.
_FILL_OPS = {b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"}
_NO_FILL_OPS = {b"n", b"S", b"s"}

_ORDER_RE = re.compile(
    r"\b(?:" + _IMPERATIVE + r")\b|\b(?:" + _AI_TERM + r")|\b(?:chat|gpt|chatgpt|inteligencia artificial)\b"
)
_IMPERATIVO_RE = re.compile(r"\b(?:" + _IMPERATIVE + r")\b")
# "Diretriz para sistemas de IA:", "nota ao modelo:": rotulo dirigido a IA.
_ROTULO_A_IA = re.compile(r"(?:" + _AI_TERM + r"|\bia\b|\bmodelos?\b|\bassistentes?\b)[^.\n:()\[\]|]{0,20}:")
# Ordem na voz passiva: "deve ser resumida como", "devem ser tratados como".
_DEVER_DE_LEITURA = re.compile(
    r"\bdevem?\s+ser\s+(?:resumid|apontad|considerad|tratad|classificad|descrit|lid|"
    r"interpretad|apresentad|avaliad|ignorad|desconsiderad)\w*")
# Os mesmos sinais com as palavras partidas ("pet ição", "in teligência"): o
# texto oculto e comparado tambem sem espacos nem pontuacao. Radicais curtos
# ("gpt", "llm") ficam de fora, porque aparecem por acaso em blocos de base64.
_RADICAIS = re.compile(
    "inteligenciaartificial|agentedeia|modelodeia|modelodelinguagem|chatgpt|sistemadeia|"
    "sistemasdeia|sistemaautomat|leitorautomat|leitoresautomat|assistenteautomat|"
    "assistentevirtual|agenteautomat|ferramentadeia|"
    "defira|indefira|acolha|julgue|redija|ignore|desconsidere|considere|conteste|impugne|"
    "negue|interprete|favoravel|integralmenteprovido|conhecidoeprovido|sevoceeum|"
    "conceda|classifique|sugira|declare|registre"
)
# Termo de IA ou sinal de leitura por maquina, para os canais em que
# imperativo sozinho e comum (metadados): "ao transcrever", "instrucoes
# anteriores", "sem avisar".
_TERMO_DE_IA = re.compile(
    r"\b(?:" + _AI_TERM + r")|\b(?:chat|gpt|chatgpt|llm|ia|leitor(?:es)? automatizad\w*|"
    r"sistemas? automatizad\w*|(?:ao|para o|aos) modelos?|"
    r"ao (?:transcrever|analisar|resumir|ler|processar|interpretar|descrever)|"
    r"(?:orientacoes|instrucoes|comandos|regras) anteriores|sem (?:avisar|informar|mencionar))\b"
    # vocativo curto seguido de dois-pontos: "Assistente: nao transcreva..."
    r"|\b(?:assistente|modelo|sistema|agente|ia|leitor\w*|transcritor)\s*:"
)
# Ordens de adulteracao que nao estao no detector de texto, que trabalha sobre
# texto visivel e evita verbos comuns em peca. Aqui so valem em canal oculto.
_ORDEM_DE_ADULTERACAO = re.compile(
    r"\b(?:substitua|troque|altere|elogie|rejeite|esqueca|apague|acrescente|modifique|"
    r"mude|inverta|minimize|exagere|enfatize)\b"
)
# Bloco sem espaco maior que isto nao e palavra partida (base64, hash).
_MAX_PEDACO = 20
# Canais fora da pagina em que uma ordem sinaliza o documento.
_CANAIS_COM_TEXTO = {
    "anotacao": "ordem_em_anotacao",
    "campo_de_formulario": "ordem_em_campo_de_formulario",
    "camada_desligada": "ordem_em_camada_desligada",
    "arquivo_embutido": "ordem_em_arquivo_embutido",
    "javascript": "ordem_em_javascript",
    "link": "ordem_em_link",
    "metadado": "comando_em_metadado",
    "metadado_de_imagem": "comando_em_metadado_de_imagem",
    "texto_substituto": "ordem_em_texto_substituto",
}


@dataclass
class HiddenSpan:
    """Um trecho de texto que nao aparece para quem le a pagina."""

    page: int
    text: str
    reason: str
    # Contraste, tamanho, cores, opacidade, modo, rotacao e posicao, quando a
    # pagina foi renderizada.
    medidas: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PdfInspection:
    """Texto visivel, trechos ocultos e metadados de um PDF."""

    visible_text: str
    hidden_spans: List[HiddenSpan] = field(default_factory=list)
    metadata_text: str = ""
    achados: List[Achado] = field(default_factory=list)
    motor: str = "conteudo"
    paginas: int = 0

    @property
    def hidden_text(self) -> str:
        return " ".join(s.text.strip() for s in self.hidden_spans if s.text.strip())


@dataclass
class PdfVerdict:
    """Decisao sobre um PDF, com os motivos e o que estava oculto."""

    flagged: bool
    reasons: List[str]
    inspection: PdfInspection
    # O que merece olhar humano sem sinalizar: texto oculto sem ordem,
    # JavaScript, anexos, revisoes.
    atencao: List[str] = field(default_factory=list)


def _to_rgb(values: Sequence[Any]) -> Optional[Color]:
    try:
        nums = [float(v) for v in values]
    except (TypeError, ValueError):
        return None
    if len(nums) == 1:
        return (nums[0], nums[0], nums[0])
    if len(nums) == 3:
        return (nums[0], nums[1], nums[2])
    if len(nums) == 4:
        c, m, y, k = nums
        return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    return None


def _same(a: Color, b: Color) -> bool:
    return all(abs(x - y) <= _SAME_COLOR for x, y in zip(a, b))


def _scale(matrix: Sequence[float]) -> float:
    return abs(matrix[0] * matrix[3] - matrix[1] * matrix[2]) ** 0.5


def _apply(matrix: Sequence[float], x: float, y: float) -> Tuple[float, float]:
    return (matrix[0] * x + matrix[2] * y + matrix[4], matrix[1] * x + matrix[3] * y + matrix[5])


class _PageState:
    """Estado grafico minimo para saber cor, tamanho e fundo de cada trecho."""

    def __init__(self, number: int, width: float, height: float) -> None:
        self.number = number
        self.width = width
        self.height = height
        self.fill: Color = _BLACK
        self.stack: List[Color] = []
        self.pending: List[Tuple[float, float, float, float]] = []
        self.rects: List[Tuple[Tuple[float, float, float, float], Color]] = []
        self.visible: List[str] = []
        self.hidden: List[HiddenSpan] = []

    def on_operator(self, operator: bytes, args: Sequence[Any], cm: Sequence[float], tm: Sequence[float]) -> None:
        if operator == b"q":
            self.stack.append(self.fill)
        elif operator == b"Q":
            if self.stack:
                self.fill = self.stack.pop()
        elif operator in (b"g", b"rg", b"k", b"sc", b"scn"):
            color = _to_rgb(args)
            if color is not None:
                self.fill = color
        elif operator == b"re" and len(args) == 4:
            try:
                x, y, w, h = (float(a) for a in args)
            except (TypeError, ValueError):
                return
            x0, y0 = _apply(cm, x, y)
            x1, y1 = _apply(cm, x + w, y + h)
            self.pending.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        elif operator in _FILL_OPS:
            self.rects.extend((bbox, self.fill) for bbox in self.pending)
            self.pending = []
        elif operator in _NO_FILL_OPS:
            self.pending = []

    def _background(self, x: float, y: float) -> Color:
        for (x0, y0, x1, y1), color in reversed(self.rects):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return color
        return _WHITE

    def on_text(self, text: str, cm: Sequence[float], tm: Sequence[float], font: Any, size: float) -> None:
        if not text.strip():
            self.visible.append(text)
            return
        x, y = _apply(cm, tm[4], tm[5])
        effective = float(size) * _scale(tm) * _scale(cm)
        reason = ""
        if effective < _MIN_READABLE_PT:
            reason = "fonte_minuscula"
        elif x < -1 or y < -1 or x > self.width + 1 or y > self.height + 1:
            reason = "fora_da_pagina"
        elif _same(self.fill, self._background(x, y)):
            reason = "cor_do_fundo"
        if reason:
            self.hidden.append(HiddenSpan(self.number, text, reason))
        else:
            self.visible.append(text)


def tem_ordem(texto: str, stage: str = "entrada") -> bool:
    """Ha ordem dirigida a IA, mesmo com as palavras partidas ou letras separadas?"""
    texto = sanitize_with_audit(texto).text  # tira largura zero entre as letras
    dobrado = fold(texto)
    pedacos = " ".join(p for p in dobrado.split() if len(p) <= _MAX_PEDACO)
    if _RADICAIS.search(re.sub(r"[^a-z]", "", pedacos)):
        return True
    cru = fold(texto, collapse=False)
    for vista in (dobrado, _undo_leet(dobrado), _undo_leet(_collapse(_join_spaced(cru)))):
        if _ORDER_RE.search(vista) or _ORDEM_DE_ADULTERACAO.search(vista):
            return True
    return detect_suspicious_patterns(texto, stage)[0] > 0.2


def _invisivel_em_imagem(motivo: str, texto: str) -> bool:
    """Texto de imagem que a pessoa nao ve e que tem palavras de verdade bastantes."""
    from polar_sentinel.reference.imagem_inspector import (
        INVISIVEL_EM_IMAGEM,
        MIN_PALAVRAS_INVISIVEIS,
        _palavras_reais,
    )

    # So vale para trecho lido de imagem embutida ("imagem_cor_do_fundo"); texto de
    # PDF na cor do fundo segue a regra de frase, que libera referencia interna.
    if not motivo.startswith("imagem_"):
        return False
    # Digitalizacao e foto dao ruido de OCR ("Lulu que OO. doa") e marca d'agua
    # ("OBSERVATORIO DO CARVAO"); frase escondida tem palavras de ligacao e pouco lixo.
    tokens = texto.split()
    return (motivo[len("imagem_"):] in INVISIVEL_EM_IMAGEM
            and _palavras_reais(texto) >= MIN_PALAVRAS_INVISIVEIS
            and parece_frase(texto)
            and _palavras_reais(texto) >= 0.6 * len(tokens))


def dirigido_a_ia(texto: str, stage: str = "entrada") -> bool:
    """Ordem com destinatario de IA explicito, para canais onde imperativo e comum."""
    texto = sanitize_with_audit(texto).text
    dobrado = fold(texto)
    if not _TERMO_DE_IA.search(dobrado):
        return False
    # O termo de IA sozinho nao e ordem: o assunto do processo no PJe pode ser
    # "uso de inteligencia artificial". Precisa de um imperativo alem dele.
    cru = fold(texto, collapse=False)
    for vista in (dobrado, _undo_leet(dobrado), _undo_leet(_collapse(_join_spaced(cru)))):
        if (_IMPERATIVO_RE.search(vista) or _ORDEM_DE_ADULTERACAO.search(vista)
                or _ROTULO_A_IA.search(vista) or _DEVER_DE_LEITURA.search(vista)):
            return True
    return detect_suspicious_patterns(texto, stage)[0] > 0.2


def desofuscado(texto: str) -> str:
    """Reune letras espacadas ou ligadas por hifen e desfaz leetspeak, para medir o texto."""
    cru = fold(sanitize_with_audit(texto).text, collapse=False)
    cru = re.sub(r"(?<![a-z0-9])(?:[a-z0-9]-)+[a-z0-9](?![a-z0-9])",
                 lambda m: m.group().replace("-", ""), cru)
    claro = _undo_leet(_collapse(_join_spaced(cru)))
    palavras = re.findall(r"[a-z0-9@$]+", claro)
    if palavras and sum(1 for p in palavras if re.search(r"[0-9@$]", p)) >= 0.3 * len(palavras):
        # Texto quase todo em leetspeak: os digitos soltos ("3", "4") tambem sao letras.
        claro = claro.translate(_LEET_TOTAL)
    return claro


_LEET_TOTAL = str.maketrans("013457@$", "oieastas")
# Palavras de ligacao: frase tem, rotulo e referencia interna nao.
_LIGACAO = frozenset(
    "a o as os e de da do das dos em no na nos nas um uma que para por pelo pela com "
    "se ao aos nao sem como mais ou "
    # ingles: ataque publicado costuma vir em ingles
    "the of and to in for on with that is by as an".split()
)


# Letras soltas em sequencia ("d e f i r a") ou ligadas por hifen ("d-e-f-i-r-a"):
# ofuscacao deliberada. Nenhum dos mais de 2.400 documentos reais medidos tem
# isso em texto oculto, nem no de baixo contraste.
_MIN_LETRAS_SOLTAS = 15
_MIN_LETRAS_DISTINTAS = 7
_HIFENIZADA = re.compile(r"(?:[^\W\d_]-){4,}[^\W\d_]")


def ofuscado(texto: str) -> bool:
    """Texto escrito para nao ser reconhecido por filtro, mas lido por modelo."""
    seguidas: List[str] = []
    maior = 0
    for parte in texto.split():
        if re.fullmatch(r"[^\W_]", parte):
            seguidas.append(parte.lower())
            # Glifo solto repetido ("0 0 0", "a a a", caixa de formulario) nao e
            # palavra partida; frase espacada usa letras variadas.
            if sum(ch.isalpha() for ch in seguidas) >= _MIN_LETRAS_SOLTAS and len(
                    {ch for ch in seguidas if ch.isalpha()}) >= _MIN_LETRAS_DISTINTAS:
                maior = len(seguidas)
        elif not re.fullmatch(r"\W+", parte):
            seguidas = []
    return maior >= _MIN_LETRAS_SOLTAS or len(_HIFENIZADA.findall(texto)) >= 3


_IDENTIFICADOR = re.compile(
    r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"          # CPF
    r"|\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"  # CNPJ
    r"|\b\d{2}\.?\d{3}-\d{3}\b"                    # CEP
    r"|\boab\s*/?\s*[a-z]{2}\b"
    r"|[\w.+-]+@[\w-]+\.[\w.]+"                      # e-mail
)
_QUALIFICACAO = re.compile(
    r"\b(?:brasileir[oa]s?|casad[oa]|solteir[oa]|divorciad[oa]|viuv[oa]|portador[a]?|"
    r"inscrit[oa]|residente|domiciliad[oa]|endereco|cpf|cnpj|rg|cep|oab|ssp|"
    r"rua|avenida|av|bairro|apto|apartamento|quadra|lote|s/n|e-?mail|eletronico|advogad[oa])\b"
)


_CARIMBO = re.compile(
    r"\b(?:assinado (?:eletronicamente|digitalmente)|documento assinado|impresso por|"
    r"consultadocumento|conferencia de documento digital|codigo verificador)\b"
)


# Assinatura do programa que gerou o PDF, posta em letra minuscula no rodape.
_GERADOR = re.compile(r"\b(?:powered by|generated by|created (?:with|by)|gerado (?:por|com))\b")
_REFERENCIA = re.compile(
    r"\b(?:disponivel em|acesso em|acessado em|consultado em)\b|https?://|www\.")


def _sem_repeticao(partes: List[str]) -> List[str]:
    """Cada texto uma vez, sem os pedacos de outro ("UTIVA NA" de "EXECUTIVA NACIONAL").

    Timbre coberto pelo corpo do texto aparece em toda pagina, cortado em lugares
    diferentes; somado, viraria frase. Ordem repetida em toda pagina continua
    contando uma vez.
    """
    # Numero nao distingue: "Pag. 1 de 9" e "Pag. 2 de 9" sao o mesmo rodape.
    limpos = {t: re.sub(r"\s+", " ", re.sub(r"\d+", "#", fold(t))).strip() for t in partes}
    unicos = sorted({v for v in limpos.values() if v}, key=len, reverse=True)
    mantidos: List[str] = []
    for v in unicos:
        if not any(v in m for m in mantidos):
            mantidos.append(v)
    vistos, saida = set(), []
    for t in partes:
        v = limpos[t]
        if v in mantidos and v not in vistos:
            vistos.add(v)
            saida.append(t)
    return saida


def dado_pessoal(texto: str) -> bool:
    """Trecho que e qualificacao de parte (documento, endereco), o que se tarja."""
    dobrado = fold(texto, collapse=False)
    if _IDENTIFICADOR.search(dobrado):
        return True
    return len(_QUALIFICACAO.findall(dobrado)) >= 2


def parece_frase(texto: str) -> bool:
    """Seis palavras de verdade e duas de ligacao, depois de desfazer a ofuscacao."""
    from polar_sentinel.reference.imagem_inspector import MIN_PALAVRAS_INVISIVEIS, _palavras_reais

    claro = desofuscado(texto)
    ligacao = sum(1 for p in re.findall(r"[a-z]+", claro) if p in _LIGACAO)
    return _palavras_reais(claro) >= MIN_PALAVRAS_INVISIVEIS and ligacao >= 2


def parece_texto(texto: str) -> bool:
    """Texto que um modelo leria como lingua, e nao glifo sem mapeamento."""
    visiveis = [ch for ch in texto if not ch.isspace()]
    if not visiveis:
        return False
    letras = sum(ch.isalpha() for ch in visiveis)
    palavras = [p for p in re.findall(r"[^\W\d_]{3,}", texto)
                if re.search(r"[aeiouáéíóúâêôãõ]", p, re.I)]
    return letras / len(visiveis) >= 0.6 and len(palavras) >= 2


def _ler_bytes(source: Union[str, Path, bytes, Any]) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    pos = source.tell() if hasattr(source, "tell") else None
    dados = source.read()
    if pos is not None and hasattr(source, "seek"):
        source.seek(pos)
    return dados


def _pela_renderizacao(dados: bytes) -> Tuple[str, List[HiddenSpan], int]:
    from polar_sentinel.reference.pdf_percepcao import agrupar, perceber_pdf, texto_visivel

    paginas = perceber_pdf(dados)
    textos: List[str] = []
    ocultos: List[HiddenSpan] = []
    for p in paginas:
        texto = texto_visivel(p)
        ocultos.extend(HiddenSpan(t["pagina"], t["texto"], t["motivo"], t["medidas"])
                       for t in agrupar(p) if t["motivo"] != "camada_ocr")
        if p.imagem is not None:
            # Pagina so de imagem (digitalizado sem camada de texto): o que se le
            # nela e o texto visivel da pagina.
            if not texto.strip():
                texto = p.imagem.visible_text
            ocultos.extend(HiddenSpan(p.numero, t.texto, "imagem_" + t.motivo, t.medidas)
                           for t in p.imagem.hidden_spans)
        textos.append(texto)
    return "\n".join(textos), ocultos, len(paginas)


def _pelo_conteudo(dados: bytes) -> Tuple[str, List[HiddenSpan], int]:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(dados))
    visible: List[str] = []
    hidden: List[HiddenSpan] = []
    for number, page in enumerate(reader.pages, start=1):
        box = page.mediabox
        state = _PageState(number, float(box.width), float(box.height))
        page.extract_text(visitor_operand_before=state.on_operator, visitor_text=state.on_text)
        visible.append("".join(state.visible))
        hidden.extend(state.hidden)
    return "\n".join(visible), hidden, len(reader.pages)


def inspect_pdf(source: Union[str, Path, Any], motor: Optional[str] = None) -> PdfInspection:
    """Le um PDF e separa o texto visivel do texto oculto.

    `motor` escolhe "renderizacao" (pypdfium2 e numpy) ou "conteudo" (so
    pypdf); sem escolha, usa a renderizacao quando estiver instalada.
    """
    from polar_sentinel.reference.pdf_percepcao import disponivel

    dados = _ler_bytes(source)
    if motor is None:
        motor = "renderizacao" if disponivel() else "conteudo"
    leitor = _pela_renderizacao if motor == "renderizacao" else _pelo_conteudo
    visible, hidden, paginas = leitor(dados)
    achados = inspecionar_estrutura(dados)
    metadata = " ".join(a.texto for a in achados if a.tipo == "metadado")
    return PdfInspection(visible_text=visible, hidden_spans=hidden, metadata_text=metadata,
                         achados=achados, motor=motor, paginas=paginas)


def evaluate_pdf(source: Union[str, Path, Any], stage: str = "entrada",
                 motor: Optional[str] = None) -> PdfVerdict:
    """Decide se um PDF deve ser sinalizado, olhando texto visivel, oculto e o resto do arquivo."""
    from polar_sentinel.harness.orchestration import create_judicial_orchestrator

    inspection = inspect_pdf(source, motor=motor)
    reasons: List[str] = []
    atencao: List[str] = []

    orchestrator = create_judicial_orchestrator(include_provenance=False)
    result = orchestrator.run(inspection.visible_text, context={"stage": stage, "source": "pdf"})
    if result.blocked or result.score > orchestrator.risk_threshold:
        reasons.append("comando_no_texto_visivel")

    by_reason: Dict[str, List[str]] = {}
    for span in inspection.hidden_spans:
        by_reason.setdefault(span.reason, []).append(span.text)
    for reason, parts in by_reason.items():
        text = " ".join(p.strip() for p in parts)
        letters = sum(ch.isalpha() for ch in text)
        claro = desofuscado(text)
        legivel = parece_texto(text) or parece_texto(claro)
        if (reason == "fonte_minuscula" and sum(ch.isalpha() for ch in claro) >= _MIN_LETTERS
                and legivel and not _GERADOR.search(fold(text))):
            reasons.append("texto_em_fonte_minuscula")
        elif tem_ordem(text, stage) and (reason != "imagem_baixo_contraste"
                                          or dirigido_a_ia(text, stage)):
            # Captura de tela em peca traz botao cinza ("Ver resumo", "Saiba mais"):
            # em imagem de contraste baixo, mas visivel, so vale ordem dirigida a IA.
            reasons.append(f"ordem_em_texto_oculto ({reason})")
        elif _invisivel_em_imagem(reason, text):
            reasons.append(f"texto_invisivel_legivel_por_maquina ({reason})")
        elif (max(letters, sum(ch.isalpha() for ch in claro)) >= _MIN_LETTERS and legivel
              and not reason.endswith("baixo_contraste")):
            atencao.append(f"texto_oculto_sem_ordem ({reason})")

    # Somado entre as formas: partir o texto entre cor do fundo, transparencia e
    # recorte nao o deixa abaixo do limite.
    invisivel_partes = _sem_repeticao([t for r, partes in by_reason.items()
                                       if r in INVISIVEL_DE_FATO for t in partes])
    tarjados = [t for t in invisivel_partes if dado_pessoal(t)]
    if tarjados and not tem_ordem(" ".join(tarjados), stage):
        # Tarja branca ou preta sobre a qualificacao da parte: a pessoa nao le o
        # CPF, a maquina le. E falha de anonimizacao, nao ordem a IA.
        atencao.append("tarja_que_nao_apaga")
        invisivel_partes = [t for t in invisivel_partes if not dado_pessoal(t)]
    # Carimbo de assinatura do PJe e do e-SAJ posto na margem ou fora da folha, e
    # nota de rodape coberta por figura mal posicionada no Word.
    for padrao, aviso in ((_CARIMBO, "carimbo_de_sistema_fora_da_vista"),
                          (_REFERENCIA, "referencia_bibliografica_coberta")):
        achados = [t for t in invisivel_partes if padrao.search(fold(t))]
        if achados and not tem_ordem(" ".join(achados), stage):
            atencao.append(aviso)
            invisivel_partes = [t for t in invisivel_partes if not padrao.search(fold(t))]
    invisivel = " ".join(invisivel_partes)
    if (parece_frase(invisivel)
            and not any(r.startswith(("ordem_em_texto_oculto", "texto_invisivel")) for r in reasons)):
        formas = ", ".join(sorted(r for r in by_reason if r in INVISIVEL_DE_FATO))
        reasons.append(f"texto_invisivel_legivel_por_maquina ({formas})")

    oculto = " ".join(t for partes in by_reason.values() for t in partes)
    if ofuscado(oculto) and not any(r.startswith(("ordem_em_texto_oculto", "texto_invisivel"))
                                    for r in reasons):
        reasons.append("texto_oculto_ofuscado")

    for achado in inspection.achados:
        if achado.tipo == "arquivo_embutido" and achado.detalhe.get("pdf"):
            interno = evaluate_pdf(achado.detalhe.pop("inspecao"), stage, motor)
            achado.detalhe["sinalizado"] = interno.flagged
            if interno.flagged:
                reasons.append("ordem_em_arquivo_embutido")
            continue
        if achado.tipo == "texto_substituto":
            # Legitimo quando repete o que a pagina mostra (acessibilidade); o
            # contrario e a pagina mostrar uma coisa e o extrator entregar outra.
            glifos = achado.detalhe.pop("glifos", "")
            achado.detalhe["diverge"] = desofuscado(achado.texto).replace(" ", "") not in (
                desofuscado(glifos).replace(" ", ""))
            if not achado.detalhe["diverge"]:
                continue
            if not tem_ordem(achado.texto, stage) and parece_frase(achado.texto):
                reasons.append("texto_invisivel_legivel_por_maquina (texto_substituto)")
            elif not tem_ordem(achado.texto, stage):
                atencao.append("texto_substituto_divergente")
        if achado.tipo == "link":
            # "?utm_source=chatgpt.com" so diz de onde o advogado copiou o link.
            achado.texto = re.sub(r"[?&]utm_[a-z]+=[^&#\s]*", "", achado.texto)
        sinal = _CANAIS_COM_TEXTO.get(achado.tipo)
        if sinal and achado.texto and tem_ordem(achado.texto, stage):
            # Metadado e endereco de link sao cheios de substantivos que tambem sao
            # imperativos ("informe", "destaque"); ali so vale ordem dirigida a IA.
            if (not achado.tipo.startswith("metadado") and achado.tipo != "link"
                    or dirigido_a_ia(achado.texto, stage)):
                reasons.append(sinal)
        if achado.tipo in ("javascript", "arquivo_embutido", "camada_desligada"):
            atencao.append(achado.tipo)
        elif achado.tipo == "anotacao" and achado.detalhe.get("oculta"):
            atencao.append("anotacao_oculta")

    tudo = "\n".join([inspection.visible_text, *(s.text for s in inspection.hidden_spans),
                      *(a.texto for a in inspection.achados)])
    limpeza = sanitize_with_audit(tudo, source="pdf")
    if limpeza.suspicious:
        if limpeza.hidden_text and tem_ordem(limpeza.hidden_text, stage):
            reasons.append("ordem_em_unicode_invisivel")
        else:
            atencao.append("unicode_invisivel")

    return PdfVerdict(flagged=bool(reasons), reasons=list(dict.fromkeys(reasons)),
                      inspection=inspection, atencao=list(dict.fromkeys(atencao)))
