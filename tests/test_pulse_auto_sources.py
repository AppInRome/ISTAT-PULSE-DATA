"""Tests for automatic official Italian data discovery; fixtures are fictional."""
import csv
from io import StringIO
import unittest
from unittest.mock import Mock
from scripts.pulse_auto_sources import (
    attachments, canonical_map, detect_manifests, discover_primary_sources, valid_file_url
)

HEADER = "Indicatore;Territorio;Popolazione;Unita;Frequenza;Anno;Valore\n"
DATA = (HEADER +
        "Tasso sperimentale;Italia;Persone 15-64 anni;%;Mensile;2026-01;10,1\n"
        "Tasso sperimentale;Italia;Persone 15-64 anni;%;Mensile;2026-02;11,2\n"
        "Tasso sperimentale;Italia;Persone 15-64 anni;%;Mensile;2026-03;12,3\n"
        "Tasso sperimentale;Francia;Persone 15-64 anni;%;Mensile;2026-03;99,9\n")
SOURCE = "https://www.istat.it/comunicato-stampa/prova/"
FILE = "https://www.istat.it/wp-content/uploads/prova.csv"
ITALIAN_NEWS = {"id":"PULSE-TEST-1", "headline":"Tasso sperimentale in Italia",
                "geographic_scope":{"country_code":"IT"},
                "public_source":{"role":"primary_statistical_source", "url": SOURCE}}


class AutoSourcesTests(unittest.TestCase):
    def test_headers_require_seven_explicit_columns(self):
        self.assertIsNotNone(canonical_map(
            ["Indicatore", "Territorio", "Popolazione", "Unita", "Frequenza", "Anno", "Valore"]))
        self.assertIsNone(canonical_map(["Indicatore","Territorio","Anno","Valore"]))

    def test_official_domain_only(self):
        self.assertTrue(valid_file_url(FILE))
        self.assertFalse(valid_file_url("https://www.istat.it.evil.invalid/x.csv"))
        self.assertFalse(valid_file_url("http://www.istat.it/file.csv"))
        self.assertFalse(valid_file_url("https://www.oecd.org/data.csv"))

    def test_bounded_attachments_same_host(self):
        html = ('<a href="../data.csv">dati</a>'
                '<a href="https://www.istat.it.evil.invalid/dati.csv">malevolo</a>'
                '<a href="https://www.inps.it/file.csv">altro ente</a>').encode()
        out = attachments(html,SOURCE)
        self.assertEqual(out, ["https://www.istat.it/data.csv"])

    def test_realistic_csv_infers_manifest_and_original_hash(self):
        results = detect_manifests(SOURCE, FILE, DATA.encode())
        self.assertEqual(len(results),1)
        a=results[0]
        self.assertEqual(a["manifest"]["schema"]["dimensions"]["Territorio"],"Italia")
        self.assertEqual(len(a["evidence"]["series"]["observations"]),3)
        self.assertEqual(a["evidence"]["series"]["observations"][-1]["value"],"12.3")
        self.assertEqual(a["evidence"]["source_row_count"],4)
        self.assertNotIn("99.9",str(a["evidence"]))

    def test_incomplete_data_is_never_invented(self):
        content = ("Indicatore;Territorio;Anno;Valore\n"
                   "Tasso sperimentale;Italia;2024;10\n"
                   "Tasso sperimentale;Italia;2025;12\n")
        self.assertEqual(detect_manifests(SOURCE,FILE,content.encode()),[])

    def test_one_period_is_not_a_series(self):
        data=HEADER+"Tasso sperimentale;Italia;Persone 15-64 anni;%;Mensile;2026-01;10,1\n"
        self.assertEqual(detect_manifests(SOURCE, FILE, data.encode()),[])

    def test_auto_discovery_is_online_search_and_parse_not_hand_manifest(self):
        html=('<html><a href="/wp-content/uploads/prova.csv">Scarica il CSV</a></html>').encode()
        fetch=Mock(side_effect=lambda url: html if url==SOURCE else DATA.encode())
        result=discover_primary_sources([ITALIAN_NEWS],fetch=fetch)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["source_article_id"], "PULSE-TEST-1")
        self.assertEqual(fetch.call_count,2)

    def test_foreign_article_excluded(self):
        a=dict(ITALIAN_NEWS,geographic_scope={"country_code":"FR"})
        fetch=Mock()
        self.assertEqual(discover_primary_sources([a], fetch=fetch),[])
        fetch.assert_not_called()


if __name__=="__main__":
    unittest.main()
