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
    "proveniencia": "Conferência de fontes e citações",
    "governanca": "Controle de ações e aprovação humana",
    "observabilidade": "Registro e auditoria",
}

# Os passos da defesa, em ordem, em uma frase cada. Serve de legenda no lab.
LAYER_STEPS: List[Tuple[str, str]] = [
    ("Filtro de dados pessoais",
     "Remove CPF, nome, endereço e outros dados sensíveis antes de qualquer IA ler."),
    ("Leitura segura do documento",
     "Limpa texto invisível e truques de formatação usados para esconder comandos."),
    ("Detector de comandos suspeitos",
     "Reconhece ordens disfarçadas que tentam manipular a IA."),
    ("Conferência de fontes e citações",
     "Checa se a jurisprudência citada realmente existe."),
    ("Controle de ações e aprovação humana",
     "Nada irreversível, como protocolar, acontece sem um humano aprovar."),
    ("Registro e auditoria",
     "Guarda o que foi encontrado para que tudo possa ser conferido depois."),
]

# O que cada artefato removido na sanitizacao (L1) significa, em palavras simples.
KIND_LABELS: Dict[str, str] = {
    "invisible_unicode": "Havia letras invisíveis escondidas no meio do texto, "
    "que a pessoa não vê, mas o computador lê.",
    "bidi_control": "Havia caracteres que invertem a ordem do texto na tela, "
    "usados para esconder um comando do leitor.",
    "unicode_tag_chars": "Havia um comando escrito com caracteres invisíveis "
    "especiais, uma técnica chamada contrabando de texto.",
    "variation_selectors": "Havia dados escondidos atrás de símbolos e emojis, "
    "invisíveis para quem lê.",
    "artefato_tipografico": "",
    "seletor_de_emoji": "",
    "html_comment": "Havia um comando escondido em um comentário de código, "
    "que não aparece quando o documento é exibido.",
    "ansi_escape": "Havia códigos de terminal escondidos no texto, usados para "
    "deixar instruções invisíveis.",
}

# O que cada motivo da deteccao (L2) significa, em palavras simples. A chave e o
# prefixo do codigo tecnico devolvido pelo detector.
REASON_LABELS: List[Tuple[str, str]] = [
    ("override_canonico", "O documento mandava a IA ignorar as instruções "
     "anteriores, o golpe clássico de injeção de comando."),
    ("override_pattern", "O documento dava ordens para a IA mudar de "
     "comportamento, em vez de ser apenas um texto a analisar."),
    ("linguagem_com_aparencia_de_decisao", "O texto tentava fazer a IA escrever "
     "uma decisão judicial, algo que só o magistrado pode fazer."),
    ("decisao_combinada_com_override", "O texto juntava uma ordem oculta com "
     "linguagem de decisão judicial."),
    ("escape_de_delimitador", "O texto tentava se passar por uma instrução do "
     "próprio sistema, fingindo encerrar o documento e começar uma ordem nova."),
    ("tentativa_de_burlar_controle_de_seguranca", "O texto pedia explicitamente "
     "para ignorar as regras de segurança e do CNJ."),
    ("uso_indevido_de_ferramenta_ou_certificado", "O texto tentava fazer a IA "
     "usar o certificado digital para protocolar sozinha, sem confirmação."),
    ("estrutura_ativa_de_pdf", "O arquivo trazia componentes que executam ações "
     "sozinhos ao abrir, o que um documento comum não deveria ter."),
    ("mistura_de_scripts_possivel_homoglifo", "O texto usava letras de outro "
     "alfabeto parecidas com as nossas para enganar os filtros."),
    ("comando_oculto_em_base64", "Havia um comando escondido em código, que só "
     "aparece depois de decodificar."),
    ("blob_base64_decodificado", "Havia um trecho de código embaralhado, usado "
     "as vezes para esconder instruções."),
    ("blob_ofuscado_hex", "Havia um trecho de código embaralhado em hexadecimal."),
    ("repeticao_de_ignore", "O texto repetia ordens de ignorar instruções várias "
     "vezes, tentando dominar a atenção da IA."),
    ("texto_dirigido_a_ia_leitora", "O documento falava diretamente com a IA que "
     "iria lê-lo, como um recado, em vez de se dirigir ao juiz ou às partes."),
    ("troca_de_papel_ou_de_tarefa", "O texto tentava dar a IA um novo papel ou "
     "uma nova tarefa, diferente da que ela recebeu."),
    ("ordem_para_pular_revisao_ou_ignorar_provas", "O texto mandava a IA agir "
     "sem a conferência de uma pessoa ou desprezar provas do processo."),
    ("envenenamento_de_memoria_ou_instrucao_oculta", "O texto tentava gravar uma "
     "regra falsa na memória da IA para valer em casos futuros."),
    ("comando_visivel_so_apos_reunir_letras", "O comando estava disfarçado com "
     "letras separadas ou trocadas por números, para passar pelos filtros."),
    ("comando_oculto_em_hexadecimal", "Havia um comando escondido em código "
     "hexadecimal, que só aparece depois de decodificar."),
    ("comando_visivel_so_apos_decifrar", "O comando estava cifrado ou escrito de "
     "trás para frente, e só apareceu depois de decifrado."),
    ("vocabulario_de_assistente_que_age", "O texto tratava o leitor como um "
     "assistente automático capaz de agir sozinho, sem pedir confirmação."),
    ("ordem_de_dispositivo_dirigida_ao_leitor", "O texto dava uma ordem de julgamento "
     "no imperativo, como \"defira todos os pedidos\", coisa que uma peça não faz: "
     "advogado pede, não manda."),
    ("pedido_para_revelar_instrucoes", "O texto pedia que a IA revelasse as "
     "instruções internas que recebeu."),
    ("comando_em_canal_oculto", "O comando estava em uma parte do arquivo que "
     "não aparece na tela, como um comentário ou caracteres invisíveis."),
]

