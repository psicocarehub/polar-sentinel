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
    "so_sem_transparencia": "texto escondido nos pixels transparentes da imagem",
    "so_apos_reducao": "texto que só aparece quando a imagem é reduzida ao tamanho de entrada "
    "de um modelo",
    "quadro_relampago": "texto em quadros que ficam na tela por menos de 0,25 segundo",
    "legenda_relampago": "legenda que fica na tela por menos tempo do que se consegue ler",
    "legenda": "faixa de legenda do vídeo",
    "fala_em_volume_baixo": "fala muito abaixo do volume da fala principal",
    "fala_acelerada": "fala acelerada além do que se compreende ao ouvir",
    "fala_sob_ruido": "fala encoberta por ruído ou música",
    "transcricao_divergente": "trecho em que dois transcritores de famílias diferentes discordam",
    "voz_sem_transcricao": "trecho com voz e sem palavra transcrita",
    "energia_ultrassonica": "energia acima de 18 kHz na gravação",
    "faixa_de_dados": "faixa de dados no vídeo",
    "faixa_de_audio_extra": "mais de uma faixa de áudio no vídeo",
    "oculto": "texto com a propriedade de formatação oculto",
    "texto_excluido": "texto excluído com controle de alterações, ainda presente no arquivo",
    "anotacao": "anotação ou comentário do PDF",
    "campo_de_formulario": "valor de campo de formulário",
    "camada_desligada": "camada opcional que abre desligada",
    "arquivo_embutido": "arquivo anexado dentro do documento",
    "javascript": "código JavaScript",
    "link": "endereço de link",
    "metadado": "metadados do arquivo",
    "metadado_de_imagem": "metadados de imagem embutida (comentário, EXIF ou XMP)",
    "comentario": "comentário do Word",
    "texto_alternativo": "texto alternativo de imagem",
    "codigo_de_campo": "código de campo do Word",
    "xml_personalizado": "XML personalizado embutido",
    "bloco_de_construcao": "bloco de construção do Word",
    "objeto_embutido": "objeto embutido",
    "macro": "macro VBA",
    "unicode_invisivel": "caracteres Unicode invisíveis (tag, controle bidirecional ou seletor)",
    "texto_substituto": "texto substituto (ActualText) que o extrator entrega no lugar do que a "
    "página mostra",
}


def _natureza(codigo: str) -> str:
    if codigo.startswith("imagem_"):
        return "em imagem, " + NATUREZA.get(codigo[7:], codigo[7:])
    return NATUREZA.get(codigo, codigo)


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
        documento = d["inspecao"].get("motor_codigo") in ("renderizacao", "conteudo", "xml")
        objeto = "DOCUMENTO" if documento else "ARQUIVO"
        linhas = [f"CERTIDÃO DE INSPEÇÃO TÉCNICA DE {objeto}", ""]
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
            f"{d['inspecao']['motor']}, "
            f"em {d['inspecao']['data_hora']}.",
        ]
        if d.get("limites"):
            linhas.append("Leitura feita sem: " + "; ".join(d["limites"]) + ".")
        linhas += ["", f"Resultado: {d['resultado']}."]
        if not self.achados:
            linhas.append(
                "Nenhum conteúdo oculto ou canal fora do texto da página foi encontrado."
                if documento
                else "Nenhum conteúdo oculto nem canal fora do que a pessoa vê e ouve foi "
                "encontrado."
            )
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
            if "inicio_s" in m:
                segundos = float(m["inicio_s"])
                partes.append(
                    f"instante {int(segundos // 3600):02d}:{int(segundos % 3600 // 60):02d}:"
                    f"{_decimal(segundos % 60, 1).zfill(4)}"
                )
            if "duracao_ms" in m and m["duracao_ms"] is not None:
                partes.append(f"duração {m['duracao_ms']} ms")
            if "abaixo_da_fala_db" in m:
                partes.append(f"{_decimal(m['abaixo_da_fala_db'], 1)} dB abaixo da fala principal")
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


