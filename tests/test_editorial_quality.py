"""Editorial standard: reject repeated, generic or evidence-free copy."""
import unittest

from scripts.pulse_editorial_quality import assess_story
from tests.test_editorial_publish import EDIT, DRAFT

class QualityTests(unittest.TestCase):
    def test_varied_provenance_grounded_story(self):
        audit=assess_story(EDIT["headline"], EDIT["lead"], EDIT["paragraphs"], DRAFT["chart_spec"]["data"])
        self.assertTrue(audit["passed"],audit["issues"])

    def test_formulaic_repetition_is_rejected(self):
        text=("Il dato più recente disponibile mostra un cambiamento interessante. "
              "Per stabilire se il cambiamento sia rilevante bisogna esaminare ancora altri fattori. "
              "La descrizione rimane uguale perché questo testo non racconta un caso specifico. ")*5
        audit=assess_story("I numeri sono interessanti", "Un articolo lungo ma generico deve essere respinto dal controllo di qualità editoriale.", [text]*7, [{"period":"2025","value":13.0}])
        self.assertFalse(audit["passed"])
        self.assertTrue(any("boilerplate" in v for v in audit["issues"]))
        self.assertIn("near_duplicate_paragraphs",audit["issues"])

    def test_chart_figures_must_be_acknowledged_in_prose(self):
        audit=assess_story(EDIT["headline"], "La fonte racconta un cambiamento generale ma non ne riprende nessuna misura originale.", [p.replace("12","dodici").replace("13","tredici") for p in EDIT["paragraphs"]], DRAFT["chart_spec"]["data"])
        self.assertIn("text_omits_chart_values",audit["issues"])

if __name__ == "__main__":
    unittest.main()
