"""Polar Sentinel: laboratorio de defesa aberta.

Interface visual para testar as camadas de defesa contra injecao de comandos
em documentos judiciais. Permite colar texto, enviar PDF ou TXT, escolher
qualquer API e inspecionar o que cada camada encontrou.

Execute:
    pip install streamlit pypdf
    streamlit run polar_sentinel/demo/sentinel_test_page.py
"""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime

import streamlit as st

from polar_sentinel import __version__
from polar_sentinel.reference.privacy_filter import filter_pii
from polar_sentinel.reference.injection_detector import detect_suspicious_patterns
from polar_sentinel.reference.hitl_approval import (
    create_pending_approval,
    approve_pending,
    consume_approval,
    payload_hash,
    reset_store,
)
from polar_sentinel.harness.adapters import MockAdapter, OpenAICompatibleAdapter
from polar_sentinel.harness.sentinel_pipeline import SentinelPipeline
from polar_sentinel.harness.orchestration import create_judicial_orchestrator
from polar_sentinel.attacks.corpus import CASES
from polar_sentinel.reference.explain import (
    build_explanation,
    CATEGORY_LABELS,
    LAYER_NAMES,
    LAYER_STEPS,
)

logging.disable(logging.CRITICAL)

NAVY = "#16243f"
BLUE = "#2f6fed"

