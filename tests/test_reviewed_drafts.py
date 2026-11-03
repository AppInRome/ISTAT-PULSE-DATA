"""Review gate tests: no accidental publication, hallucinated or untraceable numbers."""
import unittest
from scripts.pulse_reviewed_drafts import reviewed_draft

URL="https://www.istat.it/pubblicazioni/occupazione"
ARTICLE={"id":"PULSE-MEDIA-DEMO","headline":"Occupazione in aumento secondo i dati ISTAT",
         "published_at":"2026-11-02T08:00:00+00:00",
         "public_source":{"url":"https://giornale.example/occupazione","domain":"giornale.example","role":"journalistic_source"},
         "topic":"LAVORO","publication_status":"published"}
EVIDENCE={"verified":True,"indicator":"Occupazione", "unit":"%",
          "source_url":URL,"source_sha256":"a"*64,"location":"table:1:row:3",
          "extraction_method":"same_row_explicit_year_structured_table",
          "observations":[{"period":"2024","value":62.1},{"period":"2025","value":62.7}]}
DOSSIER={"article_id":"PULSE-MEDIA-DEMO","status":"manual_primary_review_required",
         "source_checks":[{"candidate_evidence":[EVIDENCE]}]}
DECISION={"decision":"approved","article_id":"PULSE-MEDIA-DEMO","reviewer":"Revisore editoriale",
          "reviewed_at":"2026-11-03T11:00:00+00:00","primary_publication_date":"2026-11-02",
          "territory":"Italia","dataset":"Occupazione","methodology":"Tabella ufficiale omogenea per anni",
          "source_url":URL,"source_sha256":"a"*64,"location":"table:1:row:3",
          "indicator":"Occupazione","unit":"%"}

class ReviewedDraftTests(unittest.TestCase):
    def test_approved_evidence_produces_draft_only(self):
        out=reviewed_draft(ARTICLE,DOSSIER,DECISION,["istat.it"])
        self.assertEqual(out["publication_status"],"draft")
        self.assertFalse(out["editorial_review"]["ready_for_publication"])
        self.assertEqual(out["editorial_review"]["source_sha256"],"a"*64)
        self.assertEqual(out["chart_spec"]["status"],"verified")
        self.assertEqual(len(out["table_spec"]["rows"]),2)
        self.assertGreaterEqual(len(out["pulse_article_body"]),4)
        self.assertEqual(out["published_at"],ARTICLE["published_at"])

    def test_missing_or_wrong_approval_is_rejected(self):
        for changes in ({"decision":"pending"},{"source_sha256":"b"*64},
                        {"source_url":"https://fake.istat.it.evil.test/report"},
                        {"location":"invented"},{"methodology":"too short"},
                        {"article_id":"WRONG"}):
            decision=dict(DECISION,**changes)
            with self.assertRaises(ValueError):
                reviewed_draft(ARTICLE,DOSSIER,decision,["istat.it"])

    def test_non_reviewable_dossier_is_rejected(self):
        with self.assertRaises(ValueError):
            reviewed_draft(ARTICLE,{**DOSSIER,"status":"primary_evidence_not_found"},DECISION,["istat.it"])

if __name__=="__main__":
    unittest.main()
