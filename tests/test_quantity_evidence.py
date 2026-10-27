"""Offline tests: statistical values may enter charts only with explicit units."""
import unittest

from scripts.pulse_evidence import quantity_evidence, italian_quantity, extract_bytes

class QuantityEvidenceTests(unittest.TestCase):
    def test_same_indicator_two_years_with_explicit_unit(self):
        rows=[["Indicatore (tonnellate)","2024","2025"],
              ["Rifiuti urbani in tonnellate","1.234","1.350"]]
        items=quantity_evidence(rows,"https://www.isprambiente.gov.it/dati/rifiuti.csv",
                                "abc123","sheet:1")
        self.assertEqual(1,len(items))
        self.assertEqual("tonnellate",items[0]["unit"])
        self.assertEqual(1234,items[0]["observations"][0]["value"])
        self.assertEqual(1350,items[0]["observations"][1]["value"])
        self.assertEqual(116,items[0]["delta"])

    def test_missing_unit_cannot_generate_chart(self):
        rows=[["Indicatore","2024","2025"],["Produzione elettrica","12","13"]]
        self.assertEqual([],quantity_evidence(rows,"https://terna.it/table.csv","x","sheet:1"))

    def test_ambiguous_decimal_point_is_not_guessed(self):
        self.assertIsNone(italian_quantity("1.25"))
        self.assertIsNone(italian_quantity("9 abc"))
        self.assertEqual(1234.5,italian_quantity("1.234,50"))

    def test_source_provenance_in_csv(self):
        data=("Indicatore (tonnellate);2024;2025\n"
              "Rifiuti urbani in tonnellate;1.234;1.350\n").encode()
        result=extract_bytes(data,"https://www.isprambiente.gov.it/data.csv","text/csv")
        self.assertEqual("verified",result["status"])
        self.assertEqual(1,len(result["evidence"]))
        self.assertEqual("same_row_explicit_year_quantity_table",result["evidence"][0]["extraction_method"])
        self.assertEqual(result["source_sha256"],result["evidence"][0]["source_sha256"])

if __name__=="__main__":
    unittest.main()
