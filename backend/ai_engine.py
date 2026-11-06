"""
AI Engine: LLM wrapper for all agents.

Supports 6 providers, 4 of which are completely free:

  FREE (no credit card):
    1. Google Gemini  - set GEMINI_API_KEY  (best: 1M token context, 250 req/day)
    2. Groq           - set GROQ_API_KEY    (fastest: 500K tokens/day)
    3. GitHub Models   - set GITHUB_TOKEN    (50 req/day on heavy models)
    4. OpenRouter      - set OPENROUTER_API_KEY (free models with :free suffix)

  PAID:
    5. Anthropic Claude - set ANTHROPIC_API_KEY (~$0.50/proposal)
    6. OpenAI GPT       - set OPENAI_API_KEY

Priority order: whichever key is set first in the list above wins.
Set only ONE key. The engine uses that provider for everything.
"""
import os
import json
import logging
from typing import Type, TypeVar
from pydantic import BaseModel

logger = logging.getLogger("ai-engine")
T = TypeVar("T", bound=BaseModel)


class AIEngineError(Exception):
    pass


# Provider configs: (env_var, module, default_model, api_base_or_none)
PROVIDERS = [
    ("GEMINI_API_KEY",      "google",    "gemini-2.5-flash",           None),
    ("GROQ_API_KEY",        "openai",    "llama-3.1-70b-versatile",    "https://api.groq.com/openai/v1"),
    ("GITHUB_TOKEN",        "openai",    "gpt-4o",                     "https://models.inference.ai.azure.com"),
    ("OPENROUTER_API_KEY",  "openai",    "google/gemini-2.5-flash:free", "https://openrouter.ai/api/v1"),
    ("ANTHROPIC_API_KEY",   "anthropic", "claude-sonnet-4-20250514",   None),
    ("OPENAI_API_KEY",      "openai",    "gpt-4o",                     None),
]


def _detect_provider():
    """Find which API key is set and return (key, module_type, model, base_url)."""
    for env_var, mod_type, default_model, base_url in PROVIDERS:
        key = os.environ.get(env_var)
        if key:
            model = os.environ.get("AI_MODEL", default_model)
            return key, mod_type, model, base_url, env_var
    return None, None, None, None, None


def ai_think(system_prompt: str, user_prompt: str, max_tokens: int = 4000) -> str:
    """Send a thinking task to whichever LLM is configured."""
    key, mod_type, model, base_url, env_name = _detect_provider()
    if not key:
        raise AIEngineError(
            "No AI API key found. Set one of: GEMINI_API_KEY (free), "
            "GROQ_API_KEY (free), GITHUB_TOKEN (free), OPENROUTER_API_KEY (free), "
            "ANTHROPIC_API_KEY, or OPENAI_API_KEY."
        )

    logger.info(f"AI call via {env_name} model={model} ({len(user_prompt)} chars)")

    if mod_type == "google":
        return _call_gemini(key, model, system_prompt, user_prompt, max_tokens)
    elif mod_type == "anthropic":
        return _call_anthropic(key, model, system_prompt, user_prompt, max_tokens)
    else:
        return _call_openai_compatible(key, model, base_url, system_prompt, user_prompt, max_tokens)


def _call_gemini(key, model, system_prompt, user_prompt, max_tokens):
    """Google Gemini via the google-genai SDK."""
    try:
        from google import genai
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=model,
            contents=f"{system_prompt}\n\n{user_prompt}",
            config={"max_output_tokens": max_tokens},
        )
        return response.text
    except ImportError:
        # Fallback: use REST API directly
        import requests
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
            "generationConfig": {"maxOutputTokens": max_tokens}
        }
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_anthropic(key, model, system_prompt, user_prompt, max_tokens):
    """Anthropic Claude."""
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    r = client.messages.create(
        model=model, max_tokens=max_tokens, system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return r.content[0].text


def _call_openai_compatible(key, model, base_url, system_prompt, user_prompt, max_tokens):
    """OpenAI-compatible APIs: Groq, GitHub Models, OpenRouter, OpenAI."""
    import openai
    kwargs = {"api_key": key}
    if base_url:
        kwargs["base_url"] = base_url
    client = openai.OpenAI(**kwargs)
    r = client.chat.completions.create(
        model=model, max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return r.choices[0].message.content


def ai_think_json(system_prompt: str, user_prompt: str, schema: Type[T], max_tokens: int = 2000) -> T:
    """Send a task, parse response as validated Pydantic JSON."""
    raw = ai_think(system_prompt, user_prompt, max_tokens)
    text = raw.strip()
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
        else:
            raise AIEngineError(f"No valid JSON in response: {text[:300]}")
    return schema(**data)


def is_ai_available() -> bool:
    _, mod_type, _, _, _ = _detect_provider()
    return mod_type is not None


def get_ai_status() -> dict:
    key, mod_type, model, base_url, env_name = _detect_provider()
    if key:
        provider_names = {
            "GEMINI_API_KEY": "Google Gemini (FREE)",
            "GROQ_API_KEY": "Groq (FREE)",
            "GITHUB_TOKEN": "GitHub Models (FREE)",
            "OPENROUTER_API_KEY": "OpenRouter (FREE)",
            "ANTHROPIC_API_KEY": "Anthropic Claude (paid)",
            "OPENAI_API_KEY": "OpenAI GPT (paid)",
        }
        return {
            "available": True,
            "provider": provider_names.get(env_name, env_name),
            "model": model,
            "env_var": env_name,
            "cost": "Free" if "FREE" in provider_names.get(env_name, "") else "Paid per token",
        }
    return {
        "available": False,
        "provider": "none",
        "detail": "Set one of: GEMINI_API_KEY (free), GROQ_API_KEY (free), GITHUB_TOKEN (free), OPENROUTER_API_KEY (free), ANTHROPIC_API_KEY, or OPENAI_API_KEY",
    }