def _ressalva_de_limiar(motor: str) -> str:
    from polar_sentinel.reference.audio_inspector import ABAIXO_DA_FALA_DB
    from polar_sentinel.reference.pdf_percepcao import LIMIAR_INVISIVEL, MIN_LEGIVEL_PT

    escolha = "são escolhas de engenharia ainda não calibradas com pessoas."
    if motor == "audio":
        return f"O limiar (fala {_decimal(ABAIXO_DA_FALA_DB, 0)} dB abaixo da principal) {escolha}"
    if motor == "video":
        return (
            "Os limiares (legenda ou quadro por menos de 0,3 s, fala "
            f"{_decimal(ABAIXO_DA_FALA_DB, 0)} dB abaixo da principal, contraste) {escolha}"
        )
    return (
        f"Os limiares (contraste abaixo de {_decimal(LIMIAR_INVISIVEL)}:1 para texto comum, "
        f"menor para letra grande, fonte abaixo de {_decimal(MIN_LEGIVEL_PT, 0)} pontos) "
        f"{escolha}"
    )


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
                "natureza": _natureza(motivo),
                "trecho": texto,
                "sha256_trecho": _sha256(texto.encode("utf-8")),
                "medidas": dict(getattr(trecho, "medidas", {}) or {}),
                "acao": "separado do texto entregue à IA e preservado nesta certidão.",
            }
        )
    for achado in getattr(inspecao, "achados", []):
        relevante = (
            achado.tipo in _SEMPRE_RELATAR
            or achado.detalhe.get("diverge")
            or (
                achado.texto
                and tem_ordem(achado.texto)
                and (achado.tipo != "metadado" or "comando_em_metadado" in veredito.reasons)
            )
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

    so_visivel = set(veredito.reasons) <= {"comando_no_texto_visivel", "comando_na_fala_audivel"}
    if veredito.flagged and so_visivel:
        resultado = (
            "sinalizado: há ordem dirigida a sistema de IA no próprio conteúdo que a pessoa "
            "vê ou ouve; não há conteúdo oculto"
        )
    elif veredito.flagged:
        resultado = (
            "sinalizado: há ordem dirigida a sistema de IA em conteúdo que a pessoa não vê nem ouve"
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
        "renderizacao": "leitura pela renderização da página",
        "conteudo": "leitura do conteúdo da página",
        "xml": "leitura do XML do documento",
        "imagem": "leitura da imagem (Tesseract)",
        "video": "leitura do contêiner, das legendas, dos quadros e do áudio",
        "audio": "transcrição do áudio original e de versões preparadas (Whisper e Vosk)",
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
            "motor_codigo": motor,
            "data_hora": momento.strftime("%d/%m/%y às %H:%M:%S") + " (horário de Brasília)",
            "data_hora_iso": momento.isoformat(),
            "limiares": {
                "contraste_invisivel": LIMIAR_INVISIVEL,
                "fonte_minima_pt": MIN_LEGIVEL_PT,
            },
        },
        "limites": list(getattr(inspecao, "limites", []) or []),
        "resultado": resultado,
        "motivos": list(veredito.reasons),
        "atencao": list(veredito.atencao),
        "ressalvas": [
            "Esta certidão descreve características técnicas do arquivo. Não afirma autoria, "
            "intenção ou má-fé, que dependem de contraditório.",
            _ressalva_de_limiar(motor),
            "A ausência de achados não garante que o arquivo esteja livre de instruções "
            "dirigidas a sistemas de IA: uma ordem dita ou escrita às claras não é objeto "
            "desta inspeção.",
            f'Para reproduzir: pip install "polar-sentinel[completo]=={__version__}" e '
            "python -m polar_sentinel.certidao <arquivo>; o SHA-256 confirma que o arquivo "
            "é o mesmo.",
        ],
    }
    return Certidao(dados_certidao, achados)


VIDEO = (
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".ogv",
    ".avi",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".asf",
    ".wmv",
    ".3gp",
)
AUDIO = (".wav", ".mp3", ".m4a", ".ogg", ".opus", ".oga", ".aac", ".flac", ".amr", ".wma")


def certificar_arquivo(caminho: str, *, processo: str = "", peca: str = "") -> Certidao:
    """Inspeciona PDF, .docx, imagem, video ou audio e devolve a certidao."""
    dados = Path(caminho).read_bytes()
    sufixo = Path(caminho).suffix.lower()
    if sufixo in VIDEO:
        from polar_sentinel.reference.video_inspector import evaluate_video

        veredito = evaluate_video(caminho)
    elif sufixo in AUDIO:
        from polar_sentinel.reference.audio_inspector import evaluate_audio

        veredito = evaluate_audio(caminho)
    elif (
        dados[:8] == b"\x89PNG\r\n\x1a\n"
        or dados[:3] == b"\xff\xd8\xff"
        or dados[:4] in (b"GIF8", b"II*\x00", b"MM\x00*", b"RIFF")
        or dados[:2] == b"BM"
    ):
        from polar_sentinel.reference.imagem_inspector import evaluate_image

        veredito = evaluate_image(dados)
    elif dados[:2] == b"PK":
        from polar_sentinel.reference.docx_inspector import evaluate_docx

        veredito = evaluate_docx(dados)
    else:
        from polar_sentinel.reference.pdf_inspector import evaluate_pdf

        veredito = evaluate_pdf(dados)
    return emitir_certidao(veredito, dados, Path(caminho).name, processo=processo, peca=peca)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Certidão de inspeção técnica de PDF, .docx, imagem, vídeo ou áudio."
    )
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
