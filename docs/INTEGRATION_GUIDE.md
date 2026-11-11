# Guia de integracao do Polar Sentinel

Este guia mostra como sistemas judiciais incorporam as defesas do Polar Sentinel
de forma incremental, sem precisar substituir as ferramentas existentes.

## Instalacao

```bash
pip install -e .
```

O nucleo nao tem dependencias externas. Os extras opcionais sao lab, http, ml e
dev, descritos no README.

## Integracao minima recomendada

### 1. Sanitizacao L1 em toda ingestao

Aplique a sanitizacao em todos os pontos de entrada, isto e, uploads, crawlers,
automacao de navegador e pesquisa web, antes de indexar em uma base de
recuperacao ou enviar ao modelo.

```python
from polar_sentinel import sanitize_with_audit

resultado = sanitize_with_audit(texto_extraido, source="pje_upload")
texto_limpo = resultado.text
trilha = [(e.kind, e.count) for e in resultado.entries]  # para o log de auditoria
```

Inspecione tambem os metadados do documento, pois sao um canal de injecao. No
caso de PDF, concatene o texto extraido com os campos de metadados antes de
sanitizar.

### 2. Deteccao L2 antes do dispatch

```python
from polar_sentinel import detect_suspicious_patterns

score, razoes = detect_suspicious_patterns(texto_limpo)
if score > 0.4:
    encaminhar_para_revisao(razoes)
```

### 3. Portao de aprovacao humana L4 para acoes com certificado

O fluxo tem tres etapas que o agente nunca percorre sozinho:

1. o agente gera a previa e cria uma aprovacao pendente;
2. um humano, dono da acao, aprova na interface;
3. o commit so executa apos consumir a aprovacao, que e de uso unico, dentro da
   janela de validade e com o hash do payload conferido.

```python
from polar_sentinel import (
    create_pending_approval, approve_pending, consume_approval, payload_hash,
)

payload = {"tribunal": "TRT-8", "processo": "...", "pdf_sha256": "..."}
digest = payload_hash("tribunal.protocolar", payload)

pend = create_pending_approval(
    action="tribunal.protocolar", payload=payload, user_id="advogada_1"
)
# ... a interface mostra a previa, o humano aprova ...
approve_pending(pend.id, user_id="advogada_1")

if not consume_approval(pend.id, "tribunal.protocolar", digest):
    raise PermissionError("aprovacao humana obrigatoria")
# so aqui a acao com certificado pode prosseguir
```

Nunca permita que o agente chame o commit diretamente.

### 4. Proveniencia de trechos L3

```python
from polar_sentinel import add_provenance, check_provenance

chunk = add_provenance(texto_do_trecho, source="stj_jurisprudencia.json")
ok, motivo = check_provenance(chunk, expected_sources=["stj", "stf"])
```

Armazene a origem e o hash de cada trecho antes de indexar, e revalide na
recuperacao. Separe o acervo oficial verificado do conteudo externo nao validado.

### 5. Trilha de auditoria L5

Registre, no minimo, o hash do prompt em vez do prompt completo, a decisao da
deteccao, as ferramentas chamadas com o hash do resultado, o identificador da
aprovacao humana quando aplicavel e o desfecho final.

## Pipeline pronto

Se preferir uma integracao de alto nivel, use o pipeline, que orquestra as
camadas e aplica o portao humano de forma automatica.

```python
from polar_sentinel import SentinelPipeline
from polar_sentinel.harness.adapters import OpenAICompatibleAdapter

pipeline = SentinelPipeline(
    adapter=OpenAICompatibleAdapter(base_url="https://sua-api/v1", model="seu-modelo")
)
resultado = pipeline.analyze_and_protect(
    document_text=texto, action="tribunal.protocolar", user_id="advogada_1"
)
```

## Mapeamento com a Resolucao CNJ 615/2025

| Exigencia | Artigo | Linha de defesa | Evidencia no harness |
| --- | --- | --- | --- |
| Revisao e supervisao humana ao longo do ciclo | Art. 2 V, 10 I, 34 | L4 | portao de aprovacao com testes |
| Vedacao a saidas com aparencia de decisao autonoma | Art. 19 par. 3 II | L4 e L2 | bloqueio de linguagem decisoria |
| Eventos adversos ao Comite em ate 72 horas | Art. 42 par. 2 | L5 | padrao de trilha auditavel |
| Dados sob jurisdicao brasileira, sem treino por terceiros | Art. 19 par. 3 III, 30 | Arquitetura | sanitizacao e fronteira externa |

O mapeamento artigo a artigo completo esta em
[CONFORMIDADE_CNJ_615.md](CONFORMIDADE_CNJ_615.md).

## Harness em integracao continua

```bash
python -m pytest -q
python -m polar_sentinel.benchmarks.agent_safety_bench
```

Inclua esses passos no pipeline de qualquer sistema que use agentes para gerar
pecas ou protocolar.

## Contato

Duvidas e sugestoes: abra uma issue no repositorio. Vulnerabilidades seguem o
[SECURITY.md](../SECURITY.md).
