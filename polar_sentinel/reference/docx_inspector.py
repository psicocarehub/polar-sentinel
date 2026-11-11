"""Polar Sentinel: o que um .docx esconde de quem le no Word.

O .docx e um zip de XML. A IA que recebe o arquivo, ou o texto extraido dele,
le o XML; a pessoa ve o que o Word desenha. Este modulo separa os dois.

Trechos ocultos no corpo, nos cabecalhos, nos rodapes e nas notas:

    oculto               propriedade "oculto" (w:vanish), no trecho ou no estilo
    cor_do_fundo         cor da letra igual a do sombreamento, do realce ou do
                         fundo da pagina (branco por padrao)
    fonte_minuscula      menos de 2 pontos
    texto_excluido       texto apagado com controle de alteracoes ligado: some
                         da tela, mas continua no arquivo

Canais fora do corpo (Achado, como no PDF):

    comentario, texto_alternativo, codigo_de_campo, xml_personalizado,
    bloco_de_construcao, objeto_embutido, macro, metadado

So usa a biblioteca padrao. Nao interpreta todas as regras de heranca do Word
(tema, estilo de tabela, formatacao condicional); o que nao interpreta, trata
como visivel.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from xml.etree import ElementTree as ET

from polar_sentinel.reference.pdf_estrutura import Achado

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"

_PARTES_DE_TEXTO = re.compile(r"word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$")
_MIN_MEIOS_PONTOS = 4  # w:sz e em meios pontos: 4 = 2 pontos
_MESMA_COR = 0.1
_CORES_DE_REALCE = {
    "yellow": "FFFF00",
    "green": "00FF00",
    "cyan": "00FFFF",
    "magenta": "FF00FF",
    "blue": "0000FF",
    "red": "FF0000",
    "darkBlue": "000080",
    "darkCyan": "008080",
    "darkGreen": "008000",
    "darkMagenta": "800080",
    "darkRed": "800000",
    "darkYellow": "808000",
    "darkGray": "808080",
    "lightGray": "C0C0C0",
    "black": "000000",
    "white": "FFFFFF",
}


@dataclass
class TrechoDocx:
    """Um trecho que o Word nao mostra."""

    parte: str
    texto: str
    motivo: str
    medidas: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocxInspection:
    visible_text: str
    hidden_spans: List[TrechoDocx] = field(default_factory=list)
    achados: List[Achado] = field(default_factory=list)


def _rgb(hexa: Optional[str]) -> Optional[Tuple[float, float, float]]:
    if not hexa or hexa.lower() == "auto" or not re.fullmatch(r"[0-9A-Fa-f]{6}", hexa):
        return None
    return tuple(int(hexa[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _ligado(elem: Optional[ET.Element]) -> bool:
    if elem is None:
        return False
    return elem.get(f"{W}val", "true").lower() not in ("0", "false", "off")


class _Estilos:
    """Propriedades de letra de cada estilo, com a heranca por basedOn."""

    def __init__(self, xml: Optional[bytes]) -> None:
        self.rpr: Dict[str, Dict[str, Any]] = {}
        self.base: Dict[str, str] = {}
        self.padrao: Dict[str, Any] = {}
        if not xml:
            return
        raiz = ET.fromstring(xml)
        defaults = raiz.find(f"{W}docDefaults/{W}rPrDefault/{W}rPr")
        if defaults is not None:
            self.padrao = _props(defaults)
        for estilo in raiz.iter(f"{W}style"):
            nome = estilo.get(f"{W}styleId", "")
            base = estilo.find(f"{W}basedOn")
            if base is not None:
                self.base[nome] = base.get(f"{W}val", "")
            rpr = estilo.find(f"{W}rPr")
            self.rpr[nome] = _props(rpr) if rpr is not None else {}

    def de(self, nome: Optional[str]) -> Dict[str, Any]:
        cadeia: List[Dict[str, Any]] = []
        vistos = set()
        while nome and nome not in vistos:
            vistos.add(nome)
            cadeia.append(self.rpr.get(nome, {}))
            nome = self.base.get(nome)
        saida = dict(self.padrao)
        for props in reversed(cadeia):
            saida.update(props)
        return saida


def _props(rpr: ET.Element) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    for tag in ("vanish", "specVanish", "webHidden"):
        elem = rpr.find(f"{W}{tag}")
        if elem is not None:
            props["oculto"] = _ligado(elem)
    cor = rpr.find(f"{W}color")
    if cor is not None and cor.get(f"{W}val"):
        props["cor"] = cor.get(f"{W}val")
    tamanho = rpr.find(f"{W}sz")
    if tamanho is not None and (tamanho.get(f"{W}val") or "").isdigit():
        props["sz"] = int(tamanho.get(f"{W}val"))
    sombra = rpr.find(f"{W}shd")
    if sombra is not None and _rgb(sombra.get(f"{W}fill")):
        props["fundo"] = sombra.get(f"{W}fill")
    realce = rpr.find(f"{W}highlight")
    if realce is not None and realce.get(f"{W}val") in _CORES_DE_REALCE:
        props["fundo"] = _CORES_DE_REALCE[realce.get(f"{W}val")]
    return props


def _texto_do_run(run: ET.Element) -> str:
    partes = []
    for filho in run:
        if filho.tag in (f"{W}t", f"{W}delText"):
            partes.append(filho.text or "")
        elif filho.tag == f"{W}tab":
            partes.append("\t")
        elif filho.tag in (f"{W}br", f"{W}cr"):
            partes.append("\n")
    return "".join(partes)


def _motivo(props: Dict[str, Any], fundo_pagina: str) -> Tuple[str, Dict[str, Any]]:
    medidas = {"cor_texto": props.get("cor", "auto"), "cor_fundo": props.get("fundo", fundo_pagina)}
    if "sz" in props:
        medidas["tamanho_pt"] = props["sz"] / 2
    if props.get("oculto"):
        return "oculto", medidas
    if "sz" in props and props["sz"] < _MIN_MEIOS_PONTOS:
        return "fonte_minuscula", medidas
    texto, fundo = _rgb(props.get("cor")), _rgb(props.get("fundo", fundo_pagina))
    if texto and fundo and all(abs(a - b) <= _MESMA_COR for a, b in zip(texto, fundo)):
        return "cor_do_fundo", medidas
    return "", medidas


def _ler_parte(
    xml: bytes,
    parte: str,
    estilos: _Estilos,
    fundo_pagina: str,
    visivel: List[str],
    ocultos: List[TrechoDocx],
    achados: List[Achado],
) -> None:
    raiz = ET.fromstring(xml)
    pais = {filho: pai for pai in raiz.iter() for filho in pai}

    for doc_pr in raiz.iter(f"{WP}docPr"):
        alt = " ".join(v for v in (doc_pr.get("title"), doc_pr.get("descr")) if v)
        if alt.strip():
            achados.append(Achado("texto_alternativo", alt, None, {"parte": parte}))
    instrucoes = " ".join((e.text or "") for e in raiz.iter(f"{W}instrText")).strip()
    if instrucoes:
        achados.append(Achado("codigo_de_campo", instrucoes, None, {"parte": parte}))

    for paragrafo in raiz.iter(f"{W}p"):
        ppr = paragrafo.find(f"{W}pPr")
        estilo_p = None
        fundo_p = None
        if ppr is not None:
            ps = ppr.find(f"{W}pStyle")
            estilo_p = ps.get(f"{W}val") if ps is not None else None
            sombra = ppr.find(f"{W}shd")
            if sombra is not None and _rgb(sombra.get(f"{W}fill")):
                fundo_p = sombra.get(f"{W}fill")
        celula = paragrafo
        while celula in pais and celula.tag != f"{W}tc":
            celula = pais[celula]
        if celula.tag == f"{W}tc":
            sombra = celula.find(f"{W}tcPr/{W}shd")
            if fundo_p is None and sombra is not None and _rgb(sombra.get(f"{W}fill")):
                fundo_p = sombra.get(f"{W}fill")

        for run in paragrafo.iter(f"{W}r"):
            dono = pais.get(run)
            while dono is not None and dono.tag != f"{W}p":
                dono = pais.get(dono)
            if dono is not paragrafo:  # run de uma caixa de texto, lido no paragrafo dela
                continue
            texto = _texto_do_run(run)
            if not texto:
                continue
            props = estilos.de(estilo_p)
            rpr = run.find(f"{W}rPr")
            if rpr is not None:
                rs = rpr.find(f"{W}rStyle")
                if rs is not None:
                    props.update(estilos.de(rs.get(f"{W}val")))
                props.update(_props(rpr))
            if fundo_p and "fundo" not in props:
                props["fundo"] = fundo_p
            excluido = pais.get(run) is not None and pais[run].tag == f"{W}del"
            motivo, medidas = ("texto_excluido", {}) if excluido else _motivo(props, fundo_pagina)
            if motivo:
                if ocultos and ocultos[-1].parte == parte and ocultos[-1].motivo == motivo:
                    ocultos[-1].texto += texto
                else:
                    ocultos.append(TrechoDocx(parte, texto, motivo, medidas))
            else:
                visivel.append(texto)
        visivel.append("\n")


def _metadados(arquivo: zipfile.ZipFile) -> List[Achado]:
    achados = []
    for nome in ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"):
        if nome in arquivo.namelist():
            texto = " ".join(
                " ".join(e.text or "" for e in ET.fromstring(arquivo.read(nome)).iter()).split()
            )
            if texto:
                achados.append(Achado("metadado", texto, None, {"origem": nome}))
    return achados


def inspect_docx(source: Union[str, Path, bytes, Any]) -> DocxInspection:
    """Le um .docx e separa o que o Word mostra do que esta so no arquivo."""
    if isinstance(source, (str, Path)):
        dados = Path(source).read_bytes()
    elif isinstance(source, (bytes, bytearray)):
        dados = bytes(source)
    else:
        dados = source.read()
    arquivo = zipfile.ZipFile(io.BytesIO(dados))
    nomes = arquivo.namelist()
    estilos = _Estilos(arquivo.read("word/styles.xml") if "word/styles.xml" in nomes else None)

    fundo_pagina = "FFFFFF"
    if "word/document.xml" in nomes:
        fundo = ET.fromstring(arquivo.read("word/document.xml")).find(f"{W}background")
        if fundo is not None and _rgb(fundo.get(f"{W}color")):
            fundo_pagina = fundo.get(f"{W}color")

    visivel: List[str] = []
    ocultos: List[TrechoDocx] = []
    achados: List[Achado] = []
    partes = sorted(
        (n for n in nomes if _PARTES_DE_TEXTO.match(n)), key=lambda n: (n != "word/document.xml", n)
    )
    for parte in partes:
        _ler_parte(arquivo.read(parte), parte, estilos, fundo_pagina, visivel, ocultos, achados)

    if "word/comments.xml" in nomes:
        raiz = ET.fromstring(arquivo.read("word/comments.xml"))
        for comentario in raiz.iter(f"{W}comment"):
            texto = "".join(t.text or "" for t in comentario.iter(f"{W}t")).strip()
            if texto:
                achados.append(
                    Achado("comentario", texto, None, {"autor": comentario.get(f"{W}author", "")})
                )
    for nome in nomes:
        if nome.startswith("customXml/item") and nome.endswith(".xml") and "Props" not in nome:
            texto = " ".join(
                " ".join(e.text or "" for e in ET.fromstring(arquivo.read(nome)).iter()).split()
            )
            if texto:
                achados.append(Achado("xml_personalizado", texto, None, {"parte": nome}))
        elif nome.startswith("word/glossary/") and nome.endswith("document.xml"):
            raiz = ET.fromstring(arquivo.read(nome))
            texto = " ".join("".join(t.text or "" for t in raiz.iter(f"{W}t")).split())
            if texto:
                achados.append(Achado("bloco_de_construcao", texto, None, {"parte": nome}))
        elif nome.startswith("word/embeddings/"):
            achados.append(
                Achado(
                    "objeto_embutido",
                    "",
                    None,
                    {"parte": nome, "bytes": arquivo.getinfo(nome).file_size},
                )
            )
        elif nome.endswith("vbaProject.bin"):
            achados.append(Achado("macro", "", None, {"parte": nome}))
    achados.extend(_metadados(arquivo))

    for trecho in ocultos:
        trecho.texto = " ".join(trecho.texto.split())
    texto_visivel = re.sub(r"\n{3,}", "\n\n", "".join(visivel))
    return DocxInspection(texto_visivel, [t for t in ocultos if t.texto], achados)


@dataclass
class DocxVerdict:
    flagged: bool
    reasons: List[str]
    inspection: DocxInspection
    atencao: List[str] = field(default_factory=list)


_CANAIS = {
    "comentario": "ordem_em_comentario",
    "texto_alternativo": "ordem_em_texto_alternativo",
    "codigo_de_campo": "ordem_em_codigo_de_campo",
    "xml_personalizado": "ordem_em_xml_personalizado",
    "bloco_de_construcao": "ordem_em_bloco_de_construcao",
    "metadado": "comando_em_metadado",
}


def evaluate_docx(source: Union[str, Path, bytes, Any], stage: str = "entrada") -> DocxVerdict:
    """Decide se um .docx deve ser sinalizado, com as mesmas regras do PDF."""
    from polar_sentinel.harness.orchestration import create_judicial_orchestrator
    from polar_sentinel.reference.pdf_inspector import (
        _MIN_LETTERS,
        dirigido_a_ia,
        parece_texto,
        tem_ordem,
    )
    from polar_sentinel.reference.sanitizer import sanitize_with_audit

    inspection = inspect_docx(source)
    reasons: List[str] = []
    atencao: List[str] = []
    orquestrador = create_judicial_orchestrator(include_provenance=False)
    resultado = orquestrador.run(
        inspection.visible_text, context={"stage": stage, "source": "docx"}
    )
    if resultado.blocked or resultado.score > orquestrador.risk_threshold:
        reasons.append("comando_no_texto_visivel")

    por_motivo: Dict[str, List[str]] = {}
    for trecho in inspection.hidden_spans:
        por_motivo.setdefault(trecho.motivo, []).append(trecho.texto)
    for motivo, partes in por_motivo.items():
        texto = " ".join(partes)
        letras = sum(ch.isalpha() for ch in texto)
        if motivo == "fonte_minuscula" and letras >= _MIN_LETTERS and parece_texto(texto):
            reasons.append("texto_em_fonte_minuscula")
        elif tem_ordem(texto, stage):
            reasons.append(f"ordem_em_texto_oculto ({motivo})")
        elif letras >= _MIN_LETTERS and motivo != "texto_excluido":
            atencao.append(f"texto_oculto_sem_ordem ({motivo})")

    for achado in inspection.achados:
        sinal = _CANAIS.get(achado.tipo)
        if sinal and achado.texto and tem_ordem(achado.texto, stage):
            if achado.tipo != "metadado" or dirigido_a_ia(achado.texto, stage):
                reasons.append(sinal)
        if achado.tipo in ("macro", "objeto_embutido"):
            atencao.append(achado.tipo)

    tudo = "\n".join(
        [
            inspection.visible_text,
            *(t.texto for t in inspection.hidden_spans),
            *(a.texto for a in inspection.achados),
        ]
    )
    limpeza = sanitize_with_audit(tudo, source="docx")
    if limpeza.suspicious:
        if limpeza.hidden_text and tem_ordem(limpeza.hidden_text, stage):
            reasons.append("ordem_em_unicode_invisivel")
        else:
            atencao.append("unicode_invisivel")
    return DocxVerdict(
        bool(reasons), list(dict.fromkeys(reasons)), inspection, list(dict.fromkeys(atencao))
    )
