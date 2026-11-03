"""Offline regression tests for the PULSE primary research queue."""
import unittest
from scripts.pulse_primary_research import (
    allowed_url, article_leads, relevant_evidence, examine, research_article, build_queue
)

DOMAINS=["istat.it","inps.it"]
ARTICLE={
    "id":"PULSE-MEDIA-TEST","headline":"Occupazione cresce secondo ISTAT",
    "published_at":"2026-11-02T09:30:00+00:00","publication_status":"published",
    "public_source":{"role":"journalistic_source","url":"https://news.example/story"}
}
EVIDENCE={
    "verified":True,"indicator":"occupazione","unit":"%",
    "source_url":"https://www.istat.it/rapporto-occupazione",
    "source_sha256":"a"*64,"location":"1:row:4",
    "extraction_method":"same_row_explicit_year_structured_table",
    "observations":[{"period":"2024","value":50.0},{"period":"2025","value":51.0}]
}

class PrimaryResearchTests(unittest.TestCase):
    def test_official_site_only_not_homepage(self):
        self.assertTrue(allowed_url("https://www.istat.it/rapporto-occupazione",DOMAINS))
        for url in ("https://www.istat.it/", "https://istat.it.evil.org/report",
                    "http://istat.it/rapporto", "https://localhost/rapporto",
                    "https://user:secret@istat.it/report",
                    "https://news.example/story"):
            self.assertFalse(allowed_url(url,DOMAINS),url)

    def test_press_report_not_primary(self):
        self.assertEqual(article_leads(ARTICLE),[])
        self.assertFalse(relevant_evidence(EVIDENCE,ARTICLE,"www.inps.it"))

    def test_same_source_indicator_is_candidate_only(self):
        e=dict(EVIDENCE)
        self.assertTrue(relevant_evidence(e,ARTICLE,"www.istat.it"))
        e["source_sha256"]=""
        self.assertFalse(relevant_evidence(e,ARTICLE,"www.istat.it"))

    def test_extraction_is_never_auto_published(self):
        source="https://www.istat.it/rapporto-occupazione"
        a=dict(ARTICLE)
        a["public_source"]={"role":"primary_statistical_source","url":source}
        def fetch(_):
            return b"<html><table></table></html>","text/html",source
        def extract(_):
            return {"source_url":source,"status":"verified","evidence":[EVIDENCE]}
        result=examine(source,a,DOMAINS,fetch_fn=fetch,extract_fn=extract)
        self.assertEqual(result["status"],"potential_evidence_requires_review")
        row=research_article(a,DOMAINS,search_fn=lambda q,limit:[],fetch_fn=fetch,extract_fn=extract)
        self.assertEqual(row["status"],"manual_primary_review_required")
        self.assertIs(row["publication_allowed_automatically"],False)

    def test_no_source_no_fabricated_numbers(self):
        q=build_queue([ARTICLE],DOMAINS,limit=1,search_fn=lambda q,limit:[])
        self.assertEqual(q["checked"],1)
        self.assertEqual(q["items"][0]["candidate_count"],0)
        self.assertEqual(q["items"][0]["status"],"primary_evidence_not_found")

    def test_not_published_article_excluded(self):
        draft=dict(ARTICLE,publication_status="quarantined")
        q=build_queue([draft],DOMAINS,search_fn=lambda q,limit:[])
        self.assertEqual(q["checked"],0)

if __name__=="__main__":
    unittest.main()
