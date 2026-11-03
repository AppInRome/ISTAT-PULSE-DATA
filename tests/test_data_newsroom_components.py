"""Offline cache, graph-spec, and AI provenance tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import pulse_http_cache as cache
from scripts.pulse_open_source_adapters import (
    vega_lite_from_verified_spec, opensdmx_exact_query
)
from scripts.pulse_ai_newsroom import validate_ai_copy

CHART = {
    "type": "line", "status": "verified", "title": "Tasso di occupazione",
    "unit": "%", "source_url": "https://www.istat.it/archivio/test",
    "data": [{"period": "2023", "value": 60.1},
             {"period": "2024", "value": 61.3},
             {"period": "2025", "value": 62.1}]
}

class DataNewsroomComponentsTests(unittest.TestCase):
    def test_istat_rate_path_detected(self):
        self.assertTrue(cache.is_istat_sdmx("https://esploradati.istat.it/SDMX/it/data/test"))
        self.assertFalse(cache.is_istat_sdmx("https://www.istat.it/comunicato-stampa/x"))
        self.assertFalse(cache.is_istat_sdmx("https://istat.it.attacker.example/sdmx"))

    def test_cache_prevents_repeat_request(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(cache, "CACHE", Path(temp)):
                calls = []
                def fake(url, timeout, max_bytes, headers):
                    calls.append(url)
                    return b"<html>test</html>", url, "text/html"
                url = "https://www.istat.it/comunicato-stampa/test/"
                first = cache.request_cached(url, transport=fake)
                second = cache.request_cached(url, transport=fake)
                self.assertEqual(first, second)
                self.assertEqual(len(calls), 1)

    def test_graph_uses_only_verified_rows(self):
        result = vega_lite_from_verified_spec(CHART)
        self.assertEqual(result["encoding"]["x"]["field"], "period")
        self.assertEqual(result["mark"]["type"], "line")
        self.assertEqual(result["data"]["values"][2]["value"], 62.1)
        self.assertEqual(result["usermeta"]["source_url"], CHART["source_url"])
        self.assertIsNone(vega_lite_from_verified_spec({**CHART, "status": "unverified"}))

    def test_bar_axis_baseline_zero(self):
        result = vega_lite_from_verified_spec({**CHART, "type": "bar"})
        self.assertTrue(result["encoding"]["y"]["scale"]["zero"])

    def test_sdmx_needs_specific_dimensions(self):
        with self.assertRaises(ValueError):
            opensdmx_exact_query("istat", "123", {})
        with self.assertRaises(ValueError):
            opensdmx_exact_query("istat", "123", {"REF_AREA": "*"})

    def test_ai_rejects_unverified_new_numbers(self):
        candidate = {"title": "L'occupazione italiana in crescita secondo il confronto",
                     "lead": "I dati mostrano un'evoluzione documentata nelle tre annualità considerate, con osservazioni della fonte ufficiale e un confronto limitato ai periodi disponibili.",
                     "paragraphs": [("Nella serie ufficiale si vedono tre osservazioni omogenee, "
                                     "senza assumere che il dato aggregato rappresenti "
                                     "tutta la popolazione allo stesso modo. ")*5 for _ in range(6)]}
        self.assertFalse(validate_ai_copy({"chart_spec": CHART}, candidate))
        candidate["paragraphs"][0] += " È cresciuto del 999,9 per cento."
        self.assertFalse(validate_ai_copy({"chart_spec": CHART}, candidate))


if __name__ == "__main__":
    unittest.main()
