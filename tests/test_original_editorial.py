"""Regressioni offline per la redazione originale PULSE: senza rete, senza APK."""
import unittest
from scripts.pulse_original_editorial import compose_verified, series_for_story
from scripts.update_news_radar import classify_topic, verify_primary_page

def example():
    return {
        "id": "PULSE-TEST", "headline": "Rapporto: povertà assoluta nel 2025 - Giornale",
        "topic": "ECONOMIA",
        "published_at": "2026-10-27T08:00:00+00:00",
        "public_source": {
            "role": "primary_statistical_source",
            "url": "https://www.istat.it/rapporto/povertà-2025"
        },
        "discovery": {
            "role": "journalistic_radar",
            "original_url": "https://www.esempio.it/news/povertà",
            "outlet": "Testata nazionale"
        },
        "statistical_claims": [{"raw_value": "8,2%", "verified": True}]
    }

class OriginalEditorialTests(unittest.TestCase):
    def test_original_text_and_chart_table_from_two_source_periods(self):
        candidate = example()
        evidence = {
            "verified_series": [{
                "verified": True, "indicator": "povertà assoluta", "unit": "%",
                "source_url": "https://www.istat.it/rapporto/povertà-2025",
                "extraction_method": "same_row_explicit_year_structured_table",
                "observations": [{"period": "2024", "value": 8.1},
                                 {"period": "2025", "value": 8.2}]
            }]
        }
        value = compose_verified(candidate, evidence)
        self.assertNotEqual(candidate["headline"], value["headline"])
        self.assertEqual("Redazione PULSE", value["byline"])
        self.assertEqual("verified", value["chart_spec"]["status"])
        self.assertEqual(2, len(value["table_spec"]["rows"]))
        self.assertEqual(2, len(value["sources"]))
        self.assertTrue(all(len(p["text"]) > 30 for p in value["pulse_article_body"]))

    def test_one_verified_value_gets_single_bar_not_a_fake_trend(self):
        candidate=example()
        candidate["headline"]="Povertà assoluta: nuovi valori nel 2025"
        ev={"verified_series":[{
            "verified":True,"indicator":"povertà assoluta","unit":"%",
            "source_url":"https://www.istat.it/rapporto/povertà-2025",
            "observations":[{"period":"2025","value":8.2}]
        }]}
        output=compose_verified(candidate,ev)
        self.assertEqual("published",output.get("publication_status","published"))
        self.assertEqual(True,output["chart_spec"]["single_observation"])
        self.assertEqual("bar",output["chart_spec"]["type"])
        self.assertEqual(1,len(output["table_spec"]["rows"]))
        self.assertIn("solo periodo",output["pulse_article_body"][1]["text"])

    def test_unrelated_figure_is_kept_out_of_oggi(self):
        result=compose_verified(example(),{"verified_series":[]})
        self.assertEqual("quarantined",result["publication_status"])
        self.assertEqual([],result["table_spec"]["rows"])

    def test_no_chart_for_unrelated_or_unverified_series(self):
        evidence = {"verified_series": [{
            "verified": True, "indicator": "tasso di occupazione", "unit": "%",
            "source_url": "https://www.istat.it/rapporto/povertà-2025",
            "observations": [{"period": "2024", "value": 30},
                             {"period": "2025", "value": 31}]
        }]}
        out = compose_verified(example(), evidence)
        self.assertEqual("none", out["chart_spec"]["type"])
        self.assertEqual([], out["table_spec"]["rows"])
        self.assertFalse(out["verified_series_relevant"])

    def test_reject_unrelated_website_data(self):
        e = [{"verified": True, "indicator": "povertà assoluta", "unit": "%",
              "source_url": "https://untrusted.example.com/stats",
              "observations": [{"period": "2024", "value": 1},
                               {"period": "2025", "value": 9}]}]
        self.assertEqual([], series_for_story(e, example()["headline"],
                                               example()["public_source"]["url"]))

    def test_no_istat_homepage_as_primary_report(self):
        self.assertIsNone(verify_primary_page("https://www.istat.it/",
                                              ["3,8%"], ["nascite"], ["istat.it"]))

    def test_classification_avoids_news_outlet_name(self):
        self.assertEqual("DEMOGRAFIA",
                         classify_topic("Nascite in calo e fecondità - Orizzonte Scuola"))
        self.assertEqual("ECONOMIA",
                         classify_topic("Emissioni di titoli di Stato e debito pubblico in aumento"))
        self.assertEqual("AMBIENTE",
                         classify_topic("Emissioni di CO2 e riscaldamento globale"))

if __name__ == "__main__":
    unittest.main()
