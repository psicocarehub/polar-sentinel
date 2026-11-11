"""Polar Sentinel: testes do tradutor para linguagem simples."""

from __future__ import annotations

from polar_sentinel.reference.explain import build_explanation, CATEGORY_LABELS
from polar_sentinel.attacks.corpus import categories


def test_documento_limpo_e_seguro():
    exp = build_explanation(
        sanitization_kinds=[],
        detection_score=0.0,
        detection_reasons=["nenhum_padrao_suspeito"],
        hitl_required=False,
    )
    assert exp.veredito == "SEGURO"
    assert not exp.o_que_estava_escondido
    assert exp.como_identificamos  # sempre explica que analisou


def test_ataque_e_perigoso_e_explicado_em_linguagem_simples():
    exp = build_explanation(
        sanitization_kinds=["unicode_tag_chars"],
        detection_score=0.8,
        detection_reasons=["override_canonico_ignore_instrucoes"],
        hitl_required=True,
    )
    assert exp.veredito == "PERIGOSO"
    # As frases devem ser legiveis, nao codigos tecnicos.
    assert any("invisiveis" in s for s in exp.o_que_estava_escondido)
    assert any("ignorar" in s for s in exp.o_que_estava_escondido)
    assert any("L4" in s or "aprovacao humana" in s for s in exp.como_identificamos)
    assert exp.recomendacao


def test_todas_as_categorias_tem_rotulo_amigavel():
    for cat in categories():
        assert cat in CATEGORY_LABELS, f"categoria sem rotulo leigo: {cat}"
