import json

import httpx
from django.conf import settings
from openai import OpenAI


def call_ollama(system, user, model=None, timeout=120):
    if not model:
        model = settings.OLLAMA_DEFAULT_MODEL
    """Call Ollama chat API and return parsed JSON."""
    resp = httpx.post(
        f"{settings.OLLAMA_BASE_URL}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "format": "json",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["message"]["content"])


def call_openai(system, user, model=None, max_tokens=4096):
    """Call OpenAI chat API and return parsed JSON."""
    if not model:
        model = settings.OPENAI_DEFAULT_MODEL
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)
