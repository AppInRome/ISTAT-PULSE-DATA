import unittest
from scripts.pulse_feature_writer import longform_sections

class FeatureWriterTests(unittest.TestCase):
    def setUp(self):
        self.series = {
            "indicator": "Tasso di occupazione", "unit": "%",
            "source_url": "https://www.istat.it/it/archivio/test",
            "observations": [{"period": "2022", "value": 60.1},
                             {"period": "2023", "value": 61.5},
                             {"period": "2024", "value": 62.0}],
        }

    def test_verified_series_yields_prose_with_exact_numbers(self):
        result = longform_sections(self.series, "istat.it")
        self.assertGreaterEqual(len(result), 6)
        self.assertTrue(all(not item["heading"] for item in result))
        prose = " ".join(item["text"] for item in result)
        for term in ("60,1", "61,5", "62", "2022", "2023", "2024",
                     "punti percentuali", "https://www.istat.it/it/archivio/test"):
            self.assertIn(term, prose)

    def test_no_graph_without_comparable_data(self):
        for series in (None, {}, {"observations": []},
                       {**self.series, "observations": self.series["observations"][:1]},
                       {**self.series, "source_url": "http://example.com"}):
            self.assertEqual(longform_sections(series, "istat.it"), [])

    def test_no_nan_or_duplicate_dates(self):
        samples = [
            {**self.series, "observations": [
                {"period": "2022", "value": float("nan")},
                {"period": "2023", "value": 10.0}]},
            {**self.series, "observations": [
                {"period": "2023", "value": 12.0},
                {"period": "2023", "value": 13.0}]}
        ]
        for sample in samples:
            self.assertEqual(longform_sections(sample, "istat.it"), [])

if __name__ == "__main__":
    unittest.main()
