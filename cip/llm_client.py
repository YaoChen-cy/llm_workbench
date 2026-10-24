"""
The only place that talks to the LLM. Adapt `_call_api` to your internal gateway.

Default implementation assumes an OpenAI-compatible /chat/completions endpoint.
LLM_MODE=mock returns canned responses from tests/fixtures/ so the pipeline can run offline.
"""
import json
import re
import time

import requests

import config

FIXTURES = config.ROOT / "tests" / "fixtures"


def call_llm(system: str, user: str, task: str = "") -> str:
    if config.LLM_MODE == "mock":
        return _mock(task)
    last_err = None
    for attempt in range(config.LLM_MAX_RETRIES + 1):
        try:
            return _call_api(system, user)
        except Exception as e:          # network / rate limit / 5xx
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after retries: {last_err}")


def _call_api(system: str, user: str) -> str:
    # ---- EDIT HERE if your internal API is not OpenAI-compatible ----
    resp = requests.post(
        f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}",
                 "Content-Type": "application/json"},
        json={
            "model": config.LLM_MODEL,
            "temperature": config.LLM_TEMPERATURE,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        },
        timeout=config.LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _mock(task: str) -> str:
    path = FIXTURES / f"mock_{task}.json"
    if not path.exists():
        path = FIXTURES / f"mock_{task}.md"
    return path.read_text(encoding="utf-8")


def parse_json(text: str):
    """Extract the first JSON object/array from a model response (tolerates ```json fences)."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    start = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=-1)
    if start == -1:
        raise ValueError("no JSON found in response")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj
