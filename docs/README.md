# Documentacao do Polar Sentinel

Indice da documentacao tecnica e institucional.

## Comece por aqui (linguagem simples)

* [Tipos de ataque explicados](TIPOS_DE_ATAQUE_EXPLICADOS.md). Todos os tipos de
  ataque de IA que cobrimos, incluindo audio, sem termos tecnicos.
* Versao em PDF com a identidade Polar, pronta para enviar a tribunais e leigos,
  em `polar_sentinel/publishing/Polar_Sentinel_Tipos_de_Ataque.pdf`. Para regenerar:
  `python -m polar_sentinel.publishing.build_guide_pdf`.

## Para entender o produto

* [Texto completo](../paper/polar-sentinel.md). O que a camada faz, como foi
  medida e o que ela pega e deixa passar.
* [Avaliacao](AVALIACAO.md). Protocolo, dados reais, conjuntos cegos e numeros de
  cada rodada.
* [Arquitetura](ARQUITETURA.md). Organizacao do codigo e fluxo de dados.

## Para entender a ameaca

* [Modelo de ameacas](MODELO_DE_AMEACAS.md). Incidentes reais no mundo, taxonomia
  tecnica e mapeamento para OWASP e MITRE ATLAS.
* [Catalogo de ataques](CATALOGO_DE_ATAQUES.md). Lista executavel dos vetores do
  corpus, gerada a partir de attacks/corpus.py.
* [Relatorio de pesquisa](pesquisa/RELATORIO-PESQUISA-PROMPT-INJECTION-JUDICIARIO.md).
  Fonte primaria com incidentes, datas, numeros e enderecos.

## Para integrar

* [Guia de integracao](INTEGRATION_GUIDE.md). Como incorporar as defesas de forma
  incremental, com mapeamento para a Resolucao CNJ 615/2025.

## Conformidade

* [Mapeamento da Resolucao CNJ 615/2025](CONFORMIDADE_CNJ_615.md), artigo a artigo.
* Resolucao CNJ 396/2021, estrategia de seguranca cibernetica.
* Manifestacao Tecnica CNIAJ 1/2026, mitigacao de injecao de comandos.
