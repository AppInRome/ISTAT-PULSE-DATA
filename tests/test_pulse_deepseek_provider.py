"""DeepSeek provider wiring tests: fake credentials and fake HTTP, no paid API call."""
import json
import os
import unittest
from unittest.mock import patch

from scripts import pulse_ai_provider as provider
from scripts import pulse_ai_live_probe as live
from scripts import pulse_editorial_engine_v1 as engine

class FakeHTTP:
    def __init__(self, body):
        self.body = json.dumps(body).encode()
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n=-1): return self.body

ENV = {
    "PULSE_AI_PROVIDER":"deepseek",
    "PULSE_DEEPSEEK_API_KEY":"test-not-a-real-token",
    "PULSE_CF_ACCOUNT_ID":"",
    "PULSE_CF_AI_TOKEN":"",
}

class DeepSeekProviderTests(unittest.TestCase):
    def test_missing_key_is_reported(self):
        with patch.dict(os.environ, {**ENV, "PULSE_DEEPSEEK_API_KEY":""}):
            self.assertFalse(provider.configure_environment())
            report = live.probe_ai(request_fn=lambda *a, **k: self.fail("must not call"))
            self.assertEqual(report["status"], "missing_deepseek_credentials")
            self.assertFalse(report["authenticated_generation"])

    def test_official_deepseek_endpoint_and_model(self):
        with patch.dict(os.environ, ENV):
            self.assertTrue(provider.configure_environment())
            self.assertEqual(os.environ["PULSE_LLM_ENDPOINT"],
                             "https://api.deepseek.com/chat/completions")
            self.assertEqual(os.environ["PULSE_LLM_MODEL"],"deepseek-flash")
            self.assertEqual(os.environ["PULSE_LLM_MAX_OUTPUT_TOKENS"], "2200")
            self.assertEqual(provider.budget_unit(), "usd_peak_estimate")
            self.assertLess(provider.reserved_budget("sample"), 0.15)

    def test_authenticated_response_required(self):
        calls=[]
        def mock_http(req, timeout):
            calls.append((req.full_url,json.loads(req.data),req.get_header("Authorization")))
            return FakeHTTP({"choices":[{"message":{"content":'{"ready":true}'}}]})
        with patch.dict(os.environ, ENV):
            report=live.probe_ai(mock_http)
        self.assertTrue(report["authenticated_generation"])
        self.assertEqual(report["status"],"connected_and_generated")
        self.assertEqual(calls[0][1]["model"],"deepseek-flash")
        self.assertEqual(calls[0][1]["thinking"],{"type":"disabled"})
        self.assertNotIn("test-not-a-real-token",json.dumps(report))

    def test_editorial_call_uses_deepseek_json_and_non_thinking(self):
        seen={}
        def mock_http(req, timeout):
            seen["url"]=req.full_url
            seen["payload"]=json.loads(req.data)
            return FakeHTTP({"choices":[{"message":{"content":'{"title":"test","lead":"test","paragraphs":[]}'}}]})
        with patch.dict(os.environ, ENV):
            provider.configure_environment()
            with patch.object(engine,"ai_prompt",return_value="Rispondi in JSON"),patch.object(engine.urllib.request,"urlopen",side_effect=mock_http):
                result=engine.call_model({})
        self.assertEqual(result["title"],"test")
        self.assertEqual(seen["payload"]["thinking"],{"type":"disabled"})
        self.assertEqual(seen["payload"]["max_tokens"],2200)
        self.assertEqual(seen["payload"]["response_format"],{"type":"json_object"})

if __name__=="__main__":
    unittest.main()
