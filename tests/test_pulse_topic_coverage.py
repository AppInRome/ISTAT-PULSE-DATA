"""Test independent metric counting without inflating gender/age variants."""
import unittest
from scripts import pulse_topic_coverage as coverage


class TopicCoverageTests(unittest.TestCase):
    def test_gender_variants_count_as_one_independent_family(self):
        records={"series":{
            "female":{"dataset_url":
                "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_pjan?geo=IT&sex=F&age=TOTAL",
                "indicator":"Popolazione femminile"},
            "male":{"dataset_url":
                "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_pjan?geo=IT&sex=M&age=TOTAL",
                "indicator":"Popolazione maschile"},
            "births":{"dataset_url":
                "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_frate?geo=IT&indic_de=TOTFERRT",
                "indicator":"Fecondità"}}}
        assessments={"generated_at":"2026-11-14T18:00:00Z","assessments":[
            {"series_key":key,"topic":"DEMOGRAFIA"} for key in records["series"]]}
        report=coverage.build(records,assessments,{"articles":[]})
        self.assertEqual(report["topics"]["DEMOGRAFIA"]["verified_series_or_subgroups"],3)
        self.assertEqual(report["topics"]["DEMOGRAFIA"]["independent_indicator_families_verified"],2)
        self.assertEqual(report["topics"]["DEMOGRAFIA"]["missing_to_target"],3)
        self.assertFalse(report["all_targets_met"])

    def test_historical_verified_eurostat_measure_remains_in_coverage(self):
        from scripts import pulse_eurostat_topics as euro
        historical=next(c for c in euro.CATALOG
                        if c["id"]=="prc_hicp_manr"
                        and c["indicator"]=="Inflazione armonizzata per alimentari")
        current=next(c for c in euro.CATALOG
                     if c["id"]=="nama_10_gdp"
                     and c["indicator"]=="Prodotto interno lordo a prezzi correnti")
        entries={"series":{
            "current":{"dataset_url":euro.request_url(current),
                       "indicator":current["indicator"],"territory":"Italia"},
            "historical":{"dataset_url":euro.request_url(historical),
                          "indicator":historical["indicator"],
                          "territory":"Italia","last_period":"2025-10",
                          "source_bytes_sha256":"a"*64,
                          "observation_signature":"b"*64},
        }}
        frontpage={"generated_at":"2026-11-14T20:00:00Z","assessments":[
            {"series_key":"current","topic":"ECONOMIA"}]}
        first=coverage.build(entries,frontpage,{"articles":[]})
        self.assertEqual(first["topics"]["ECONOMIA"]["independent_indicator_families_verified"],2)
        self.assertEqual(first["previously_verified_series_classified_from_audited_history"],1)
        # The same source is still covered even if it was not in today's
        # 30-item bounded discovery. It does not become today's fresh news.
        self.assertEqual(first["topics"]["ECONOMIA"]["published_articles_in_archive"],0)

    def test_catalogue_candidate_without_historical_audit_is_not_verified(self):
        from scripts import pulse_eurostat_topics as euro
        candidate=next(c for c in euro.CATALOG if c["id"]=="demo_find")
        entry={"dataset_url":euro.request_url(candidate),
               "indicator":candidate["indicator"],"territory":"Italia",
               "last_period":"2024"}
        report=coverage.build({"series":{"unverified":entry}},
                              {"assessments":[]},{"articles":[]})
        self.assertEqual(report["topics"]["DEMOGRAFIA"]["independent_indicator_families_verified"],0)

    def test_recover_legacy_independent_labor_from_published_article(self):
        url="https://opendata.inps.it/example.csv"
        entry={"dataset_url":url,"indicator":"Numero lavoratori",
               "territory":"Lazio","last_period":"2025",
               "source_bytes_sha256":"0"*64,
               "observation_signature":"1"*64}
        feed={"articles":[{"topic":"LAVORO","publication_status":"published",
               "source_documents":[{"url":url}],
               "verified_series_relevant":[{"indicator":"Numero lavoratori",
                                            "territory":"Lazio"}]}]}
        report=coverage.build({"series":{"archived":entry}},
                              {"assessments":[]},feed)
        self.assertEqual(report["topics"]["LAVORO"]["independent_indicator_families_verified"],1)
        self.assertEqual(report["topics"]["LAVORO"]["published_articles_in_archive"],1)

    def test_distinguish_multiple_measures_from_same_dataset(self):
        a="https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_wasmun"
        self.assertNotEqual(
            coverage.independent_metric_identity(a+"?unit=THS_T&geo=IT"),
            coverage.independent_metric_identity(a+"?unit=KG_HAB&geo=IT"))


if __name__=="__main__":
    unittest.main()
