# Como contribuir

Obrigado pelo interesse em fortalecer a defesa dos sistemas de IA do Judiciario.

## Formas de contribuir

* Tribunais: enviem casos reais de ataque, sempre anonimizados, como novos
  casos do corpus.
* Desenvolvedores de sistemas judiciais: enviem PRs de integracao e adaptadores
  para outros parsers de documento.
* Pesquisadores: estendam o corpus de ataques, o benchmark e os detectores.

## Regras basicas

* Nunca inclua dados pessoais reais, sigilosos ou sob segredo de justica.
  Use apenas dados ficticios, como os do corpus.
* Vulnerabilidades seguem a politica de [SECURITY.md](SECURITY.md), nao via
  issue publica.
* Todo PR deve manter a suite de testes verde e o benchmark sem regressao.

## Ambiente de desenvolvimento

```bash
pip install -e ".[dev,lab,http]"
make test
make bench
make pdfs
```

## Adicionar um novo vetor de ataque

1. Adicione um `AttackCase` em `attacks/corpus.py`, com dados ficticios,
   categoria, referencia OWASP, severidade, camada alvo e defesa esperada.
2. Se aplicavel, defina a `pdf_technique` para que o gerador produza o PDF.
3. Rode `make test`. O teste orientado pelo corpus garante que todo ataque seja
   barrado e todo benigno passe. Se o seu vetor escapar, esse e o sinal de que
   uma camada precisa ser estendida.

## Estilo

* Codigo e comentarios em portugues claro.
* Funcoes pequenas, nomes descritivos, sem dependencias desnecessarias no nucleo.
