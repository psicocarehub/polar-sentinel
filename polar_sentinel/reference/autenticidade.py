"""Polar Sentinel: integridade e proveniencia de prova digital.

Responde a uma pergunta mais estreita que "isto e verdadeiro?": o arquivo e o
mesmo que foi assinado, ou declarado, por quem o assinou? A resposta tem tres
saidas, e "inconclusivo" e uma delas:

    integridade_confirmada  assinatura valida, sem alteracao do conteudo depois
                            dela (o que foi assinado e o que se ve)
    alteracao_detectada     o arquivo mudou depois da assinatura ou do
                            manifesto de proveniencia, de um jeito que muda o que
                            se ve, ou o hash nao confere
    inconclusivo            nao ha assinatura nem manifesto, ou a cadeia nao
                            fecha numa raiz confiavel: o arquivo nao prova nada
                            sozinho, nem a favor nem contra

PDF assinado (pyHanko): valida cada assinatura (hash, criptografia, cadeia
ate as raizes da ICP-Brasil que vem no pacote, ou as que o usuario passar), le
o nivel de modificacao depois de cada uma e, quando ha revisao posterior,
desenha a pagina como estava assinada e como esta agora e aponta onde mudou.
Atualizacao de validacao de longo prazo (LTV) e assinatura posterior nao
contam como alteracao. Ataques de sombra e de aparencia em PDF assinado
(Mainka et al., NDSS 2021; LabSEC/UFSC, 2026) aparecem aqui como diferenca
visual depois da assinatura.

Imagem, video e audio (C2PA, pelo leitor oficial c2pa-python): presenca,
validade, quem assinou o manifesto e se ele declara geracao por IA. A ausencia
de manifesto nao e indicio de nada.

A revogacao dos certificados so e consultada com `buscar_na_rede=True`.
Precisa de pyhanko (PDF) e de c2pa-python (midia).
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

# Fracao minima de pixels diferentes numa pagina para contar como alteracao visual.
_DIFERENCA_MINIMA = 0.0005
# Tipos de origem que o C2PA usa para conteudo gerado por IA.
_GERADO_POR_IA = (
    "trainedAlgorithmicMedia",
    "compositeWithTrainedAlgorithmicMedia",
    "algorithmicMedia",
)


MODIFICACAO = {
    "NONE": "nenhuma",
    "LTA_UPDATES": "só atualização de validação de longo prazo",
    "FORM_FILLING": "preenchimento de formulário",
    "ANNOTATIONS": "anotações",
    "OTHER": "alteração de conteúdo",
}


@dataclass
class Laudo:
    conclusao: str
    arquivo: Dict[str, Any]
    assinaturas: List[Dict[str, Any]] = field(default_factory=list)
    alteracoes_visuais: List[Dict[str, Any]] = field(default_factory=list)
    proveniencia: Dict[str, Any] = field(default_factory=dict)
    observacoes: List[str] = field(default_factory=list)


def raizes_icp_brasil() -> List[Any]:
    """Raizes v5, v10, v11 e v12 da ICP-Brasil, publicadas pelo ITI."""
    from pyhanko.keys import load_cert_from_pemder

    pasta = resources.files("polar_sentinel.reference") / "icp_brasil"
    certificados = []
    for item in sorted(pasta.iterdir(), key=lambda p: p.name):
        if item.name.endswith(".pem"):
            with resources.as_file(item) as caminho:
                certificados.append(load_cert_from_pemder(str(caminho)))
    return certificados


def _paginas_renderizadas(dados: bytes, escala: float = 1.0) -> List[Any]:
    import numpy as np
    import pypdfium2 as pdfium

    documento = pdfium.PdfDocument(io.BytesIO(dados))
    try:
        return [
            np.asarray(documento[i].render(scale=escala).to_pil().convert("L"))
            for i in range(len(documento))
        ]
    finally:
        documento.close()


def _retangulos_de_assinatura(dados: bytes) -> Dict[int, List[Sequence[float]]]:
    """Retangulos (em pontos) dos campos de assinatura, por pagina (0 em diante)."""
    from pypdf import PdfReader

    leitor = PdfReader(io.BytesIO(dados))
    saida: Dict[int, List[Sequence[float]]] = {}
    for numero, pagina in enumerate(leitor.pages):
        for ref in pagina.get("/Annots") or []:
            anot = ref.get_object()
            campo = anot if anot.get("/FT") else (anot.get("/Parent") or {})
            if hasattr(campo, "get_object"):
                campo = campo.get_object()
            if campo.get("/FT") == "/Sig" and anot.get("/Rect"):
                saida.setdefault(numero, []).append([float(v) for v in anot["/Rect"]])
    return saida


def diferencas_visuais(
    antes: bytes, depois: bytes, ignorar: Dict[int, List[Sequence[float]]]
) -> List[Dict[str, Any]]:
    """Paginas que mudaram de aparencia entre duas revisoes, fora dos campos de assinatura."""
    import numpy as np

    escala = 1.0
    paginas_antes = _paginas_renderizadas(antes, escala)
    paginas_depois = _paginas_renderizadas(depois, escala)
    saida = []
    if len(paginas_depois) != len(paginas_antes):
        saida.append(
            {
                "pagina": None,
                "tipo": "numero_de_paginas",
                "antes": len(paginas_antes),
                "depois": len(paginas_depois),
            }
        )
    for i, (a, d) in enumerate(zip(paginas_antes, paginas_depois)):
        if a.shape != d.shape:
            saida.append({"pagina": i + 1, "tipo": "tamanho_da_pagina"})
            continue
        mudou = np.abs(a.astype(int) - d.astype(int)) > 24
        altura = a.shape[0]
        for x0, y0, x1, y1 in ignorar.get(i, []):
            mudou[
                int(altura - max(y0, y1) * escala) - 2 : int(altura - min(y0, y1) * escala) + 2,
                int(min(x0, x1) * escala) - 2 : int(max(x0, x1) * escala) + 2,
            ] = False
        fracao = float(mudou.mean())
        if fracao > _DIFERENCA_MINIMA:
            ys, xs = np.nonzero(mudou)
            saida.append(
                {
                    "pagina": i + 1,
                    "tipo": "conteudo",
                    "fracao_alterada": round(fracao, 4),
                    "regiao_pt": [
                        round(float(xs.min()) / escala, 1),
                        round(float(altura - ys.max()) / escala, 1),
                        round(float(xs.max()) / escala, 1),
                        round(float(altura - ys.min()) / escala, 1),
                    ],
                }
            )
    return saida


def _assinaturas_legadas(dados: bytes) -> List[Dict[str, Any]]:
    """Assinaturas que o pyHanko nao lista (dicionario direto, adbe.pkcs7.sha1, de 2006 e antes).

    Confere o hash: o conteudo assinado (ByteRange) contra o resumo guardado
    na estrutura CMS. Nao valida a assinatura nem a cadeia.
    """
    from asn1crypto import cms
    from pypdf import PdfReader

    leitor = PdfReader(io.BytesIO(dados))
    campos = leitor.trailer["/Root"].get("/AcroForm") or {}
    campos = campos.get_object().get("/Fields") if hasattr(campos, "get_object") else []
    saida = []
    for ref in campos or []:
        campo = ref.get_object()
        valor = campo.get("/V")
        if campo.get("/FT") != "/Sig" or valor is None:
            continue
        assinatura = valor.get_object()
        intervalo = [int(v) for v in assinatura.get("/ByteRange", [])]
        if len(intervalo) != 4:
            continue
        assinado = (
            dados[intervalo[0] : intervalo[0] + intervalo[1]]
            + dados[intervalo[2] : intervalo[2] + intervalo[3]]
        )
        registro: Dict[str, Any] = {
            "campo": str(campo.get("/T", "")),
            "formato": str(assinatura.get("/SubFilter", "")),
            "signatario": str(assinatura.get("/Name", "")),
            "data_declarada": str(assinatura.get("/M", "")),
            "bytes_assinados": intervalo[2] + intervalo[3],
            "bytes_depois": max(len(dados) - intervalo[2] - intervalo[3], 0),
            "validacao_criptografica": "não feita (formato legado)",
        }
        try:
            dados_cms = cms.ContentInfo.load(bytes(assinatura["/Contents"]).rstrip(b"\x00"))[
                "content"
            ]
            encapsulado = dados_cms["encap_content_info"]["content"].native
            info = dados_cms["signer_infos"][0]
            resumo = None
            if info["signed_attrs"].native:
                for atributo in info["signed_attrs"]:
                    if atributo["type"].native == "message_digest":
                        resumo = atributo["values"][0].native
            algoritmo = info["digest_algorithm"]["algorithm"].native
            alvo = encapsulado if encapsulado else resumo
            calculo = hashlib.new("sha1" if encapsulado else algoritmo, assinado).digest()
            registro["hash_confere"] = alvo == calculo
            certificados = dados_cms["certificates"]
            if certificados:
                registro["emissor"] = certificados[0].chosen.issuer.human_friendly
        except Exception as exc:  # noqa: BLE001
            registro.update({"hash_confere": False, "erro": f"{type(exc).__name__}: {exc}"[:200]})
        saida.append(registro)
    return saida


def _nome(certificado: Any) -> str:
    try:
        return certificado.subject.human_friendly
    except Exception:  # noqa: BLE001
        return str(certificado)


def verificar_pdf(
    dados: bytes, *, raizes: Optional[List[Any]] = None, buscar_na_rede: bool = False
) -> Laudo:
    """Valida as assinaturas de um PDF e aponta alteracoes depois delas."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    import logging

    logging.getLogger("pyhanko").setLevel(logging.CRITICAL)
    logging.getLogger("pyhanko_certvalidator").setLevel(logging.CRITICAL)
    laudo = Laudo("inconclusivo", _descricao(dados))
    leitor = PdfFileReader(io.BytesIO(dados), strict=False)
    assinaturas = list(leitor.embedded_signatures)
    if not assinaturas:
        legadas = _assinaturas_legadas(dados)
        if not legadas:
            laudo.observacoes.append(
                "O PDF não tem assinatura digital: sem elemento de integridade."
            )
            return laudo
        laudo.assinaturas = legadas
        if any(not a.get("hash_confere") for a in legadas):
            laudo.conclusao = "alteracao_detectada"
            laudo.observacoes.append("O hash assinado não confere com o arquivo.")
        else:
            laudo.observacoes.append(
                "Assinatura em formato legado: o hash assinado confere com o arquivo, mas a "
                "assinatura e a cadeia não foram validadas criptograficamente por esta ferramenta."
            )
        return laudo

    contexto = ValidationContext(
        trust_roots=raizes if raizes is not None else raizes_icp_brasil(),
        allow_fetching=buscar_na_rede,
    )
    retangulos = _retangulos_de_assinatura(dados)
    alterado = False
    confiaveis = 0
    for emb in assinaturas:
        registro: Dict[str, Any] = {"campo": emb.field_name}
        try:
            st = validate_pdf_signature(emb, contexto)
            registro.update(
                {
                    "hash_confere": bool(st.intact),
                    "assinatura_valida": bool(st.valid),
                    "cadeia_confiavel": bool(st.trusted),
                    "signatario": _nome(st.signing_cert),
                    "emissor": st.signing_cert.issuer.human_friendly,
                    "data_declarada": str(st.signer_reported_dt) if st.signer_reported_dt else "",
                    "cobertura": str(st.coverage).split(".")[-1],
                    "modificacao_depois": MODIFICACAO.get(
                        str(st.modification_level).split(".")[-1], str(st.modification_level)
                    )
                    if st.modification_level is not None
                    else "",
                    "permissao_docmdp": bool(st.docmdp_ok) if st.docmdp_ok is not None else None,
                }
            )
        except Exception as exc:  # noqa: BLE001 - assinatura malformada vira registro, nao queda
            registro.update({"erro": f"{type(exc).__name__}: {exc}"[:300], "hash_confere": False})
        intervalo = list(emb.sig_object["/ByteRange"])
        fim = int(intervalo[2]) + int(intervalo[3])
        registro["bytes_assinados"] = fim
        registro["bytes_depois"] = max(len(dados) - fim, 0)
        if registro.get("cadeia_confiavel"):
            confiaveis += 1
        if not registro.get("hash_confere"):
            alterado = True
        elif registro["bytes_depois"] > 0:
            diferencas = diferencas_visuais(dados[:fim], dados, retangulos)
            registro["diferencas_visuais"] = len(diferencas)
            for d in diferencas:
                laudo.alteracoes_visuais.append({**d, "depois_da_assinatura": emb.field_name})
            if diferencas:
                alterado = True
        laudo.assinaturas.append(registro)

    if alterado:
        laudo.conclusao = "alteracao_detectada"
        laudo.observacoes.append(
            "O conteúdo visível mudou depois de uma assinatura, ou o hash assinado não confere: "
            "o que se vê não é o que foi assinado."
        )
    elif confiaveis == len(laudo.assinaturas):
        laudo.conclusao = "integridade_confirmada"
        laudo.observacoes.append(
            "As assinaturas conferem e fecham numa raiz confiável, e nada visível mudou depois "
            "delas. Isso prova integridade e autoria da assinatura, não a veracidade do conteúdo."
        )
    else:
        laudo.observacoes.append(
            "As assinaturas conferem, mas ao menos uma cadeia não fecha numa raiz confiável "
            "(ICP-Brasil ou as raízes informadas): não há como atribuir a assinatura."
        )
    if not buscar_na_rede:
        laudo.observacoes.append("A revogação dos certificados não foi consultada.")
    return laudo


