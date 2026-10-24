"""
LLM adapter. Two provider types:
  - "ollama": native /api/chat, so we can pass num_ctx (Ollama's OpenAI endpoint ignores it)
  - "openai": any OpenAI-compatible /chat/completions gateway (company API, vLLM, LM Studio...)

`stream_chat` yields text chunks; `complete` returns the whole answer (used by pipelines later).
"""
import json
from typing import AsyncIterator

import httpx

TIMEOUT = httpx.Timeout(connect=15, read=300, write=60, pool=15)


def _headers(p: dict) -> dict:
    h = {"Content-Type": "application/json"}
    if p.get("api_key"):
        h["Authorization"] = f"Bearer {p['api_key']}"
    for k, v in (p.get("extra_headers") or {}).items():
        h[k] = str(v).replace("{api_key}", p.get("api_key", ""))
    return h


def _client(p: dict) -> httpx.AsyncClient:
    # bypass_proxy=True ignores HTTP(S)_PROXY env vars (same effect as NO_PROXY for the gateway).
    return httpx.AsyncClient(verify=p.get("verify_ssl", True), trust_env=not p.get("bypass_proxy", True),
                             timeout=TIMEOUT, headers=_headers(p))


def _base(p: dict) -> str:
    if not p.get("base_url"):
        raise LLMError("No base URL configured for this provider (Settings → Model).")
    return p["base_url"].rstrip("/")


class LLMError(Exception):
    pass


async def _raise_for(r: httpx.Response):
    if r.status_code >= 400:
        body = (await r.aread()).decode("utf-8", "replace")[:500]
        raise LLMError(f"HTTP {r.status_code} from LLM: {body}")


async def stream_chat(messages: list[dict], p: dict) -> AsyncIterator[str]:
    try:
        async with _client(p) as c:
            if p["type"] == "ollama":
                body = {"model": p["model"], "messages": messages, "stream": True,
                        "options": {"num_ctx": p.get("context_tokens", 8192),
                                    "temperature": p.get("temperature", 0.1)}}
                async with c.stream("POST", f"{_base(p)}/api/chat", json=body) as r:
                    await _raise_for(r)
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        obj = json.loads(line)
                        if obj.get("error"):
                            raise LLMError(obj["error"])
                        if chunk := obj.get("message", {}).get("content"):
                            yield chunk
            else:
                body = {"model": p["model"], "messages": messages, "stream": True,
                        "temperature": p.get("temperature", 0.1)}
                async with c.stream("POST", f"{_base(p)}/chat/completions", json=body) as r:
                    await _raise_for(r)
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        obj = json.loads(data)
                        choices = obj.get("choices") or [{}]
                        if chunk := (choices[0].get("delta") or {}).get("content"):
                            yield chunk
    except httpx.HTTPError as e:
        raise LLMError(f"Cannot reach LLM at {p.get('base_url')}: {type(e).__name__}: {e}") from e


async def complete(messages: list[dict], p: dict) -> str:
    return "".join([c async for c in stream_chat(messages, p)])


async def list_models(p: dict) -> list[str]:
    try:
        async with _client(p) as c:
            if p["type"] == "ollama":
                r = await c.get(f"{_base(p)}/api/tags")
                await _raise_for(r)
                return [m["name"] for m in r.json().get("models", [])]
            r = await c.get(f"{_base(p)}/models")
            await _raise_for(r)
            return [m["id"] for m in r.json().get("data", [])]
    except httpx.HTTPError as e:
        raise LLMError(f"Cannot reach LLM at {p.get('base_url')}: {type(e).__name__}: {e}") from e
