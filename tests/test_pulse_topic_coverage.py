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

    def test_distinguish_multiple_measures_from_same_dataset(self):
        a="https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_wasmun"
        self.assertNotEqual(
            coverage.independent_metric_identity(a+"?unit=THS_T&geo=IT"),
            coverage.independent_metric_identity(a+"?unit=KG_HAB&geo=IT"))


if __name__=="__main__":
    unittest.main()
