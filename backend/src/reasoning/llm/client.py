from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class LLMClient(Protocol):
    def stream(self, messages: list[dict], *, temperature: float = 0.2) -> AsyncIterator[str]: ...


class LiteLLMClient:
    def __init__(self, model: str, api_base: str):
        self.model = f"openai/{model}"
        self.api_base = api_base

    async def stream(self, messages: list[dict], *, temperature: float = 0.2) -> AsyncIterator[str]:
        from litellm import acompletion

        resp = await acompletion(model=self.model, api_base=self.api_base, api_key="local",
                                 messages=messages, temperature=temperature, stream=True)
        async for chunk in resp:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class FakeLLMClient:
    def __init__(self, reply: str):
        self.reply = reply
        self.last_messages: list[dict] = []

    async def stream(self, messages: list[dict], *, temperature: float = 0.2) -> AsyncIterator[str]:
        self.last_messages = messages
        n = len(self.reply)
        for i in range(3):
            yield self.reply[i * n // 3:(i + 1) * n // 3]


class FailingLLMClient:
    """Yields one chunk then raises — exercises mid-stream failure handling."""

    def __init__(self, reply: str):
        self.reply = reply
        self.last_messages: list[dict] = []

    async def stream(self, messages: list[dict], *, temperature: float = 0.2) -> AsyncIterator[str]:
        self.last_messages = messages
        yield self.reply
        raise RuntimeError("llm stream failed")
