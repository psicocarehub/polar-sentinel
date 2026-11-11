"""Polar Sentinel: certidao de inspecao tecnica de documento.

A Nota Tecnica CNJ 2635739 (09/06/2026) pede que o conteudo suspeito seja
separado, preservado e registrado nos autos com a peca, a pagina, a natureza
tecnica, a acao tomada, a data e a hora, a versao da ferramenta e o hash do
trecho. Esta e essa certidao, gerada a partir do veredito de `evaluate_pdf` ou
`evaluate_docx`.

A certidao descreve fatos do arquivo, com as medidas que um perito confere
(contraste, tamanho, cores, posicao). Nao atribui autoria, intencao nem
ma-fe: isso depende de contraditorio.

Uso:
    python -m polar_sentinel.certidao peticao.pdf \
        --processo 0000000-00.2026.8.26.0100 --peca "Peticao inicial"
    python -m polar_sentinel.certidao peticao.docx --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from polar_sentinel import __version__

NATUREZA = {
    "cor_do_fundo": "texto na mesma cor do fundo",
    "fonte_minuscula": "texto em fonte menor que 2 pontos",
    "fora_da_pagina": "texto posicionado fora da área exibida da página",
    "modo_invisivel": "texto em modo de renderização invisível, sem imagem digitalizada embaixo",
    "transparente": "texto com opacidade de preenchimento próxima de zero",
    "coberto_ou_recortado": "texto coberto por outro objeto ou cortado por recorte",
    "baixo_contraste": "texto em contraste baixo, legível com dificuldade",
    "ocr_divergente": "camada de texto de página digitalizada que não confere com a imagem",
    "oculto": "texto com a propriedade de formatação oculto",
    "texto_excluido": "texto excluído com controle de alterações, ainda presente no arquivo",
    "anotacao": "anotação ou comentário do PDF",
    "campo_de_formulario": "valor de campo de formulário",
    "camada_desligada": "camada opcional que abre desligada",
    "arquivo_embutido": "arquivo anexado dentro do documento",
    "javascript": "código JavaScript",
    "link": "endereço de link",
    "metadado": "metadados do arquivo",
    "comentario": "comentário do Word",
    "texto_alternativo": "texto alternativo de imagem",
    "codigo_de_campo": "código de campo do Word",
    "xml_personalizado": "XML personalizado embutido",
    "bloco_de_construcao": "bloco de construção do Word",
    "objeto_embutido": "objeto embutido",
    "macro": "macro VBA",
    "unicode_invisivel": "caracteres Unicode invisíveis (tag, controle bidirecional ou seletor)",
}

_SEMPRE_RELATAR = {"javascript", "arquivo_embutido", "camada_desligada", "macro", "objeto_embutido"}


def _agora_brasilia(agora: Optional[datetime] = None) -> datetime:
    agora = agora or datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        return agora.astimezone(ZoneInfo("America/Sao_Paulo"))
    except Exception:  # noqa: BLE001 - sem base de fusos (Windows sem tzdata)
        return agora.astimezone(timezone(timedelta(hours=-3)))


def _sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def _decimal(valor: float, casas: int = 2) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


@dataclass
class Certidao:
    dados: Dict[str, Any]
    achados: List[Dict[str, Any]] = field(default_factory=list)

    def como_dict(self) -> Dict[str, Any]:
        return {**self.dados, "achados": self.achados}

    def como_json(self) -> str:
        return json.dumps(self.como_dict(), ensure_ascii=False, indent=2)

    def como_texto(self) -> str:
        d = self.dados
        linhas = ["CERTIDÃO DE INSPEÇÃO TÉCNICA DE DOCUMENTO", ""]
        if d.get("processo"):
            linhas.append(f"Processo: {d['processo']}")
        if d.get("peca"):
            linhas.append(f"Peça: {d['peca']}")
        doc = d["documento"]
        paginas = f", {doc['paginas']} página(s)" if doc.get("paginas") else ""
        linhas += [
            f"Arquivo: {doc['nome']} ({doc['bytes']} bytes{paginas})",
            f"SHA-256 do arquivo: {doc['sha256']}",
            f"Inspeção: Polar Sentinel {d['inspecao']['versao']}, "
            f"leitura por {d['inspecao']['motor']}, "
            f"em {d['inspecao']['data_hora']}.",
            "",
            f"Resultado: {d['resultado']}.",
        ]
        if not self.achados:
            linhas.append("Nenhum conteúdo oculto ou canal fora do texto da página foi encontrado.")
        for n, a in enumerate(self.achados, start=1):
            onde = f"Página {a['pagina']}. " if a.get("pagina") else ""
            linhas += ["", f"{n}. {onde}{a['natureza'][0].upper()}{a['natureza'][1:]}."]
            m = a.get("medidas") or {}
            partes = []
            if "contraste" in m:
                partes.append(f"contraste {_decimal(m['contraste'])}:1")
            if "tamanho_pt" in m:
                partes.append(f"fonte {_decimal(m['tamanho_pt'], 1)} pt")
            if "cor_texto" in m and "cor_fundo" in m:
                partes.append(f"cor {m['cor_texto']} sobre {m['cor_fundo']}")
            if "opacidade" in m and m["opacidade"] < 1:
                partes.append(f"opacidade {_decimal(m['opacidade'])}")
            if "posicao_pt" in m:
                x0, y0, x1, y1 = m["posicao_pt"]
                partes.append(
                    f"caixa de ({_decimal(x0, 1)}; {_decimal(y0, 1)}) a "
                    f"({_decimal(x1, 1)}; {_decimal(y1, 1)}) pontos"
                )
            if partes:
                linhas.append("   Medidas: " + "; ".join(partes) + ".")
            if a.get("trecho"):
                linhas.append(f'   Trecho: "{a["trecho"]}"')
                linhas.append(f"   SHA-256 do trecho: {a['sha256_trecho']}")
            linhas.append(f"   Ação: {a['acao']}")
        linhas += ["", "Ressalvas:"] + [f"- {r}" for r in d["ressalvas"]]
        return "\n".join(linhas)


def emitir_certidao(
    veredito: Any,
    dados: bytes,
    nome: str,
    *,
    processo: str = "",
    peca: str = "",
    agora: Optional[datetime] = None,
) -> Certidao:
    """Monta a certidao a partir do veredito e dos bytes do arquivo inspecionado."""
    from polar_sentinel.reference.pdf_inspector import tem_ordem
    from polar_sentinel.reference.sanitizer import sanitize_with_audit

    inspecao = veredito.inspection
    momento = _agora_brasilia(agora)
    achados: List[Dict[str, Any]] = []
    for trecho in inspecao.hidden_spans:
        motivo = getattr(trecho, "reason", None) or getattr(trecho, "motivo", "")
        texto = getattr(trecho, "text", None) or getattr(trecho, "texto", "")
        achados.append(
            {
                "pagina": getattr(trecho, "page", None),
                "parte": getattr(trecho, "parte", None),
                "codigo": motivo,
                "natureza": NATUREZA.get(motivo, motivo),
                "trecho": texto,
                "sha256_trecho": _sha256(texto.encode("utf-8")),
                "medidas": dict(getattr(trecho, "medidas", {}) or {}),
                "acao": "separado do texto entregue à IA e preservado nesta certidão.",
            }
        )
    for achado in getattr(inspecao, "achados", []):
        relevante = achado.tipo in _SEMPRE_RELATAR or (
            achado.texto
            and tem_ordem(achado.texto)
            and (achado.tipo != "metadado" or "comando_em_metadado" in veredito.reasons)
        )
        if not relevante or achado.tipo == "revisoes":
            continue
        detalhe = {k: v for k, v in achado.detalhe.items() if k != "inspecao"}
        achados.append(
            {
                "pagina": achado.pagina,
                "codigo": achado.tipo,
                "natureza": NATUREZA.get(achado.tipo, achado.tipo),
                "trecho": achado.texto[:2000],
                "sha256_trecho": _sha256(achado.texto.encode("utf-8")),
                "medidas": detalhe,
                "acao": "conteúdo fora do texto da página; não entregue à IA e preservado "
                "nesta certidão.",
            }
        )
    if "ordem_em_unicode_invisivel" in veredito.reasons or "unicode_invisivel" in veredito.atencao:
        tudo = "\n".join(
            [inspecao.visible_text, *(a.texto for a in getattr(inspecao, "achados", []))]
        )
        decodificado = sanitize_with_audit(tudo).hidden_text
        achados.append(
            {
                "pagina": None,
                "codigo": "unicode_invisivel",
                "natureza": NATUREZA["unicode_invisivel"],
                "trecho": decodificado,
                "sha256_trecho": _sha256(decodificado.encode("utf-8")),
                "medidas": {},
                "acao": "caracteres removidos do texto entregue à IA; conteúdo decodificado "
                "preservado nesta certidão.",
            }
        )

    if veredito.flagged:
        resultado = (
            "documento sinalizado: há ordem dirigida a sistema de IA em conteúdo que o leitor "
            "humano não vê"
        )
    elif achados:
        resultado = (
            "há conteúdo oculto ou fora do texto da página, sem ordem dirigida a sistema de IA "
            "identificada"
        )
    else:
        resultado = "nada encontrado"

    from polar_sentinel.reference.pdf_percepcao import LIMIAR_INVISIVEL, MIN_LEGIVEL_PT

    motor = getattr(inspecao, "motor", "xml")
    rotulo_motor = {
        "renderizacao": "renderização da página",
        "conteudo": "leitura do conteúdo da página",
        "xml": "leitura do XML do documento",
    }.get(motor, motor)
    dados_certidao = {
        "processo": processo,
        "peca": peca,
        "documento": {
            "nome": nome,
            "bytes": len(dados),
            "sha256": _sha256(dados),
            "paginas": getattr(inspecao, "paginas", None),
        },
        "inspecao": {
            "ferramenta": "Polar Sentinel",
            "versao": __version__,
            "motor": rotulo_motor,
            "data_hora": momento.strftime("%d/%m/%y às %H:%M:%S") + " (horário de Brasília)",
            "data_hora_iso": momento.isoformat(),
            "limiares": {
                "contraste_invisivel": LIMIAR_INVISIVEL,
                "fonte_minima_pt": MIN_LEGIVEL_PT,
            },
        },
        "resultado": resultado,
        "motivos": list(veredito.reasons),
        "atencao": list(veredito.atencao),
        "ressalvas": [
            "Esta certidão descreve características técnicas do arquivo. Não afirma autoria, "
            "intenção ou má-fé, que dependem de contraditório.",
            f"Os limiares (contraste abaixo de {_decimal(LIMIAR_INVISIVEL)}:1 para texto "
            "comum, menor para letra grande, fonte abaixo de "
            f"{_decimal(MIN_LEGIVEL_PT, 0)} pontos) são escolhas de engenharia ainda não "
            "calibradas "
            "com leitores.",
            "A ausência de achados não garante que o documento esteja livre de instruções "
            "dirigidas "
            "a sistemas de IA: uma ordem escrita às claras, visível, não é objeto desta inspeção.",
            f'Para reproduzir: pip install "polar-sentinel[pdf]=={__version__}" e '
            "python -m polar_sentinel.certidao <arquivo>; o SHA-256 confirma que o arquivo "
            "é o mesmo.",
        ],
    }
    return Certidao(dados_certidao, achados)


def certificar_arquivo(caminho: str, *, processo: str = "", peca: str = "") -> Certidao:
    """Inspeciona um PDF ou .docx e devolve a certidao."""
    dados = Path(caminho).read_bytes()
    if dados[:2] == b"PK":
        from polar_sentinel.reference.docx_inspector import evaluate_docx

        veredito = evaluate_docx(dados)
    else:
        from polar_sentinel.reference.pdf_inspector import evaluate_pdf

        veredito = evaluate_pdf(dados)
    return emitir_certidao(veredito, dados, Path(caminho).name, processo=processo, peca=peca)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Certidão de inspeção técnica de PDF ou .docx.")
    parser.add_argument("arquivo")
    parser.add_argument("--processo", default="")
    parser.add_argument("--peca", default="")
    parser.add_argument("--json", action="store_true", help="saída em JSON")
    args = parser.parse_args(argv)
    certidao = certificar_arquivo(args.arquivo, processo=args.processo, peca=args.peca)
    print(certidao.como_json() if args.json else certidao.como_texto())
    return 1 if certidao.dados["motivos"] else 0


if __name__ == "__main__":
    sys.exit(main())
