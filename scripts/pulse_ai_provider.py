"""PULSE optional AI adapter; source/data/graphs remain independent of any model.

Default remains legacy Cloudflare for backward-compatible offline tests.
Mistral Small 4 is selected explicitly via PULSE_AI_PROVIDER=mistral.
No API request is performed merely by importing or configuring this module.
"""
from __future__ import annotations

import os

from scripts import pulse_cloudflare_llama as cloudflare

MISTRAL_MODEL = "mistral-small-2603"
MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_INPUT_USD_PER_MTOK = 0.15
MISTRAL_OUTPUT_USD_PER_MTOK = 0.60
MISTRAL_MAX_OUTPUT_TOKENS = 2200
MISTRAL_RUN_BUDGET_USD_ESTIMATE = 0.15


def active_provider():
    provider = os.getenv("PULSE_AI_PROVIDER", "cloudflare").strip().lower() or "cloudflare"
    if provider not in ("cloudflare", "mistral"):
        raise ValueError("unsupported_PULSE_AI_PROVIDER")
    return provider


def configure_environment():
    if active_provider() == "cloudflare":
        return cloudflare.configure_environment()
    key = os.getenv("PULSE_MISTRAL_API_KEY", "").strip()
    if not key:
        return False
    os.environ["PULSE_LLM_ENDPOINT"] = MISTRAL_ENDPOINT
    os.environ["PULSE_LLM_MODEL"] = MISTRAL_MODEL
    os.environ["PULSE_LLM_API_KEY"] = key
    os.environ["PULSE_LLM_MAX_OUTPUT_TOKENS"] = str(MISTRAL_MAX_OUTPUT_TOKENS)
    return True


def reserved_cost(prompt):
    """Maximum-token conservative estimate, not provider billing or monthly cap."""
    if active_provider() == "cloudflare":
        return cloudflare.reserved_neurons(prompt)
    # Italian: reserve one input token per two characters plus protocol overhead.
    input_tokens = (len(prompt) + 1) // 2 + 100
    return (input_tokens * MISTRAL_INPUT_USD_PER_MTOK +
            MISTRAL_MAX_OUTPUT_TOKENS * MISTRAL_OUTPUT_USD_PER_MTOK) / 1_000_000


def run_budget_limit():
    return (cloudflare.BUDGET_NEURONS if active_provider() == "cloudflare"
            else MISTRAL_RUN_BUDGET_USD_ESTIMATE)


def budget_unit():
    return ("neurons_estimate" if active_provider() == "cloudflare"
            else "USD_upper_estimate")


def credentials_status():
    return "missing_" + active_provider() + "_credentials"
