"""PULSE deterministic regional editing tests, entirely offline synthetic fixtures."""
from copy import deepcopy
import unittest
from scripts import pulse_regional_editing as grouping


def pair(region, before, after, tag="Ordinaria", kind="Numero_lavoratori"):
    source="https://opendata.inps.it/download/dataset/files/inps_test.csv"
    sha="f"*64
    indicator="Integrazioni Salariali Lavoratori 2025 — "+kind
    series={
        "indicator":indicator, "unit":"numero", "territory":region,
        "population":"Lavoratori, serie INPS verificata",
        "frequency":"Mensile (anno e mese nelle righe)",
        "classification_values":{"Regione":region, "Tipo_intervento":tag},
        "observations":[{"period":"2025-11","value":before},
                        {"period":"2025-12","value":after}]
    }
    evidence={"verified":True,"dataset_url":source,"source_url":
              "https://opendata.inps.it/opendata/api/3/action/package_show?id=test",
              "source_sha256":sha,"publisher":"INPS","series":series}
    item={"id":"PULSE-DATA-"+region.upper(), "period_reference":"2025-12",
          "published_at":"2026-11-14T13:00:00Z",
          "editorial_format":"deterministic_source_locked_auto_audited",
          "publication_status":"published",
          "automatic_review":{"passed":True,"model_used":False},
          "public_source":{"role":"primary_statistical_source"},
          "source_documents":[{"url":source,"sha256":sha}],
          "verified_series_relevant":[{
              "indicator":indicator,"unit":"numero","territory":region,
              "population":series["population"],
              "observations":series["observations"]}],
          "headline":"Old title; not to be changed",
          "summary":"Original scientific text; not to be changed",
          "chart_spec":{"status":"verified","data":[0,1]},
          "table_spec":{"status":"verified","rows":[[0],[1]]}}
    return item,evidence


class RegionalEditorialTests(unittest.TestCase):
    def setUp(self):
        self.pairs=[
            pair("Sardegna",100,155),
            pair("Campania",200,150),
            pair("Lazio",800,807),
            pair("Piemonte",120,118),
            pair("Abruzzo",500,520),
        ]

    def test_one_regional_overview_and_max_two_marked_standalones(self):
        originals=deepcopy(self.pairs)
        result=grouping.build_digest(self.pairs,published_at="2026-11-14T18:00:00Z")
        self.assertEqual(result["schema"],grouping.SCHEMA)
        self.assertEqual(len(result["groups"]),1)
        g=result["groups"][0]
        self.assertEqual(g["coverage"],5)
        self.assertFalse(g["country_total_available"])
        self.assertEqual(len(g["related_article_ids"]),5)
        self.assertEqual(len(g["spotlight_article_ids"]),2)
        self.assertEqual(g["period_display"],"dicembre 2025")
        self.assertIn("non", g["caution"].lower())
        self.assertNotIn("Italia: 1",g["title"])
        self.assertEqual(self.pairs,originals) # NO source, article or graph mutations
        second=grouping.build_digest(self.pairs,result,"2026-11-15T18:00:00Z")
        self.assertEqual(result,second)

    def test_incompatible_classification_cannot_be_collapsed(self):
        changed=deepcopy(self.pairs)
        changed[0][1]["series"]["classification_values"]["Tipo_intervento"]="Straordinaria"
        self.assertEqual(len(grouping.build_digest(changed)["groups"]),1)
        self.assertEqual(grouping.build_digest(changed)["groups"][0]["coverage"],4)
        for i in range(3):
            changed[i][1]["series"]["classification_values"]["Tipo_intervento"]="Special"+str(i)
        self.assertEqual(len(grouping.build_digest(changed)["groups"]),0)

    def test_not_same_period_or_source(self):
        changed=deepcopy(self.pairs)
        changed[0][0]["source_documents"][0]["sha256"]="0"*64
        changed[1][1]["series"]["observations"][-2]["period"]="2025-09"
        changed[2][1]["series"]["observations"][-1]["period"]="2026-01"
        self.assertEqual(len(grouping.build_digest(changed)["groups"]),0)

    def test_preserve_prior_groups_if_source_unavailable(self):
        old=grouping.build_digest(self.pairs,published_at="2026-11-14T18:00:00Z")
        self.assertEqual(grouping.build_digest([],old),old)

    def test_zero_base_is_not_divided_and_small_change_does_not_spawn_story(self):
        rows=[pair("Abruzzo",0,100), pair("Piemonte",2,3), pair("Sardegna",800,810)]
        g=grouping.build_digest(rows)["groups"][0]
        self.assertIsNone(g["regions"][0]["relative_percent"])
        self.assertEqual(g["spotlight_article_ids"],[])


if __name__=="__main__":
    unittest.main()
