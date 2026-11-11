"""Polar Sentinel: tradutor para linguagem simples.

Converte os sinais tecnicos das camadas de defesa em uma explicacao que
qualquer pessoa entende: o que tentaram fazer, como estava escondido, como o
Polar Sentinel percebeu e qual a recomendacao.

E usado pelo laboratorio visual, mas funciona para qualquer documento, nao
apenas para os casos do corpus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Nome claro de cada camada, para nao depender das siglas L0 a L5.
# A sigla fica apenas como referencia secundaria na documentacao tecnica.
LAYER_NAMES: Dict[str, str] = {
    "privacidade": "Filtro de dados pessoais",
    "sanitizacao": "Leitura segura do documento",
    "deteccao": "Detector de comandos suspeitos",
    "proveniencia": "Conferencia de fontes e citacoes",
    "governanca": "Controle de acoes e aprovacao humana",
    "observabilidade": "Registro e auditoria",
}

# Os passos da defesa, em ordem, em uma frase cada. Serve de legenda no lab.
LAYER_STEPS: List[Tuple[str, str]] = [
    ("Filtro de dados pessoais",
     "Remove CPF, nome, endereco e outros dados sensiveis antes de qualquer IA ler."),
    ("Leitura segura do documento",
     "Limpa texto invisivel e truques de formatacao usados para esconder comandos."),
    ("Detector de comandos suspeitos",
     "Reconhece ordens disfarcadas que tentam manipular a IA."),
    ("Conferencia de fontes e citacoes",
     "Checa se a jurisprudencia citada realmente existe."),
    ("Controle de acoes e aprovacao humana",
     "Nada irreversivel, como protocolar, acontece sem um humano aprovar."),
    ("Registro e auditoria",
     "Guarda o que foi encontrado para que tudo possa ser conferido depois."),
]

# O que cada artefato removido na sanitizacao (L1) significa, em palavras simples.
KIND_LABELS: Dict[str, str] = {
    "invisible_unicode": "Havia letras invisiveis escondidas no meio do texto, "
    "que a pessoa nao ve, mas o computador le.",
    "bidi_control": "Havia caracteres que invertem a ordem do texto na tela, "
    "usados para esconder um comando do leitor.",
    "unicode_tag_chars": "Havia um comando escrito com caracteres invisiveis "
    "especiais, uma tecnica chamada contrabando de texto.",
    "variation_selectors": "Havia dados escondidos atras de simbolos e emojis, "
    "invisiveis para quem le.",
    "artefato_tipografico": "",
    "seletor_de_emoji": "",
    "html_comment": "Havia um comando escondido em um comentario de codigo, "
    "que nao aparece quando o documento e exibido.",
    "ansi_escape": "Havia codigos de terminal escondidos no texto, usados para "
    "deixar instrucoes invisiveis.",
}

# O que cada motivo da deteccao (L2) significa, em palavras simples. A chave e o
# prefixo do codigo tecnico devolvido pelo detector.
REASON_LABELS: List[Tuple[str, str]] = [
    ("override_canonico", "O documento mandava a IA ignorar as instrucoes "
     "anteriores, o golpe classico de injecao de comando."),
    ("override_pattern", "O documento dava ordens para a IA mudar de "
     "comportamento, em vez de ser apenas um texto a analisar."),
    ("linguagem_com_aparencia_de_decisao", "O texto tentava fazer a IA escrever "
     "uma decisao judicial, algo que so o magistrado pode fazer."),
    ("decisao_combinada_com_override", "O texto juntava uma ordem oculta com "
     "linguagem de decisao judicial."),
    ("escape_de_delimitador", "O texto tentava se passar por uma instrucao do "
     "proprio sistema, fingindo encerrar o documento e comecar uma ordem nova."),
    ("tentativa_de_burlar_controle_de_seguranca", "O texto pedia explicitamente "
     "para ignorar as regras de seguranca e do CNJ."),
    ("uso_indevido_de_ferramenta_ou_certificado", "O texto tentava fazer a IA "
     "usar o certificado digital para protocolar sozinha, sem confirmacao."),
    ("estrutura_ativa_de_pdf", "O arquivo trazia componentes que executam acoes "
     "sozinhos ao abrir, o que um documento comum nao deveria ter."),
    ("mistura_de_scripts_possivel_homoglifo", "O texto usava letras de outro "
     "alfabeto parecidas com as nossas para enganar os filtros."),
    ("comando_oculto_em_base64", "Havia um comando escondido em codigo, que so "
     "aparece depois de decodificar."),
    ("blob_base64_decodificado", "Havia um trecho de codigo embaralhado, usado "
     "as vezes para esconder instrucoes."),
    ("blob_ofuscado_hex", "Havia um trecho de codigo embaralhado em hexadecimal."),
    ("repeticao_de_ignore", "O texto repetia ordens de ignorar instrucoes varias "
     "vezes, tentando dominar a atencao da IA."),
    ("texto_dirigido_a_ia_leitora", "O documento falava diretamente com a IA que "
     "iria le-lo, como um recado, em vez de se dirigir ao juiz ou as partes."),
    ("troca_de_papel_ou_de_tarefa", "O texto tentava dar a IA um novo papel ou "
     "uma nova tarefa, diferente da que ela recebeu."),
    ("ordem_para_pular_revisao_ou_ignorar_provas", "O texto mandava a IA agir "
     "sem a conferencia de uma pessoa ou desprezar provas do processo."),
    ("envenenamento_de_memoria_ou_instrucao_oculta", "O texto tentava gravar uma "
     "regra falsa na memoria da IA para valer em casos futuros."),
    ("comando_visivel_so_apos_reunir_letras", "O comando estava disfarcado com "
     "letras separadas ou trocadas por numeros, para passar pelos filtros."),
    ("comando_oculto_em_hexadecimal", "Havia um comando escondido em codigo "
     "hexadecimal, que so aparece depois de decodificar."),
    ("comando_visivel_so_apos_decifrar", "O comando estava cifrado ou escrito de "
     "tras para frente, e so apareceu depois de decifrado."),
    ("vocabulario_de_assistente_que_age", "O texto tratava o leitor como um "
     "assistente automatico capaz de agir sozinho, sem pedir confirmacao."),
    ("ordem_de_dispositivo_dirigida_ao_leitor", "O texto dava uma ordem de julgamento "
     "no imperativo, como \"defira todos os pedidos\", coisa que uma peca nao faz: "
     "advogado pede, nao manda."),
    ("pedido_para_revelar_instrucoes", "O texto pedia que a IA revelasse as "
     "instrucoes internas que recebeu."),
    ("comando_em_canal_oculto", "O comando estava em uma parte do arquivo que "
     "nao aparece na tela, como um comentario ou caracteres invisiveis."),
]

# Nome amigavel do tipo de ataque por categoria do corpus.
CATEGORY_LABELS: Dict[str, str] = {
    "benigno": "Documento legitimo",
    "injecao_direta": "Comando escondido a vista (texto oculto)",
    "unicode_smuggling": "Contrabando de caracteres invisiveis",
    "artefato_documento": "Comando escondido em artefato do documento",
    "injecao_indireta": "Comando escondido em metadado",
    "escape_de_contexto": "Texto fingindo ser instrucao do sistema",
    "ofuscacao": "Comando disfarcado ou embaralhado",
    "rag_poisoning": "Jurisprudencia falsa (envenenamento de base)",
    "memory_poisoning": "Memoria envenenada",
    "tool_misuse": "Uso indevido de ferramenta ou certificado",
    "governanca_saida": "Tentativa de produzir decisao automatica",
    "injecao_multimodal": "Comando escondido em audio, imagem ou video",
}


@dataclass
class Explanation:
    """Explicacao em linguagem simples do resultado da analise."""

    veredito: str            # SEGURO, SUSPEITO ou PERIGOSO
    cor: str                 # cor associada ao veredito
    resumo: str              # uma frase que resume tudo
    o_que_estava_escondido: List[str] = field(default_factory=list)
    como_identificamos: List[str] = field(default_factory=list)
    recomendacao: str = ""


def _reason_to_plain(reason: str) -> str:
    for prefix, label in REASON_LABELS:
        if reason.startswith(prefix):
            return label
    return ""


def build_explanation(
    *,
    sanitization_kinds: List[str],
    detection_score: float,
    detection_reasons: List[str],
    hitl_required: bool,
    action: str = "",
) -> Explanation:
    """Monta a explicacao leiga a partir dos sinais das camadas."""
    escondido: List[str] = []
    for kind in sanitization_kinds:
        label = KIND_LABELS.get(kind)
        if label and label not in escondido:
            escondido.append(label)

    identificado: List[str] = []
    if escondido:  # residuo comum de PDF (hifen suave, BOM) nao tem rotulo e nao conta
        identificado.append(
            "A leitura segura do documento limpou e revelou conteudo oculto antes "
            "de qualquer IA ler."
        )
    # Sinal fraco isolado (abaixo do limiar) nao e apresentado como achado: uma
    # clausula com "sem aprovacao previa" nao e tentativa de manipulacao.
    relevantes = detection_reasons if detection_score > 0.4 else []
    for reason in relevantes:
        plain = _reason_to_plain(reason)
        if plain and plain not in escondido and plain not in identificado:
            escondido.append(plain)
    if any(_reason_to_plain(r) for r in relevantes):
        identificado.append(
            "O detector de comandos suspeitos reconheceu padroes de manipulacao "
            "no texto."
        )
    if hitl_required:
        identificado.append(
            "O controle de acoes exigiu aprovacao humana antes de qualquer acao "
            "com certificado digital."
        )

    # Veredito final.
    if detection_score >= 0.6 or (escondido and detection_score >= 0.4):
        veredito, cor = "PERIGOSO", "#dc2626"
    elif detection_score >= 0.4 or escondido:
        veredito, cor = "SUSPEITO", "#ca8a04"
    else:
        veredito, cor = "SEGURO", "#16a34a"

    if veredito == "SEGURO":
        resumo = ("Nao encontramos comandos escondidos nem sinais de manipulacao "
                  "neste documento.")
        recomendacao = ("O documento passou nas verificacoes automaticas. Em acoes "
                        "criticas, a revisao humana continua recomendada.")
        if not identificado:
            identificado.append("Todas as camadas analisaram o documento e nada "
                                "suspeito foi encontrado.")
    elif veredito == "SUSPEITO":
        resumo = ("Encontramos sinais de que alguem tentou influenciar a IA por "
                  "meio deste documento.")
        recomendacao = ("Recomendamos revisao humana antes de seguir. O conteudo "
                        "suspeito foi separado e registrado, nao apagado.")
    else:
        resumo = ("Este documento contem um ataque de injecao de comando, ou seja, "
                  "uma instrucao escondida para manipular a IA.")
        recomendacao = ("Nao prossiga de forma automatica. O comando foi bloqueado, "
                        "separado e registrado para auditoria, e a acao exige "
                        "confirmacao humana.")

    return Explanation(
        veredito=veredito,
        cor=cor,
        resumo=resumo,
        o_que_estava_escondido=escondido,
        como_identificamos=identificado,
        recomendacao=recomendacao,
    )
