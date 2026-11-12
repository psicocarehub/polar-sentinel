"""Polar Sentinel: laudo tecnico de integridade e proveniencia.

Uso:
    python -m polar_sentinel.laudo prova.pdf
    python -m polar_sentinel.laudo foto.jpg --json
    python -m polar_sentinel.laudo prova.pdf --rede     # consulta revogacao

Conclusao em tres saidas: integridade confirmada, alteracao detectada ou
inconclusivo. Veja reference/autenticidade.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from polar_sentinel import __version__
from polar_sentinel.certidao import _agora_brasilia

CONCLUSAO = {
    "integridade_confirmada": "integridade confirmada",
    "alteracao_detectada": "alteração detectada",
    "inconclusivo": "inconclusivo",
}


def _sim_nao(valor):
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    return valor


def como_texto(laudo, nome: str) -> str:
    momento = _agora_brasilia()
    linhas = [
        "LAUDO TÉCNICO DE INTEGRIDADE E PROVENIÊNCIA",
        "",
        f"Arquivo: {nome} ({laudo.arquivo['bytes']} bytes)",
        f"SHA-256 do arquivo: {laudo.arquivo['sha256']}",
        f"Exame: Polar Sentinel {__version__}, em {momento.strftime('%d/%m/%y às %H:%M:%S')} "
        "(horário de Brasília).",
        "",
        f"Conclusão: {CONCLUSAO.get(laudo.conclusao, laudo.conclusao)}.",
    ]
    for n, a in enumerate(laudo.assinaturas, start=1):
        linhas += ["", f"Assinatura {n} ({a.get('campo') or 'sem nome'})"]
        for chave, rotulo in (
            ("signatario", "Signatário"),
            ("emissor", "Emissor"),
            ("data_declarada", "Data declarada"),
            ("formato", "Formato"),
            ("hash_confere", "Hash assinado confere"),
            ("assinatura_valida", "Assinatura criptograficamente válida"),
            ("cadeia_confiavel", "Cadeia fecha numa raiz confiável"),
            ("modificacao_depois", "Modificação depois da assinatura"),
            ("bytes_depois", "Bytes acrescentados depois da assinatura"),
            ("validacao_criptografica", "Validação criptográfica"),
            ("erro", "Erro"),
        ):
            if chave in a and a[chave] not in (None, ""):
                valor = _sim_nao(a[chave])
                linhas.append(f"   {rotulo}: {valor}")
    for d in laudo.alteracoes_visuais:
        onde = f"página {d['pagina']}" if d.get("pagina") else "documento"
        regiao = ""
        if d.get("regiao_pt"):
            x0, y0, x1, y1 = d["regiao_pt"]
            regiao = f", região de ({x0}; {y0}) a ({x1}; {y1}) pontos"
        linhas.append(
            f"Alteração visível depois de {d.get('depois_da_assinatura')}: {onde}{regiao}."
        )
    if laudo.proveniencia:
        p = laudo.proveniencia
        linhas += ["", "Proveniência (C2PA)"]
        linhas.append(f"   Manifesto: {'presente' if p.get('manifesto') else 'ausente'}")
        for chave, rotulo in (
            ("estado", "Estado da validação"),
            ("gerador", "Programa que gerou"),
            ("assinado_por", "Manifesto assinado por"),
            ("acoes", "Ações declaradas"),
            ("declara_geracao_por_ia", "Declara geração por IA"),
            ("problemas", "Problemas"),
        ):
            if p.get(chave) not in (None, "", []):
                valor = _sim_nao(p[chave])
                linhas.append(f"   {rotulo}: {valor}")
    linhas += ["", "Observações:"] + [f"- {o}" for o in laudo.observacoes]
    linhas += [
        "- Este laudo trata da integridade do arquivo e do que foi declarado por quem o assinou. "
        "Não afirma que o conteúdo é verdadeiro nem detecta, por pontuação, mídia gerada por IA.",
    ]
    return "\n".join(linhas)


def main(argv: Optional[List[str]] = None) -> int:
    from polar_sentinel.reference.autenticidade import verificar

    parser = argparse.ArgumentParser(description="Laudo de integridade e proveniência.")
    parser.add_argument("arquivo")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--rede", action="store_true", help="consulta revogação dos certificados")
    args = parser.parse_args(argv)
    caminho = Path(args.arquivo)
    laudo = (
        verificar(caminho, buscar_na_rede=args.rede)
        if caminho.suffix.lower() == ".pdf"
        else verificar(caminho)
    )
    if args.json:
        print(json.dumps(asdict(laudo), ensure_ascii=False, indent=2, default=str))
    else:
        print(como_texto(laudo, caminho.name))
    return {"alteracao_detectada": 2, "inconclusivo": 1}.get(laudo.conclusao, 0)


if __name__ == "__main__":
    sys.exit(main())
