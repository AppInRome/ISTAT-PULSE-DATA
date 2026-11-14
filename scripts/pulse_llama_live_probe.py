#!/usr/bin/env python3
"""Prove the *actual* Cloudflare Llama endpoint, never just the presence of env vars.

The probe consumes only one short Workers AI generation. Its on-disk result is
safe to publish as CI diagnostic: no account identifiers, keys, URLs or prompts.
No story is published or approved by the probe.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request

from scripts.pulse_cloudflare_llama import MODEL, configure_environment

def probe_llama(request_fn=None):
    import os
    result = {"model": MODEL, "tested_at": datetime.now(timezone.utc).isoformat(),
              "status": "unavailable", "authenticated_generation": False}
    if not (os.getenv("PULSE_CF_ACCOUNT_ID") and os.getenv("PULSE_CF_AI_TOKEN")):
        result["status"] = "missing_cloudflare_credentials"
        return result
    try:
        configure_environment()
    except ValueError:
        result["status"] = "invalid_cloudflare_account_id"
        return result
    body = {
        "model": MODEL, "max_tokens": 64, "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Rispondi con un oggetto JSON valido."},
            {"role": "user", "content": 'Rispondi esattamente con JSON: {"ready":true}'},
        ],
    }
    req = urllib.request.Request(
        os.environ["PULSE_LLM_ENDPOINT"],
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + os.environ["PULSE_LLM_API_KEY"],
                 "Content-Type": "application/json"},
        method="POST",
    )
    request_fn = request_fn or urllib.request.urlopen
    try:
        with request_fn(req, timeout=65) as response:
            payload = json.loads(response.read(100000))
        msg = payload["choices"][0]["message"]["content"]
        actual = json.loads(msg)
        if actual.get("ready") is True:
            result["status"] = "connected_and_generated"
            result["authenticated_generation"] = True
        else:
            result["status"] = "unexpected_model_output"
    except urllib.error.HTTPError as exc:
        # Do not forward Cloudflare's error body; some vendors echo prompts.
        result["status"] = "cloudflare_http_" + str(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        result["status"] = "cloudflare_network_unavailable"
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        result["status"] = "invalid_llama_response"
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Real Llama API test without exposing credentials")
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    report = probe_llama()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PULSE Llama:", report["status"], flush=True)
    return 0 if report["authenticated_generation"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