st.set_page_config(
    page_title="Polar Sentinel: laboratorio de defesa",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------- estilo
st.markdown(
    f"""
    <style>
    .ps-title {{ font-size: 2.2rem; font-weight: 800; color: {NAVY}; margin: 0; }}
    .ps-sub {{ font-size: 1.05rem; color: #475569; margin-top: 0.2rem; }}
    .ps-tag {{ font-size: 0.85rem; color: #64748b; }}
    .ps-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;
               padding: 18px; }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<p class="ps-title">Polar Sentinel</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="ps-sub">Camada aberta de defesa em profundidade para uso seguro e '
    "soberano de IA no Judiciario brasileiro.</p>",
    unsafe_allow_html=True,
)
st.markdown(
    f'<p class="ps-tag">Versao {__version__}  |  Alinhado a Resolucao CNJ 615/2025 '
    "e a Manifestacao Tecnica CNIAJ 1/2026  |  Licenca Apache 2.0</p>",
    unsafe_allow_html=True,
)
st.divider()

with st.expander("Como o Polar Sentinel funciona, em uma olhada"):
    st.markdown(
        "O documento passa por uma sequencia de verificacoes antes de qualquer IA "
        "agir. Cada etapa tem um nome claro:"
    )
    for i, (nome, frase) in enumerate(LAYER_STEPS, start=1):
        st.markdown(f"**{i}. {nome}.** {frase}")


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Configuracao")

    st.subheader("Defesas ativas")
    enable_privacy = st.checkbox("Filtro de dados pessoais", value=True)
    enable_detection = st.checkbox("Detector de comandos suspeitos", value=True)

    st.subheader("Modelo ou API")
    use_real = st.checkbox("Usar API externa", value=False)
    if use_real:
        api_key = st.text_input("Chave da API", type="password")
        base_url = st.text_input("Base URL", "https://api.openai.com/v1")
        model = st.text_input("Modelo", "gpt-4o-mini")
        adapter = OpenAICompatibleAdapter(
            api_key=api_key or None, base_url=base_url, model=model
        )
    else:
        adapter = MockAdapter("Resposta segura gerada apos todas as defesas.")
        st.caption("Mock adapter ativo (seguro para demonstracao).")

    st.divider()
    st.caption("Agnostico de modelo. Soberania em primeiro lugar.")


orchestrator = create_judicial_orchestrator(
    include_privacy=enable_privacy,
    include_sanitize=True,
    include_detection=enable_detection,
)
pipeline = SentinelPipeline(adapter=adapter, custom_orchestrator=orchestrator)


# ---------------------------------------------------------------- exemplos
st.subheader("Casos de teste do corpus")
st.caption(
    "Exemplos com dados ficticios, cobrindo desde peticoes limpas ate os vetores "
    "mais sofisticados de injecao. Selecione um para carregar."
)

example_labels = {
    f"{'OK' if c.benign else c.severity.upper():7}  {c.name}": c for c in CASES
}
choice = st.selectbox("Escolha um caso", ["(documento proprio)"] + list(example_labels))
if choice != "(documento proprio)":
    selected = example_labels[choice]
    st.session_state["doc_text"] = selected.payload
    tipo = CATEGORY_LABELS.get(selected.category, selected.category)
    if selected.benign:
        st.success(f"**{selected.name}**. Este e um documento legitimo, sem ataque. "
                   "Use para ver o sistema liberar o que e seguro.")
    else:
        st.info(
            f"**{selected.name}**\n\n"
            f"Tipo de ataque: {tipo}\n\n"
            f"O que e: {selected.description}\n\n"
            f"Como o Polar Sentinel se defende: {selected.defense}"
        )


# ---------------------------------------------------------------- entrada
st.subheader("Documento")
col_in, col_prev = st.columns([1.1, 1])

with col_in:
    uploaded = st.file_uploader("Enviar PDF ou TXT", type=["pdf", "txt"])
    text_area = st.text_area(
        "Ou cole o texto do documento",
        value=st.session_state.get("doc_text", ""),
        height=220,
        placeholder="Cole aqui uma peticao, decisao ou qualquer documento judicial.",
    )

    document_text = ""
    if uploaded is not None:
        if uploaded.type == "application/pdf":
            try:
                from polar_sentinel.reference.pdf_inspector import evaluate_pdf

                pdf = evaluate_pdf(uploaded)
                insp = pdf.inspection
                # O texto oculto segue para as camadas, para que a ordem escondida
                # seja avaliada, e aparece em destaque para quem opera.
                document_text = "\n".join([insp.visible_text, insp.hidden_text, insp.metadata_text])
                if insp.hidden_spans:
                    motivos = sorted({s.reason for s in insp.hidden_spans})
                    aviso = st.error if pdf.flagged else st.warning
                    aviso(
                        "Este PDF tem texto que nao aparece para quem le a pagina "
                        f"({', '.join(motivos)}): {insp.hidden_text[:600]}"
                    )
            except Exception as exc:
                st.error(f"Erro ao ler o PDF: {exc}")
        else:
            document_text = uploaded.getvalue().decode("utf-8", errors="ignore")
    elif text_area:
        document_text = text_area

    action = st.selectbox(
        "Acao simulada",
        ["tribunal.protocolar", "tribunal.juntada", "tribunal.analyze", "tribunal.parecer"],
        index=0,
    )

with col_prev:
    st.markdown("**Previa de risco**")
    if document_text.strip():
        preview = filter_pii(document_text).text if enable_privacy else document_text
        score, reasons = detect_suspicious_patterns(preview)
        color = "#16a34a" if score < 0.3 else ("#ca8a04" if score < 0.6 else "#dc2626")
        st.markdown(
            f"""
            <div class="ps-card">
              <div style="background:#e5e7eb; height:20px; border-radius:6px; overflow:hidden;">
                <div style="width:{min(score*100,100):.0f}%; height:100%; background:{color};"></div>
              </div>
              <div style="text-align:center; margin-top:6px; font-weight:700; color:{NAVY};">
                Score de risco: {score:.2f}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if reasons and reasons != ["nenhum_padrao_suspeito"]:
            st.caption("Sinais: " + ", ".join(r.split(":")[0] for r in reasons[:4]))
    else:
        st.info("Insira um documento para ver a previa.")


# ---------------------------------------------------------------- analise
def _risk_band(score: float):
    if score < 0.3:
        return "#16a34a", "BAIXO"
    if score < 0.6:
        return "#ca8a04", "MEDIO"
    return "#dc2626", "ALTO"


def _markdown_report(result, action):
    color_label = _risk_band(result["risk_score"])[1]
    layers = json.dumps(result.get("layer_details", []), indent=2, ensure_ascii=False)
    return f"""# Relatorio de auditoria Polar Sentinel

Gerado em: {datetime.now().isoformat(timespec='seconds')}
Acao: {action}
Score de risco: {result['risk_score']:.2f} ({color_label})
Estado: {result['status']}

## Resumo
- Aprovacao humana obrigatoria: {result['hitl_required']}
- Identificador de aprovacao: {result.get('approval_id')}

## Resultados por camada
{layers}

## Conformidade (CNJ 615/2025)
- Art. 10 e 34: supervisao humana via portao L4.
- Art. 19: bloqueio de saidas com aparencia de decisao.
- LGPD e soberania: filtro de privacidade aplicado antes do modelo.
"""


if st.button(
    "Analisar com o Polar Sentinel", type="primary", disabled=not document_text.strip()
):
    result = pipeline.analyze_and_protect(
        document_text=document_text, action=action, user_id="lab_user"
    )
    st.session_state["last_result"] = result
    st.session_state["last_action"] = action

if "last_result" in st.session_state:
    result = st.session_state["last_result"]
    action = st.session_state.get("last_action", action)

    st.divider()
    st.subheader("Resultado da analise")

    # Extrai os sinais das camadas para montar a explicacao em linguagem simples.
    san_kinds = []
    det_reasons = []
    for layer in result.get("layer_details", []):
        meta = layer.get("metadata", {})
        if layer.get("layer") == "sanitizacao":
            san_kinds = [k for k, _ in meta.get("removed", [])]
        if layer.get("layer") == "deteccao":
            det_reasons = meta.get("reasons", [])

    exp = build_explanation(
        sanitization_kinds=san_kinds,
        detection_score=result["risk_score"],
        detection_reasons=det_reasons,
        hitl_required=result["hitl_required"],
        action=action,
    )

    # Veredito em destaque, em linguagem simples.
    st.markdown(
        f"""
        <div class="ps-card" style="border-left:6px solid {exp.cor};">
          <div style="font-size:0.8rem; color:#64748b;">VEREDITO</div>
          <div style="font-size:1.8rem; font-weight:800; color:{exp.cor};">
            {exp.veredito}
          </div>
          <div style="font-size:1.05rem; color:#1f2937; margin-top:6px;">{exp.resumo}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if exp.o_que_estava_escondido:
            st.markdown("#### O que estava escondido")
            for item in exp.o_que_estava_escondido:
                st.markdown(f"- {item}")
        else:
            st.markdown("#### O que estava escondido")
            st.markdown("- Nada. O documento nao tinha conteudo oculto.")
    with col_b:
        st.markdown("#### Como o Polar Sentinel identificou")
        for item in exp.como_identificamos:
            st.markdown(f"- {item}")

    st.markdown("#### Recomendacao")
    st.markdown(exp.recomendacao)

    # Detalhe tecnico, para quem quiser ir fundo.
    with st.expander("Ver detalhe tecnico por camada"):
        c1, c2, c3 = st.columns(3)
        c1.metric("Score de risco", f"{result['risk_score']:.2f}")
        c2.metric("Estado", result["status"])
        c3.metric("Aprovacao humana", "OBRIGATORIA" if result["hitl_required"] else "Nao")
        for layer in result.get("layer_details", []):
            icon = "🔴" if layer.get("blocked") else "🟢"
            nome = LAYER_NAMES.get(layer.get("layer", ""), layer.get("layer", ""))
            st.markdown(f"**{icon} {nome}**  (score {layer.get('score', 0)})")
            st.json(layer.get("metadata", {}))

    if result["hitl_required"]:
        st.warning(
            "Acao de alto risco ou com certificado digital. Exige aprovacao humana "
            "antes do protocolo."
        )
        col_ok, col_no = st.columns(2)
        if col_ok.button("Simular aprovacao humana", type="primary"):
            reset_store()
            digest = payload_hash(action, {"text": result["final_text"]})
            pend = create_pending_approval(action=action, payload={"text": result["final_text"]}, user_id="lab_user")
            approve_pending(pend.id, user_id="lab_user")
            ok = consume_approval(pend.id, action, digest)
            st.success(f"Aprovacao consumida com sucesso: {ok}. Acao liberada uma unica vez.")
        if col_no.button("Rejeitar"):
            st.error("Acao bloqueada. Nenhum protocolo sera realizado.")

    st.markdown("#### Exportar relatorio")
    report_md = _markdown_report(result, action)
    d1, d2 = st.columns(2)
    d1.download_button(
        "Baixar Markdown",
        data=report_md,
        file_name=f"relatorio_polar_sentinel_{datetime.now():%Y%m%d_%H%M}.md",
    )
    d2.download_button(
        "Baixar JSON",
        data=json.dumps(result, indent=2, ensure_ascii=False),
        file_name=f"resultado_polar_sentinel_{datetime.now():%Y%m%d_%H%M}.json",
    )

st.divider()
st.caption(
    "Polar Sentinel: defesa soberana, privada e auditavel para o Judiciario brasileiro."
)
