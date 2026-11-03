"""Offline tests for the permanent automated PULSE editorial pipeline."""
import unittest
from datetime import datetime, timedelta, timezone
from scripts.pulse_auto_promotion import promote_media_brief, run_pending_research, reported_values

SOURCE = "https://www.istat.it/comunicato-stampa/occupazione/"
ARTICLE = {
    "id": "PULSE-MEDIA-EXAMPLE", "story_fingerprint": "existing-news-fingerprint",
    "origin_kind": "pulse_media_radar", "publication_status": "published",
    "published_at": "2026-11-03T07:00:00+00:00",
    "headline": "Tasso di occupazione al 62,7% nel 2025 secondo ISTAT",
    "reported_headline": "Tasso di occupazione al 62,7% nel 2025 secondo ISTAT",
    "topic": "LAVORO", "pulse_score": 60,
    "public_source": {"role": "journalistic_source", "url": "https://news.example/story",
                      "domain": "news.example"},
    "statistical_claims": [{"raw_value": "62,7%", "verified": False}],
}
RECORD = {
    "verified": True, "indicator": "Tasso di occupazione", "unit": "%",
    "source_url": SOURCE, "source_sha256": "a"*64,
    "location": "sheet:occupazione:row:7",
    "extraction_method": "same_row_explicit_year_structured_table",
    "observations": [
        {"period": "2024", "value": 61.8},
        {"period": "2025", "value": 62.7},
    ]
}
def dossier(record=RECORD):
    return {"article_id": ARTICLE["id"], "status": "manual_primary_review_required",
            "source_checks": [{"url": SOURCE, "candidate_evidence": [record]}]}

class AutoPromotionTests(unittest.TestCase):
    def test_exact_primary_match_generates_full_article_chart_table(self):
        output = promote_media_brief(dict(ARTICLE), dossier())
        self.assertIsNotNone(output)
        self.assertEqual(output["id"], ARTICLE["id"])
        self.assertEqual(output["published_at"], ARTICLE["published_at"])
        self.assertEqual(output["story_fingerprint"], ARTICLE["story_fingerprint"])
        self.assertEqual(output["public_source"]["role"], "primary_statistical_source")
        self.assertEqual(output["chart_spec"]["status"], "verified")
        self.assertEqual(len(output["table_spec"]["rows"]), 2)
        self.assertEqual(output["evidence_provenance"]["source_sha256"], "a"*64)
        self.assertEqual(output["editorial_format"], "automated_verified_analysis")
        self.assertTrue(output["pulse_article_body"])
        self.assertEqual(output["discovery"]["original_url"], "https://news.example/story")

    def test_do_not_promote_mismatch_or_missing_source(self):
        for record in (
            {**RECORD, "source_sha256": ""},
            {**RECORD, "unit": "persone"},
            {**RECORD, "observations": [
                {"period": "2024", "value": 1.0}, {"period": "2025", "value": 2.0}]},
            {**RECORD, "observations": [
                {"period": "2021", "value": 61.8}, {"period": "2022", "value": 62.7}]},
            {**RECORD, "indicator": "Temperatura media"},
        ):
            with self.subTest(record=record):
                self.assertIsNone(promote_media_brief(dict(ARTICLE), dossier(record)))

    def test_local_story_requires_explicit_matching_geography(self):
        local_article = {**ARTICLE, "territories": ["lazio"]}
        self.assertIsNone(promote_media_brief(local_article, dossier()))
        local_row = {**RECORD, "territory": "lazio"}
        self.assertIsNotNone(promote_media_brief(local_article, dossier(local_row)))

    def test_year_not_a_numeric_claim(self):
        self.assertEqual(reported_values({**ARTICLE, "statistical_claims": [
            {"raw_value": "2025"}]}), set())
        self.assertEqual(reported_values({**ARTICLE, "statistical_claims": [
            {"raw_value": "5,4 milioni"}]}), set())

    def test_scheduled_retry_and_no_downgrade(self):
        now = datetime(2026, 11, 3, 15, tzinfo=timezone.utc)
        work = {ARTICLE["id"]: dict(ARTICLE)}
        calls = []
        def research(item, domains):
            calls.append(item["id"])
            return dossier()
        result = run_pending_research(work, ["istat.it"], now, budget=2, research_fn=research)
        self.assertEqual(result["promoted"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(work[ARTICLE["id"]]["published_at"], ARTICLE["published_at"])
        self.assertEqual(work[ARTICLE["id"]]["public_source"]["role"], "primary_statistical_source")
        retry = run_pending_research(work, ["istat.it"], now + timedelta(hours=40),
                                     research_fn=research)
        self.assertEqual(retry["attempted"], 0)

    def test_failure_keeps_original_article(self):
        now = datetime(2026, 11, 3, 15, tzinfo=timezone.utc)
        work = {ARTICLE["id"]: dict(ARTICLE)}
        result = run_pending_research(work, ["istat.it"], now,
                                      research_fn=lambda x,d: dossier({
                                          **RECORD, "source_sha256": "bad"}))
        self.assertEqual(result["promoted"], 0)
        self.assertEqual(work[ARTICLE["id"]]["public_source"]["role"], "journalistic_source")
        self.assertEqual(work[ARTICLE["id"]]["publication_status"], "published")
        self.assertEqual(work[ARTICLE["id"]]["published_at"], ARTICLE["published_at"])

if __name__=="__main__":
    unittest.main()
