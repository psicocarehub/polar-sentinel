.PHONY: help install test bench heldout pdfs lab lint clean

help:
	@echo "Alvos disponiveis:"
	@echo "  install   instala o pacote em modo editavel com extras de dev"
	@echo "  test      roda a suite de testes"
	@echo "  bench     roda o benchmark sobre o corpus de desenvolvimento"
	@echo "  heldout   roda a avaliacao nos conjuntos de validacao e cegos"
	@echo "  pdfs      gera os PDFs de teste em polar_sentinel/attacks/samples"
	@echo "  lab       abre o laboratorio visual em Streamlit"
	@echo "  lint      roda o ruff, se instalado"
	@echo "  clean     remove artefatos de build e cache"

install:
	pip install -e ".[dev,lab,http]"

test:
	python -m pytest -q

bench:
	python -m polar_sentinel.benchmarks.agent_safety_bench

heldout:
	python -m polar_sentinel.benchmarks.heldout_eval

pdfs:
	python -m polar_sentinel.attacks.generate_test_pdfs

lab:
	streamlit run polar_sentinel/demo/sentinel_test_page.py

lint:
	ruff check . || true

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf build dist *.egg-info .pytest_cache
