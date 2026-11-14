"""Independent, fake-data tests of PULSE Eurostat diversification.

No test fixture is a claim about Italy and no test invokes a paid service.
"""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from scripts import pulse_eurostat_topics as euro
from scripts import pulse_italia_official_discovery as official
from scripts import pulse_italia_newsroom as newsroom
from scripts import pulse_deterministic_writer as writer
from scripts import pulse_italia_auto_pipeline as pipeline


def payload(country="IT", unit="CP_MEUR", values=None, status=None, geography_first=False):
    # Multidimensional JSON-stat 2.0 (time NOT necessarily the final index).
    if values is None:
        values = {"0":1000.0, "1":1050.0, "2":1100.0}
    axes=(["geo","time","unit"] if geography_first else ["time","unit","geo"]) + ["freq","na_item"]
    dims={
        "time":{"category":{"index":{"2023":0,"2024":1,"2025":2},
                            "label":{"2023":"2023","2024":"2024","2025":"2025"}}},
        "geo":{"category":{"index":{country:0},"label":{country:"Country"}}},
        "unit":{"category":{"index":{unit:0},"label":{unit:"Unit"}}},
        "freq":{"category":{"index":{"A":0}}},
        "na_item":{"category":{"index":{"B1G":0}}}
    }
    return json.dumps({
        "class":"dataset","id":axes,"size":[3 if k=="time" else 1 for k in axes],
        "dimension":dims,"value":values,**({"status":status} if status is not None else {})
    }).encode()


class EurostatVerifiedSeriesTests(unittest.TestCase):
    def setUp(self):
        self.c=euro.CATALOG[0]
        self.u=euro.request_url(self.c)

    def test_seven_theme_sources_have_unambiguous_registry(self):
        self.assertTrue({"ECONOMIA","DEMOGRAFIA","SALUTE","ISTRUZIONE","CASA","AMBIENTE","ENERGIA"}.issubset(
            {c["topic"] for c in euro.CATALOG}))
        for c in euro.CATALOG:
            self.assertIn("geo=IT", euro.request_url(c))
            self.assertTrue(euro.request_url(c).startswith(euro.API))

    def test_exact_resolved_cell_and_source_bytes(self):
        blob=payload()
        ev=euro.verified_jsonstat_evidence(blob,self.c,self.u)
        self.assertTrue(ev["verified"])
        self.assertEqual(ev["topic"],"ECONOMIA")
        self.assertEqual(ev["series"]["territory"],"Italia")
        self.assertEqual([v["value"] for v in ev["series"]["observations"]],
                         [1000.0,1050.0,1100.0])
        self.assertEqual([x["jsonstat_cell_index"] for x in ev["source_locations"]],[0,1,2])
        self.assertEqual(len(ev["source_sha256"]),64)
        self.assertIn("CP_MEUR", str(ev["series"]["classification_values"]))
        self.assertTrue(newsroom.italian_official_url(ev["source_url"]))
        self.assertTrue(newsroom.italian_official_url(ev["dataset_url"]))
        draft,audit=writer.write_verified_article(ev)
        self.assertIsNotNone(draft,audit)
        self.assertTrue(audit["passed"])

    def test_reject_non_italian_data_or_mislabeled_units(self):
        for blob in (payload(country="DE"), payload(unit="PC")):
            with self.subTest(blob=blob[:20]), self.assertRaises(ValueError):
                euro.verified_jsonstat_evidence(blob,self.c,self.u)
        self.assertFalse(newsroom.italian_official_url(
            "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nama_10_gdp?geo=DE"))
        self.assertFalse(newsroom.italian_official_url("https://ec.europa.eu/other-service"))

    def test_breaks_and_suppressed_cells_are_not_reported(self):
        blob=payload(status={"0":"b","1":"u","2":"c"})
        with self.assertRaisesRegex(ValueError,"not_enough"):
            euro.verified_jsonstat_evidence(blob,self.c,self.u)

    def test_multiple_dimensions_cannot_be_mixed_into_series(self):
        blob=json.loads(payload())
        blob["size"][1]=2
        blob["dimension"]["unit"]["category"]["index"]["PC"]=1
        blob["value"]=[1000,80,1100,85,1200,90]
        # Query demands CP_MEUR: must retain only exact known cell,
        # not the second percentage unit.
        ev=euro.verified_jsonstat_evidence(json.dumps(blob).encode(),self.c,self.u)
        self.assertEqual([x["value"] for x in ev["series"]["observations"]],[1000,1100,1200])
        blob["dimension"]["unit"]["category"]["index"]={"unknown":0,"PC":1}
        with self.assertRaises(ValueError):
            euro.verified_jsonstat_evidence(json.dumps(blob).encode(),self.c,self.u)

    def test_unsupported_or_unfiltered_dimension_rejected(self):
        obj=json.loads(payload())
        obj["id"].append("cause")
        obj["size"].append(2)
        obj["dimension"]["cause"]={"category":{"index":{"A":0,"B":1}}}
        obj["value"]=[1]*12
        with self.assertRaisesRegex(ValueError,"unfiltered_multi_category"):
            euro.verified_jsonstat_evidence(json.dumps(obj).encode(),self.c,self.u)

    def test_injected_api_fake_sources_are_reported_without_lying(self):
        blob=payload()
        def get(url):
            if "nama_10_gdp" in url:
                return blob
            raise OSError("simulated backend unavailable")
        got,checks=euro.discover(fetch_fn=get)
        self.assertEqual(len(got),1)
        self.assertEqual(len(checks),len(euro.CATALOG))
        self.assertEqual(sum(c["status"]=="source_series_found" for c in checks),1)
        self.assertTrue(all(c["status"]!="source_series_found" for c in checks[1:]))

    def test_missing_filter_dimensions_fail_closed(self):
        blob=json.loads(payload())
        blob["id"].remove("na_item")
        blob["size"].pop()
        blob["dimension"].pop("na_item")
        with self.assertRaisesRegex(ValueError, "requested_dimension_missing"):
            euro.verified_jsonstat_evidence(json.dumps(blob).encode(), self.c, self.u)

    def test_new_candidacies_are_official_dataset_queries_not_fake_counts(self):
        ids={c["id"] for c in euro.CATALOG}
        self.assertTrue({"demo_find", "demo_gind", "sdg_04_60",
                         "ilc_lvho07a", "hlth_silc_08",
                         "sdg_12_51", "sdg_07_50"}.issubset(ids))
        # The official URL of each candidate is only an intention to query.
        # Verification requires actual source cells and a separate audit.
        for candidate in euro.CATALOG:
            self.assertIn("geo=IT", euro.request_url(candidate))
            self.assertIsInstance(candidate["filters"], dict)
            self.assertTrue(candidate["indicator"])

    def test_discovery_budget_prefers_independent_metrics_over_gender_slices(self):
        checked=[]
        def fake_get(url):
            checked.append(url)
            raise OSError("offline candidate - never fake source statistics")
        found,reports=euro.discover(fetch_fn=fake_get, limit=16)
        self.assertFalse(found)
        self.assertEqual(len(reports),16)
        self.assertTrue(any("demo_find?" in url for url in checked))
        self.assertFalse(any("demo_pjan?" in url and "sex=M" in url
                             for url in checked))

    def test_status_unchanged_on_script_injection(self):
        with self.assertRaises(ValueError):
            euro.verified_jsonstat_evidence(payload(),self.c,
                    "https://evil.example/eurostat/api/dissemination/statistics/1.0/data")
        self.assertNotIn("Mistral", str(euro.CATALOG))


if __name__=="__main__":
    unittest.main()
