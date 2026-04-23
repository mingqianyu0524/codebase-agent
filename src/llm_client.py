"""OpenAI-compatible LLM wrapper (default: Kimi internal deployment)."""
from __future__ import annotations

import time
from typing import Optional

import httpx
from openai import OpenAI, APIError, RateLimitError

from .config import load_config, resolve_api_key


class LLMClient:
    def __init__(self, provider: str = "kimi", config: Optional[dict] = None):
        cfg = config or load_config()
        llm_cfg = cfg["llm"]
        prov_cfg = llm_cfg["providers"][provider]
        api_key = resolve_api_key(prov_cfg)
        if not api_key:
            raise RuntimeError(
                f"API key not set for provider '{provider}'. "
                f"Check 'api_key' or 'api_key_env' in agent_config.yaml."
            )
        self.client = OpenAI(
            base_url=prov_cfg["base_url"],
            api_key=api_key,
            http_client=httpx.Client(trust_env=False, timeout=120.0),  # bypass system proxy for internal endpoints
        )
        self.model = prov_cfg["default_model"]
        self.fallback_models: list[str] = list(prov_cfg.get("fallback_models") or [])
        self.max_tokens = llm_cfg.get("max_tokens", 4096)
        self.temperature = llm_cfg.get("temperature", 0.3)

    def _is_rate_limit(self, err: Exception) -> bool:
        if isinstance(err, RateLimitError):
            return True
        status = getattr(err, "status_code", None)
        if status == 429:
            return True
        # OpenRouter surfaces upstream 429s inside APIError payloads.
        msg = str(err)
        return "429" in msg or "rate-limit" in msg.lower() or "rate limit" in msg.lower()

    def complete(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        system: Optional[str] = None,
        retries: int = 3,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        model_chain = [model] if model else [self.model, *self.fallback_models]
        last_err: Exception | None = None

        for idx, m in enumerate(model_chain):
            for attempt in range(retries):
                try:
                    resp = self.client.chat.completions.create(
                        model=m,
                        messages=messages,
                        max_tokens=max_tokens or self.max_tokens,
                        temperature=temperature if temperature is not None else self.temperature,
                    )
                    if idx > 0:
                        print(f"[llm] succeeded on fallback model: {m}")
                    return resp.choices[0].message.content or ""
                except (RateLimitError, APIError) as e:
                    last_err = e
                    if self._is_rate_limit(e):
                        has_fallback_left = idx < len(model_chain) - 1
                        if has_fallback_left:
                            print(f"[llm] rate-limited on {m}; falling back to {model_chain[idx+1]}")
                            break  # move to next model immediately
                        time.sleep(2 ** attempt * 5)
                    else:
                        time.sleep(2 ** attempt)
        raise RuntimeError(
            f"LLM call failed across models {model_chain}: {last_err}"
        )


if __name__ == "__main__":
    client = LLMClient()
    print(f"Model: {client.model}")
    reply = client.complete("Reply with exactly: pong")
    print(f"Reply: {reply!r}")
