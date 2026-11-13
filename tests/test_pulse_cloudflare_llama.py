"""Cloudflare Llama configuration tests — never send real API requests."""
import os
import unittest
from unittest.mock import patch
from scripts.pulse_cloudflare_llama import (
    configure_environment, configured, remaining_for_run, reserved_neurons,
    BUDGET_NEURONS, MODEL
)


class CloudflareLlamaTests(unittest.TestCase):
    def test_no_auth_means_no_connection(self):
        with patch.dict(os.environ, {"PULSE_CF_ACCOUNT_ID": "", "PULSE_CF_AI_TOKEN": ""}):
            self.assertFalse(configured())
            self.assertFalse(configure_environment())

    def test_old_worker_is_never_endpoint(self):
        aid = "0123456789abcdef0123456789abcdef"
        with patch.dict(os.environ, {"PULSE_CF_ACCOUNT_ID": aid,
                                      "PULSE_CF_AI_TOKEN": "dummy-token",
                                      "PULSE_LLM_ENDPOINT": "https://pulse-tommy-api.test"}):
            self.assertTrue(configure_environment())
            ep = os.environ["PULSE_LLM_ENDPOINT"]
            self.assertEqual(ep,
                "https://api.cloudflare.com/client/v4/accounts/" + aid +
                "/ai/v1/chat/completions")
            self.assertEqual(os.environ["PULSE_LLM_MODEL"], MODEL)
            self.assertNotIn("tommy", ep)
            self.assertEqual(os.environ["PULSE_LLM_MAX_OUTPUT_TOKENS"], "1400")

    def test_invalid_account_rejected(self):
        with patch.dict(os.environ, {"PULSE_CF_ACCOUNT_ID": "incorrect",
                                      "PULSE_CF_AI_TOKEN": "dummy-token"}):
            with self.assertRaisesRegex(ValueError, "invalid_Cloudflare_account_id"):
                configure_environment()

    def test_budget_reserves_worst_case_output(self):
        small = reserved_neurons("A")
        long = reserved_neurons("B" * 20000)
        self.assertGreater(long, small)
        self.assertGreater(small, 250)
        self.assertLess(small, 320)
        self.assertEqual(remaining_for_run(BUDGET_NEURONS + 1), 0)

    def test_reject_empty_accounts_despite_legacy_secrets(self):
        with patch.dict(os.environ, {"PULSE_CF_ACCOUNT_ID": "", "PULSE_CF_AI_TOKEN": "",
                                      "PULSE_LLM_API_KEY": "unused-old-token"}):
            self.assertFalse(configure_environment())


if __name__ == "__main__":
    unittest.main()