def verificar_proveniencia(caminho: Union[str, Path]) -> Laudo:
    """Le o manifesto C2PA de uma imagem, video, audio ou PDF."""
    import json

    dados = Path(caminho).read_bytes()
    laudo = Laudo("inconclusivo", _descricao(dados))
    try:
        import c2pa
    except ImportError:
        laudo.observacoes.append("Leitor C2PA não instalado (pip install c2pa-python).")
        return laudo
    try:
        leitor = c2pa.Reader(str(caminho))
    except Exception as exc:  # noqa: BLE001 - sem manifesto o leitor levanta erro
        laudo.proveniencia = {"manifesto": False, "detalhe": str(exc)[:200]}
        laudo.observacoes.append(
            "Sem manifesto de proveniência (C2PA). A ausência não indica nada: a maioria das "
            "câmeras e programas ainda não grava manifesto."
        )
        return laudo
    with leitor:
        loja = json.loads(leitor.json())
        estado = str(leitor.get_validation_state() or "")
    ativo = loja.get("manifests", {}).get(loja.get("active_manifest", ""), {})
    acoes = [
        a
        for asserc in ativo.get("assertions", [])
        if asserc.get("label", "").startswith("c2pa.actions")
        for a in asserc.get("data", {}).get("actions", [])
    ]
    origem_ia = any(
        any(t in str(a.get("digitalSourceType", "")) for t in _GERADO_POR_IA) for a in acoes
    )
    problemas = [s for s in loja.get("validation_status", []) or []]
    laudo.proveniencia = {
        "manifesto": True,
        "estado": estado,
        "gerador": ativo.get("claim_generator", "") or str(ativo.get("claim_generator_info", "")),
        "assinado_por": (ativo.get("signature_info") or {}).get("issuer", ""),
        "acoes": [a.get("action") for a in acoes],
        "declara_geracao_por_ia": origem_ia,
        "problemas": [p.get("code") for p in problemas],
    }
    hash_falhou = any("mismatch" in str(p.get("code", "")) for p in problemas)
    if hash_falhou:
        laudo.conclusao = "alteracao_detectada"
        laudo.observacoes.append(
            "O conteúdo não confere com o hash do manifesto: foi alterado depois."
        )
    elif estado.lower() in ("valid", "trusted") and any(
        "untrusted" in str(p.get("code", "")) for p in problemas
    ):
        laudo.observacoes.append(
            "O conteúdo confere com o manifesto, mas quem assinou o manifesto não está numa "
            "lista de confiança: não há como atribuir a declaração."
        )
    elif estado.lower() in ("valid", "trusted"):
        laudo.conclusao = "integridade_confirmada"
        laudo.observacoes.append(
            "O manifesto confere com o conteúdo. Ele prova o que o signatário declarou "
            "(origem, edições, uso de IA), não que a cena retratada aconteceu."
        )
    else:
        laudo.observacoes.append("O manifesto existe, mas a assinatura dele não foi validada.")
    if origem_ia:
        laudo.observacoes.append("O próprio manifesto declara geração ou composição por IA.")
    return laudo


def _descricao(dados: bytes) -> Dict[str, Any]:
    return {"bytes": len(dados), "sha256": hashlib.sha256(dados).hexdigest()}


def verificar(caminho: Union[str, Path], **kwargs: Any) -> Laudo:
    """PDF: assinaturas e alteracoes; o resto: manifesto C2PA."""
    dados = Path(caminho).read_bytes()
    if dados[:5] == b"%PDF-":
        laudo = verificar_pdf(dados, **kwargs)
        if laudo.conclusao == "inconclusivo" and not laudo.assinaturas:
            proveniencia = verificar_proveniencia(caminho)
            if proveniencia.proveniencia.get("manifesto"):
                return proveniencia
        return laudo
    return verificar_proveniencia(caminho)
