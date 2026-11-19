import unittest

from scripts.pulse_editorial_status import make_status, latest_published_at


class EditorialStatusTests(unittest.TestCase):
    def sample(self):
        feed = {"articles": [
            {"id": "PULSE-DATA-1", "publication_status": "published",
             "published_at": "2026-11-14T20:00:00Z",
             "first_published_at_utc": "2026-11-14T20:00:00Z"}
        ]}
        frontpage = {"generated_at": "2026-11-19T08:00:00Z"}
        report = {"published_new": 0, "published_article_ids": [],
                  "research_checked": 2, "rejected": 1,
                  "rejected_reasons": {"numeric_evidence_incomplete": 1},
                  "candidate_decisions": [
                      {"article_id": "PULSE-DATA-1", "novelty": "unchanged",
                       "tier": "context", "decision": "already_published"},
                      {"article_id": "PULSE-DATA-2", "novelty": "revision",
                       "tier": "review_revision", "decision": "revision_requires_review"}]}
        pipeline = {"official_discovery": {"sources_considered": [
            {"provider": "ISTAT", "status": "inaccessible_or_unsupported"},
            {"provider": "EUROSTAT", "status": "source_series_found"}]}}
        return feed, frontpage, report, pipeline

    def test_zero_new_does_not_forge_publication_date(self):
        args = self.sample()
        result = make_status(*args, "2026-11-19T09:00:00Z")
        self.assertEqual(result["last_editorial_check_at"], "2026-11-19T09:00:00Z")
        self.assertEqual(result["last_published_article_at"], "2026-11-14T20:00:00Z")
        self.assertEqual(result["published_articles_total"], 1)
        self.assertEqual(result["selection_counts"]["revision_requires_review"], 1)
        self.assertEqual(result["sources_unavailable"][0]["source"], "ISTAT")

    def test_new_article_requires_real_presence(self):
        feed, frontpage, report, pipeline = self.sample()
        report["published_new"] = 1
        report["published_article_ids"] = ["PULSE-DATA-2"]
        with self.assertRaisesRegex(ValueError, "not_in_feed"):
            make_status(feed, frontpage, report, pipeline, "2026-11-19T09:00:00Z")
        feed["articles"].append({
            "id": "PULSE-DATA-2", "publication_status": "published",
            "published_at": "2026-11-19T09:00:00Z"})
        status = make_status(feed, frontpage, report, pipeline, "2026-11-19T09:01:00Z")
        self.assertEqual(status["published_new_in_last_check"], 1)
        self.assertEqual(status["last_published_article_at"], "2026-11-19T09:00:00Z")

    def test_invalid_date_and_count_fail_closed(self):
        feed, frontpage, report, pipeline = self.sample()
        with self.assertRaisesRegex(ValueError, "invalid_check_timestamp"):
            make_status(feed, frontpage, report, pipeline, "not_a_date")
        report["published_article_ids"] = ["id"]
        with self.assertRaisesRegex(ValueError, "publication_count_mismatch"):
            make_status(feed, frontpage, report, pipeline, "2026-11-19T09:00:00Z")

    def test_no_publication_when_archive_empty(self):
        self.assertIsNone(latest_published_at([]))


if __name__ == "__main__":
    unittest.main()
