"""
llm/client.py – async client for any OpenAI-compatible chat endpoint.

Works with:
  - llama.cpp  (local, no key)
  - GitHub Models  (https://models.inference.ai.azure.com, GitHub PAT)
  - OpenAI API     (https://api.openai.com, OPENAI_API_KEY)
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

log = logging.getLogger("mineai.llm")


class LlamaClient:
    """
    Async wrapper around any OpenAI-compatible /v1/chat/completions endpoint.

    Pass `api_key` for cloud providers (GitHub Models, OpenAI).
    Leave it as None for local llama.cpp (no auth header sent).
    """

    def __init__(
        self,
        base_url: str,
        model:    str = "local-model",
        timeout:  int = 60,
        api_key:  str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model    = model
        self._timeout  = aiohttp.ClientTimeout(total=timeout)
        self._api_key  = api_key
        self._session: aiohttp.ClientSession | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._session = aiohttp.ClientSession(
                timeout=self._timeout, headers=headers
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Chat completion (OpenAI-compatible) ───────────────────────────────────

    async def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.3,
        stop: list[str] | None = None,
    ) -> str:
        """
        Call /v1/chat/completions and return the assistant reply as a string.
        """
        payload: dict[str, Any] = {
            "model":       self._model,
            "messages":    messages,
            "max_tokens":  max_tokens,
            "temperature": temperature,
            "stream":      False,
        }
        if stop:
            payload["stop"] = stop

        session = await self._get_session()
        url     = f"{self._base_url}/v1/chat/completions"

        log.debug("POST %s  (%d messages)", url, len(messages))

        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"LLM error {resp.status}: {body[:200]}")
                data = await resp.json()
                content: str = data["choices"][0]["message"]["content"]
                log.debug("LLM response (%d chars): %s…", len(content), content[:80])
                return content
        except aiohttp.ClientConnectorError as exc:
            raise RuntimeError(
                f"Cannot reach LLM server at {self._base_url}. "
                "Check that it is running or that the endpoint URL is correct."
            ) from exc

    # ── Convenience: raw completion (fallback) ────────────────────────────────

    async def complete(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.3,
        stop: list[str] | None = None,
    ) -> str:
        """Call the native /completion endpoint."""
        payload: dict[str, Any] = {
            "prompt":      prompt,
            "n_predict":   max_tokens,
            "temperature": temperature,
            "stream":      False,
        }
        if stop:
            payload["stop"] = stop

        session = await self._get_session()
        url     = f"{self._base_url}/completion"
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"LLM error {resp.status}: {body[:200]}")
            data = await resp.json()
            return data["content"]
