"""Polar Sentinel — Adapters para integração com qualquer API/LLM.

Permite plugar qualquer modelo ou API (compatível com OpenAI, hospedada ou local)
no harness e no pipeline.

Exemplo de uso:
    from polar_sentinel.harness.adapters import OpenAICompatibleAdapter, MockAdapter
    from polar_sentinel.harness.sentinel_pipeline import SentinelPipeline

    adapter = OpenAICompatibleAdapter(api_key=..., base_url="https://api.openai.com/v1")
    pipeline = SentinelPipeline(adapter=adapter)

    result = pipeline.analyze_and_protect(text, action="tribunal.xxx", user_id="...")
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict


class BaseAdapter(ABC):
    """Interface que qualquer API deve implementar para usar no Sentinel."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """Gera resposta do modelo. Deve ser seguro e após sanitização."""
        raise NotImplementedError

    def __call__(self, prompt: str, **kwargs) -> str:
        return self.generate(prompt, **kwargs)


class MockAdapter(BaseAdapter):
    """Adapter de mock para testes e desenvolvimento."""

    def __init__(self, response: str = "Resposta simulada limpa."):
        self.response = response

    def generate(self, prompt: str, **kwargs) -> str:
        # Simula comportamento "seguro"
        if "ignore" in prompt.lower() or "inject" in prompt.lower():
            return "Ação bloqueada por Sentinel (mock)."
        return self.response


class OpenAICompatibleAdapter(BaseAdapter):
    """
    Adapter para qualquer API compatível com OpenAI, hospedada ou local.

    Exemplo:
        adapter = OpenAICompatibleAdapter(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url="https://sua-api/v1",
            model="seu-modelo"
        )
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: int = 60,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

        try:
            import httpx
            self._client = httpx.Client(timeout=timeout)
        except ImportError:
            self._client = None

    def generate(self, prompt: str, **kwargs) -> str:
        if self._client is None:
            raise ImportError("Instale httpx: pip install httpx")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", 0.2),
            "max_tokens": kwargs.get("max_tokens", 1024),
        }

        url = f"{self.base_url}/chat/completions"
        resp = self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


class CustomFunctionAdapter(BaseAdapter):
    """Adapter que usa qualquer função callable que você passar."""

    def __init__(self, fn: Callable[[str], str]):
        self.fn = fn

    def generate(self, prompt: str, **kwargs) -> str:
        return self.fn(prompt)
