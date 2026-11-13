"""Cloudflare Workers AI configuration for PULSE's original Italian news engine.

This never connects to legacy pulse-tommy-api, reads its secrets, or deploys
Workers. The official Cloudflare AI REST endpoint runs a hosted Llama model.
"""
from __future__ import annotations

import os
import re

MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
ACCOUNT = re.compile(r"[0-9a-f]{32}", re.I)
BUDGET_NEURONS = 8200
MAX_OUTPUT_TOKENS = 1400
INPUT_NEURONS_PER_MILLION = 26668
OUTPUT_NEURONS_PER_MILLION = 204805


def configured():
    return bool(os.getenv("PULSE_CF_ACCOUNT_ID") and os.getenv("PULSE_CF_AI_TOKEN"))


def configure_environment():
    """Set the expected API variables without exposing or logging any secret."""
    account = os.getenv("PULSE_CF_ACCOUNT_ID", "").strip()
    token = os.getenv("PULSE_CF_AI_TOKEN", "").strip()
    if not account or not token:
        return False
    if not ACCOUNT.fullmatch(account):
        raise ValueError("invalid_Cloudflare_account_id")
    # A Cloudflare Workers AI REST v1 endpoint, NOT the user's old Worker URL.
    os.environ["PULSE_LLM_ENDPOINT"] = (
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions"
    )
    os.environ["PULSE_LLM_MODEL"] = MODEL
    os.environ["PULSE_LLM_API_KEY"] = token
    os.environ["PULSE_LLM_MAX_OUTPUT_TOKENS"] = str(MAX_OUTPUT_TOKENS)
    return True


def reserved_neurons(prompt, max_output_tokens=MAX_OUTPUT_TOKENS):
    """Conservative preflight estimate, not the provider's exact consumption."""
    # Italian text often uses ~3 characters/token; assume TWO characters
    # per input token and reserve the entire max output, not just actual output.
    prompt_tokens = max(1, (len(prompt) + 1) // 2) + 100
    return ((prompt_tokens * INPUT_NEURONS_PER_MILLION) +
            (int(max_output_tokens) * OUTPUT_NEURONS_PER_MILLION)) / 1_000_000


def remaining_for_run(used=0.0):
    return max(0.0, BUDGET_NEURONS - float(used))