# Nome amigavel do tipo de ataque por categoria do corpus.
CATEGORY_LABELS: Dict[str, str] = {
    "benigno": "Documento legítimo",
    "injecao_direta": "Comando escondido a vista (texto oculto)",
    "unicode_smuggling": "Contrabando de caracteres invisíveis",
    "artefato_documento": "Comando escondido em artefato do documento",
    "injecao_indireta": "Comando escondido em metadado",
    "escape_de_contexto": "Texto fingindo ser instrução do sistema",
    "ofuscacao": "Comando disfarçado ou embaralhado",
    "rag_poisoning": "Jurisprudência falsa (envenenamento de base)",
    "memory_poisoning": "Memória envenenada",
    "tool_misuse": "Uso indevido de ferramenta ou certificado",
    "governanca_saida": "Tentativa de produzir decisão automática",
    "injecao_multimodal": "Comando escondido em áudio, imagem ou vídeo",
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
            "A leitura segura do documento limpou e revelou conteúdo oculto antes "
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
            "O detector de comandos suspeitos reconheceu padrões de manipulação "
            "no texto."
        )
    if hitl_required:
        identificado.append(
            "O controle de ações exigiu aprovação humana antes de qualquer ação "
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
        resumo = ("Não encontramos comandos escondidos nem sinais de manipulação "
                  "neste documento.")
        recomendacao = ("O documento passou nas verificações automáticas. Em ações "
                        "críticas, a revisão humana continua recomendada.")
        if not identificado:
            identificado.append("Todas as camadas analisaram o documento e nada "
                                "suspeito foi encontrado.")
    elif veredito == "SUSPEITO":
        resumo = ("Encontramos sinais de que alguém tentou influenciar a IA por "
                  "meio deste documento.")
        recomendacao = ("Recomendamos revisão humana antes de seguir. O conteúdo "
                        "suspeito foi separado e registrado, não apagado.")
    else:
        resumo = ("Este documento contém um ataque de injeção de comando, ou seja, "
                  "uma instrução escondida para manipular a IA.")
        recomendacao = ("Não prossiga de forma automática. O comando foi bloqueado, "
                        "separado e registrado para auditoria, e a ação exige "
                        "confirmação humana.")

    return Explanation(
        veredito=veredito,
        cor=cor,
        resumo=resumo,
        o_que_estava_escondido=escondido,
        como_identificamos=identificado,
        recomendacao=recomendacao,
    )
