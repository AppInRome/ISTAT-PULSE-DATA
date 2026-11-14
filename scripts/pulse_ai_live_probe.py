#!/usr/bin/env python3
"""Verify an actual AI inference on the configured PULSE provider, without logging secrets."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.pulse_ai_provider import active_provider, configure_environment


def probe_ai(request_fn=None):
    provider = active_provider()
    report = {"provider": provider, "model": "not_configured",
              "tested_at": datetime.now(timezone.utc).isoformat(),
              "status": "not_connected", "authenticated_generation": False}
    if not configure_environment():
        report["status"] = "missing_" + provider + "_credentials"
        return report
    report["model"] = os.environ["PULSE_LLM_MODEL"]
    req_body = {
        "model": report["model"], "max_tokens": 80, "temperature": 0,
        "response_format": {"type":"json_object"},
        "messages": [
            {"role":"system","content":"Rispondi esclusivamente con JSON valido."},
            {"role":"user","content":'Rispondi con JSON {"ready":true}'},
        ],
    }
    if provider == "deepseek":
        req_body["thinking"] = {"type":"disabled"}
    req = Request(
        os.environ["PULSE_LLM_ENDPOINT"],
        data=json.dumps(req_body).encode("utf-8"),
        headers={"Authorization":"Bearer " + os.environ["PULSE_LLM_API_KEY"],
                 "Content-Type":"application/json"},
        method="POST",
    )
    try:
        with (request_fn or urlopen)(req, timeout=70) as result:
            response = json.loads(result.read(100_000))
        answer = json.loads(response["choices"][0]["message"]["content"])
        if answer.get("ready") is True:
            report["status"] = "connected_and_generated"
            report["authenticated_generation"] = True
        else:
            report["status"] = "unexpected_model_output"
    except HTTPError as exc:
        # Never print the error body; providers can echo user data in it.
        report["status"] = "provider_http_" + str(exc.code)
    except (URLError, TimeoutError, OSError):
        report["status"] = "provider_network_unavailable"
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        report["status"] = "invalid_ai_response"
    return report


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    args=p.parse_args(argv)
    report=probe_ai()
    out=Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    print("PULSE AI:", report["provider"], report["status"])
    return 0 if report["authenticated_generation"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
