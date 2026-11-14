"""PULSE AI provider adapter: prefer DeepSeek Flash V4.1, no legacy Worker.

Credential never reaches source control or logs; Actions injects a GitHub secret.
DeepSeek pricing uses conservative peak rates in estimates, not a billing API.
"""
from __future__ import annotations

import os
from scripts import pulse_cloudflare_llama as cf

DEEPSEEK_MODEL = "deepseek-flash"  # DeepSeek-V4.1-Flash-1017 official API alias
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MAX_OUTPUT_TOKENS = 2200
# Estimates use peak (highest) USD per million token rates for DeepSeek Flash.
DEEPSEEK_INPUT_PER_MILLION = 0.30
DEEPSEEK_OUTPUT_PER_MILLION = 1.20
DEEPSEEK_PER_RUN_ESTIMATE_LIMIT_USD = 0.15


def active_provider():
    preferred = os.getenv("PULSE_AI_PROVIDER", "").strip().lower()
    if preferred not in ("", "deepseek", "cloudflare"):
        raise ValueError("invalid_PULSE_AI_PROVIDER")
    if preferred:
        return preferred
    return "deepseek" if os.getenv("PULSE_DEEPSEEK_API_KEY", "").strip() else "cloudflare"


def configured():
    provider = active_provider()
    if provider == "deepseek":
        return bool(os.getenv("PULSE_DEEPSEEK_API_KEY", "").strip())
    return cf.configured()


def configure_environment():
    provider = active_provider()
    if provider == "cloudflare":
        return cf.configure_environment()
    token = os.getenv("PULSE_DEEPSEEK_API_KEY", "").strip()
    if not token:
        return False
    os.environ["PULSE_LLM_ENDPOINT"] = DEEPSEEK_ENDPOINT
    os.environ["PULSE_LLM_MODEL"] = DEEPSEEK_MODEL
    os.environ["PULSE_LLM_API_KEY"] = token
    os.environ["PULSE_LLM_MAX_OUTPUT_TOKENS"] = str(DEEPSEEK_MAX_OUTPUT_TOKENS)
    return True


def run_budget_limit():
    return DEEPSEEK_PER_RUN_ESTIMATE_LIMIT_USD if active_provider() == "deepseek" else cf.BUDGET_NEURONS


def reserved_budget(prompt):
    """Worst-case *estimation*, not a guarantee or account-level monthly cap."""
    if active_provider() == "cloudflare":
        return cf.reserved_neurons(prompt)
    # Estimate conservative prompt tokens as at most two characters per token,
    # plus overhead; output tokens reserved in full even if not consumed.
    input_tokens = (len(prompt) + 1) // 2 + 100
    return (input_tokens * DEEPSEEK_INPUT_PER_MILLION +
            DEEPSEEK_MAX_OUTPUT_TOKENS * DEEPSEEK_OUTPUT_PER_MILLION) / 1_000_000


def budget_unit():
    return "usd_peak_estimate" if active_provider() == "deepseek" else "cloudflare_neurons_estimate"
