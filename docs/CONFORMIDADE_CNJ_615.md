# Mapeamento de conformidade com a Resolucao CNJ 615/2025

Este documento relaciona, artigo a artigo, as exigencias da Resolucao CNJ
615/2025 com a linha de defesa do Polar Sentinel que as atende. A numeracao foi
conferida no ato oficial publicado pelo CNJ.

| Exigencia | Artigo | Linha de defesa | Como o Polar Sentinel atende |
| --- | --- | --- | --- |
| Participacao e supervisao humana em todas as etapas | Art. 2, V | L4 e L5 | Portao de aprovacao humana e trilha auditavel que torna a supervisao efetiva |
| Supervisao humana efetiva, periodica e adequada | Art. 3, VII | L4 e L5 | Aprovacao de uso unico mais registro por evento |
| Vedacao a solucoes sem revisao humana dos resultados | Art. 10, I | L4 | Acoes irreversiveis exigem aprovacao humana antes do commit |
| Uso auxiliar e complementar, vedado o uso autonomo de decisao | Art. 19, par. 3, II | L4 e L2 | Bloqueio de saidas com aparencia de decisao judicial |
| Vedacao de uso ou compartilhamento de dados do Judiciario para treinamento sem autorizacao | Art. 19, par. 3, III | Arquitetura | Soberania de jurisdicao e fronteira de sanitizacao para modelo externo |
| Uso auxiliar e complementar, vedado instrumento autonomo | Art. 20, IV | L4 | Mesma governanca de saida do Art. 19 |
| Avaliacao de grau de risco | Art. 9 e Art. 11 | Processo | O harness fornece evidencia para a classificacao de exposicao adversarial |
| Cadastro e catalogo na plataforma Sinapses | Art. 23, 24 e 25 | Documentacao | Atributos de exposicao adversarial prontos para inventario |
| Padroes de seguranca da informacao | Art. 26 a 31 | L1, L4 e L5 | Sanitizacao na entrada, least agency e trilha auditavel |
| Vedacao de compartilhamento de dados sigilosos sem anonimizacao | Art. 30 | L0 e Arquitetura | Filtro de privacidade antes do modelo |
| Revisao detalhada do conteudo gerado pelo usuario interno | Art. 32 | L4 e L5 | Previa estruturada e nada que substitua a autoridade final |
| Permitir a modificacao pelo magistrado | Art. 34 | L4 | A acao so prossegue apos confirmacao humana |
| Informar eventos adversos ao Comite Nacional em ate 72 horas | Art. 42, par. 2 | L5 | Registro estruturado por evento, com hash do payload e desfecho |

## Observacoes

* O texto da Resolucao 615/2025 nao menciona prompt injection de forma explicita.
  A sua camada de seguranca e geral. O tema foi tratado depois, pela
  Manifestacao Tecnica CNIAJ 1/2026, a quem o Polar Sentinel responde ponto a
  ponto no [texto completo](../paper/polar-sentinel.md).
* Fonte da numeracao: ato oficial CNJ 615/2025. Recomenda-se reconferir no PDF
  oficial antes de uso em peca formal, pois pode haver retificacoes.
