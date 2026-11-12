"""Polar Sentinel: o que o PDF carrega fora do texto da pagina.

Ferramentas de IA que recebem o arquivo inteiro leem mais do que a pagina
mostra. Este modulo lista esses canais, com o texto de cada um:

    anotacao             comentarios, notas, caixas de texto (inclusive ocultas)
    campo_de_formulario  valor e dica de campos, visiveis ou nao
    camada_desligada     camadas opcionais que comecam desligadas
    arquivo_embutido     anexos dentro do PDF (PDF anexado e inspecionado)
    javascript           codigo que roda ao abrir ou ao clicar
    link                 enderecos de links
    metadado             dicionario de informacoes e XMP
    revisoes             quantas vezes o arquivo foi salvo por acrescimo

Nada aqui decide sozinho: os textos voltam para `evaluate_pdf`, que procura
ordem dirigida a IA em cada canal. Precisa de pypdf.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_TAGS = re.compile(r"<[^>]+>")
# Bits do campo /F de anotacao: 2 oculta, 6 nao exibir.
_ANOT_OCULTA = 0b10
_ANOT_NAO_EXIBE = 0b100000
_EXTENSOES_TEXTO = (".txt", ".csv", ".xml", ".html", ".htm", ".json", ".md", ".rtf")


@dataclass
class Achado:
    """Um canal do arquivo com o texto que ele carrega."""

    tipo: str
    texto: str
    pagina: Optional[int] = None
    detalhe: Dict[str, Any] = field(default_factory=dict)


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    try:
        valor = valor.get_object()
    except AttributeError:
        pass
    if isinstance(valor, bytes):
        valor = valor.decode("utf-8", "replace")
    return _TAGS.sub(" ", str(valor)).strip()


def _javascript_de(acao: Any) -> str:
    try:
        acao = acao.get_object()
    except AttributeError:
        return ""
    if not hasattr(acao, "get") or acao.get("/S") != "/JavaScript":
        return ""
    codigo = acao.get("/JS")
    try:
        codigo = codigo.get_object()
        if hasattr(codigo, "get_data"):
            return codigo.get_data().decode("utf-8", "replace")
    except AttributeError:
        pass
    return _texto(codigo)


def _anotacoes(reader) -> List[Achado]:
    achados: List[Achado] = []
    for numero, page in enumerate(reader.pages, start=1):
        for ref in page.get("/Annots") or []:
            anot = ref.get_object()
            subtipo = str(anot.get("/Subtype", "")).lstrip("/")
            flags = int(anot.get("/F", 0) or 0)
            oculta = bool(flags & (_ANOT_OCULTA | _ANOT_NAO_EXIBE))
            acao = anot.get("/A")
            js = _javascript_de(acao) if acao is not None else ""
            if js:
                achados.append(Achado("javascript", js, numero, {"origem": f"anotacao {subtipo}"}))
            if subtipo == "Link":
                alvo = acao.get_object() if acao is not None else None
                uri = _texto(alvo.get("/URI")) if hasattr(alvo, "get") else ""
                if uri:
                    achados.append(Achado("link", uri, numero))
                continue
            partes = [_texto(anot.get(k)) for k in ("/Contents", "/RC", "/Subj", "/TU")]
            if subtipo == "Widget":
                valor = anot.get("/V")
                pai = anot.get("/Parent")
                if valor is None and pai is not None:
                    valor = pai.get_object().get("/V")
                partes.append(_texto(valor))
                tipo = "campo_de_formulario"
            else:
                tipo = "anotacao"
            texto = " ".join(p for p in partes if p and p != "None")
            if texto:
                achados.append(Achado(tipo, texto, numero, {"subtipo": subtipo, "oculta": oculta}))
    return achados


def _camadas_desligadas(reader) -> List[Achado]:
    raiz = reader.trailer["/Root"]
    props = raiz.get("/OCProperties")
    if props is None:
        return []
    padrao = props.get_object().get("/D")
    desligadas = (padrao.get_object().get("/OFF") if padrao is not None else None) or []
    nomes = [_texto(ref.get_object().get("/Name")) for ref in desligadas]
    if not nomes:
        return []
    return [Achado("camada_desligada", " ".join(nomes), None, {"camadas": nomes})]


def _javascript_do_documento(reader) -> List[Achado]:
    raiz = reader.trailer["/Root"]
    achados: List[Achado] = []
    abrir = raiz.get("/OpenAction")
    js = _javascript_de(abrir) if abrir is not None else ""
    if js:
        achados.append(Achado("javascript", js, None, {"origem": "ao abrir"}))
    nomes = raiz.get("/Names")
    arvore = nomes.get_object().get("/JavaScript") if nomes is not None else None
    if arvore is not None:
        pares = arvore.get_object().get("/Names") or []
        for i in range(1, len(pares), 2):
            js = _javascript_de(pares[i])
            if js:
                achados.append(Achado("javascript", js, None, {"origem": _texto(pares[i - 1])}))
    for numero, page in enumerate(reader.pages, start=1):
        aa = page.get("/AA")
        if aa is not None:
            for gatilho, acao in aa.get_object().items():
                js = _javascript_de(acao)
                if js:
                    achados.append(
                        Achado("javascript", js, numero, {"origem": f"pagina {gatilho}"})
                    )
    return achados


def _embutidos(reader, profundidade: int) -> List[Achado]:
    achados: List[Achado] = []
    try:
        anexos = reader.attachments
    except Exception:  # noqa: BLE001 - arvore de nomes malformada
        return achados
    for nome, conteudos in anexos.items():
        for dados in conteudos:
            detalhe: Dict[str, Any] = {"nome": nome, "bytes": len(dados)}
            texto = ""
            if dados[:5] == b"%PDF-" and profundidade > 0:
                detalhe["pdf"] = True
                detalhe["inspecao"] = dados
            elif nome.lower().endswith(_EXTENSOES_TEXTO):
                texto = dados.decode("utf-8", "replace")
            achados.append(Achado("arquivo_embutido", texto, None, detalhe))
    return achados


def _metadados(reader) -> List[Achado]:
    achados: List[Achado] = []
    info = " ".join(_texto(v) for v in (reader.metadata or {}).values() if v)
    if info:
        achados.append(Achado("metadado", info, None, {"origem": "info"}))
    meta = reader.trailer["/Root"].get("/Metadata")
    if meta is not None:
        try:
            xmp = meta.get_object().get_data().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            xmp = ""
        texto = " ".join(_TAGS.sub(" ", xmp).split())
        if texto:
            achados.append(Achado("metadado", texto, None, {"origem": "xmp"}))
    return achados


def _metadados_de_imagens(reader) -> List[Achado]:
    """Comentario, EXIF e XMP dos JPEG embutidos nas paginas."""
    try:
        from PIL import Image

        from polar_sentinel.reference.imagem_inspector import metadados_da_imagem
    except ImportError:
        return []
    achados: List[Achado] = []
    for numero, page in enumerate(reader.pages, start=1):
        recursos = page.get("/Resources")
        xobjetos = recursos.get_object().get("/XObject") if recursos is not None else None
        if xobjetos is None:
            continue
        for nome, ref in xobjetos.get_object().items():
            objeto = ref.get_object()
            filtro = objeto.get("/Filter")
            filtros = filtro if isinstance(filtro, list) else [filtro]
            if objeto.get("/Subtype") != "/Image" or "/DCTDecode" not in [str(f) for f in filtros]:
                continue
            try:
                imagem = Image.open(io.BytesIO(objeto.get_data()))
            except Exception:  # noqa: BLE001
                continue
            for a in metadados_da_imagem(imagem):
                achados.append(
                    Achado(
                        "metadado_de_imagem", a.texto, numero, {**a.detalhe, "imagem": str(nome)}
                    )
                )
    return achados


def inspecionar_estrutura(dados: bytes, profundidade: int = 1) -> List[Achado]:
    """Lista os canais fora do texto da pagina. `dados` e o PDF em bytes."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(dados))
    achados: List[Achado] = []
    coletores = (
        _anotacoes,
        _camadas_desligadas,
        _javascript_do_documento,
        _metadados,
        _metadados_de_imagens,
    )
    for coletor in coletores:
        try:
            achados.extend(coletor(reader))
        except Exception as exc:  # noqa: BLE001 - PDF malformado nao derruba a inspecao
            achados.append(
                Achado("erro_de_leitura", "", None, {"coletor": coletor.__name__, "erro": str(exc)})
            )
    achados.extend(_embutidos(reader, profundidade))
    revisoes = dados.count(b"%%EOF")
    if revisoes > 1:
        achados.append(Achado("revisoes", "", None, {"quantidade": revisoes}))
    return achados
