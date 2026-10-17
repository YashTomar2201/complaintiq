"""Thin wrapper around the LLM provider (Google Gemini, free tier). Everything else calls `complete()` only,
so swapping providers (or using a fake in tests) means changing this file alone.

Free tiers have rate limits, so every call is throttled (requests per minute) and retried with a growing pause.

Usage: python -m src.ai.llm models      # list the models your key can use
"""
import os
import sys
import time
from dataclasses import dataclass

from dotenv import load_dotenv

from src.ingest.cfpb import ROOT

load_dotenv(ROOT / ".env")

DEFAULT_MODEL = "gemini-2.5-flash"   # override with GEMINI_MODEL in .env
DEFAULT_RPM = 10                      # stay well under free-tier limits; override with GEMINI_RPM


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int


class GeminiClient:
    def __init__(self, model=None, rpm=None):
        from google import genai  # imported here so tests that use a fake client need no SDK/key
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise SystemExit("GEMINI_API_KEY is not set. Add it to .env (see .env.example).")
        self.client = genai.Client(api_key=key)
        self.model_name = model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
        self.min_gap = 60.0 / float(rpm or os.getenv("GEMINI_RPM") or DEFAULT_RPM)
        self._last_call = 0.0

    def complete(self, system, user, schema, attempts=5):
        """Ask for JSON that matches the pydantic `schema`. Returns LLMResult."""
        from google.genai import errors, types
        config = types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json",
                                             response_schema=schema, temperature=0)
        for i in range(1, attempts + 1):
            wait = self.min_gap - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()
            try:
                r = self.client.models.generate_content(model=self.model_name, contents=user, config=config)
                u = r.usage_metadata
                return LLMResult(r.text or "", getattr(u, "prompt_token_count", 0) or 0,
                                 getattr(u, "candidates_token_count", 0) or 0)
            except errors.APIError as e:
                retryable = e.code in (429, 500, 503, 504)
                if not retryable or i == attempts:
                    raise
                time.sleep(min(2 ** i * 5, 60))  # 10s, 20s, 40s, 60s: rate limits usually clear within a minute


def get_client():
    return GeminiClient()


def list_models():
    from google import genai
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return sorted(m.name.removeprefix("models/") for m in client.models.list()
                  if "generateContent" in (m.supported_actions or []))


if __name__ == "__main__":
    if sys.argv[1:] == ["models"]:
        print("\n".join(list_models()))
    else:
        raise SystemExit(__doc__)
