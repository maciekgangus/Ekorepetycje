"""LLM chat service — Ollama (dev/CPU) or Amazon Bedrock (prod).

Switch via env var:
  LLM_PROVIDER=ollama   (default) → http://ollama:11434
  LLM_PROVIDER=bedrock            → boto3 bedrock-runtime

Ollama model:   OLLAMA_MODEL=llama3.2:3b  (default, ~2 GB RAM)
                            llama3.1:8b   (better quality, ~5 GB RAM)
Bedrock model:  BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
"""

from __future__ import annotations

import json
import logging
import os
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Jesteś pomocnym asystentem platformy Ekorepetycje — serwisu korepetycji online \
łączącego uczniów z doświadczonymi nauczycielami.

Pomagasz użytkownikom w sprawach takich jak:
- Dostępne przedmioty (matematyka, programowanie, języki obce i inne)
- Sposób rezerwacji lekcji i korzystania z platformy
- Cennik i pakiety godzin
- Polityka odwoływania zajęć (24 h przed lekcją — bez opłat)
- Jak znaleźć odpowiedniego nauczyciela
- Bezpieczeństwo danych i polityka prywatności

Zawsze odpowiadaj po polsku. Bądź przyjazny, zwięzły i konkretny — odpowiedź w 2–4 zdaniach \
wystarczy, chyba że pytanie wymaga szczegółów.
Jeśli nie znasz odpowiedzi lub pytanie wykracza poza zakres platformy, zaproponuj kontakt \
przez formularz na stronie."""


# ---------------------------------------------------------------------------
# Ollama (dev / CPU)
# ---------------------------------------------------------------------------

class OllamaChatService:
    """Streams responses from a local Ollama server."""

    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
        self.model    = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json={"model": self.model, "messages": full_messages, "stream": True},
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line:
                            data = json.loads(line)
                            if chunk := data.get("message", {}).get("content", ""):
                                yield chunk
        except Exception as exc:
            logger.error("Ollama error: %s", exc)
            yield "Przepraszam, wystąpił błąd połączenia z modelem. Spróbuj ponownie za chwilę."


# ---------------------------------------------------------------------------
# Amazon Bedrock (prod)
# ---------------------------------------------------------------------------

class BedrockChatService:
    """Streams responses from Amazon Bedrock (Claude models).

    IAM requirement: bedrock:InvokeModelWithResponseStream on the model ARN.
    Attach the policy to the EC2 instance role — no extra API keys needed.

    Recommended models:
      anthropic.claude-3-haiku-20240307-v1:0   — cheapest, fast
      anthropic.claude-3-5-haiku-20241022-v1:0 — smarter, still cheap
    Note: Claude models require us-east-1 or us-west-2.
    """

    def __init__(self) -> None:
        self.model_id = os.getenv(
            "BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
        )
        self.region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        import asyncio
        import boto3

        client = boto3.client("bedrock-runtime", region_name=self.region)
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "system": SYSTEM_PROMPT,
            "messages": messages,
            "max_tokens": 1024,
        })
        try:
            response = await asyncio.to_thread(
                client.invoke_model_with_response_stream,
                modelId=self.model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            for event in response["body"]:
                chunk = event.get("chunk")
                if chunk:
                    data = json.loads(chunk.get("bytes", b"{}"))
                    if data.get("type") == "content_block_delta":
                        yield data.get("delta", {}).get("text", "")
        except Exception as exc:
            logger.error("Bedrock error: %s", exc)
            yield "Przepraszam, wystąpił błąd. Spróbuj ponownie za chwilę."


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_chat_service() -> OllamaChatService | BedrockChatService:
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider == "bedrock":
        return BedrockChatService()
    return OllamaChatService()
