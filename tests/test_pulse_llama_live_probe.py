"""Tests for an actual-token check: use a FAKE transport, never contact Cloudflare."""
from __future__ import annotations
from io import BytesIO
import json
import os
import unittest
from unittest.mock import patch
import urllib.error

from scripts.pulse_llama_live_probe import probe_llama

ACCOUNT = "0123456789abcdef0123456789abcdef"

class FakeResponse:
    def __init__(self, content):
        self.content = BytesIO(content)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, size=-1):
        return self.content.read(size)


class LlamaLiveProbeTests(unittest.TestCase):
    def test_missing_token_cannot_be_reported_as_connected(self):
        with patch.dict(os.environ, {"PULSE_CF_ACCOUNT_ID": ACCOUNT, "PULSE_CF_AI_TOKEN": ""}):
            report = probe_llama(request_fn=lambda *a, **k: self.fail("HTTP should not be called"))
        self.assertEqual(report["status"], "missing_cloudflare_credentials")
        self.assertFalse(report["authenticated_generation"])

    def test_live_api_shape_requires_model_json_response(self):
        called = []
        def fake_http(req, timeout):
            called.append((req.full_url, json.loads(req.data), req.get_header("Authorization")))
            return FakeResponse(json.dumps({"choices": [{"message": {"content": '{"ready": true}'}}]}).encode())
        with patch.dict(os.environ, {"PULSE_CF_ACCOUNT_ID": ACCOUNT, "PULSE_CF_AI_TOKEN": "fake-private-token"}):
            report = probe_llama(request_fn=fake_http)
        self.assertTrue(report["authenticated_generation"])
        self.assertEqual(report["status"], "connected_and_generated")
        self.assertTrue(called[0][0].startswith("https://api.cloudflare.com/client/v4/accounts/"))
        self.assertEqual(called[0][1]["model"], "@cf/meta/llama-3.3-70b-instruct-fp8-fast")
        self.assertEqual(called[0][1]["response_format"]["type"], "json_object")
        self.assertNotIn("fake-private-token", json.dumps(report))

    def test_api_failure_is_explicit_without_token_or_response_body(self):
        def failing(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 401, "token fake-private-token", {}, None)
        with patch.dict(os.environ, {"PULSE_CF_ACCOUNT_ID": ACCOUNT, "PULSE_CF_AI_TOKEN": "fake-private-token"}):
            report = probe_llama(request_fn=failing)
        self.assertEqual(report["status"], "cloudflare_http_401")
        self.assertFalse(report["authenticated_generation"])
        self.assertNotIn("fake-private-token", json.dumps(report))

    def test_wrong_json_is_not_authenticated_generation(self):
        with patch.dict(os.environ, {"PULSE_CF_ACCOUNT_ID": ACCOUNT, "PULSE_CF_AI_TOKEN": "fake"}):
            report = probe_llama(request_fn=lambda req, timeout:
                FakeResponse(b'{"choices":[{"message":{"content":"not JSON"}}]}'))
        self.assertEqual(report["status"], "invalid_llama_response")
        self.assertFalse(report["authenticated_generation"])

if __name__ == "__main__":
    unittest.main()
