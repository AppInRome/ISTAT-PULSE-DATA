#!/usr/bin/env python3
"""Offline checks for the original PULSE Italia newsroom layer."""
import unittest
from datetime import datetime, timezone
from scripts.pulse_italia_newsroom import (
    italy_relevant, same_story, select_candidates, eligible_primary,
    italian_official_url, score
)

NOW = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)


def candidate(i, headline, topic="LAVORO", country=None, verified=False):
    story = {
        "id": "PULSE-TEST-" + str(i),
        "publication_status": "published",
        "published_at": "2026-11-13T12:00:00Z",
        "topic": topic, "headline": headline,
        "summary": "Rapporto statistico sul territorio selezionato",
        "public_source": {
            "url": "https://www.istat.it/comunicato-" + str(i),
            "role": "primary_statistical_source" if verified else "journalistic_source",
        },
        "chart_spec": {"status": "verified", "data": [
            {"period": "2024", "value": 7}, {"period": "2025", "value": 8}
        ]} if verified else {"status": "requires_primary_source"},
    }
    if country:
        story["geographic_scope"] = {"country_code": country}
    if verified:
        story["verification_tier"] = "verified_comparable_series"
        story["verified_series"] = [{"verified": True, "observations": [
            {"period": "2024", "value": 7}, {"period": "2025", "value": 8}
        ]}]
    return story


class ItalianScopeTests(unittest.TestCase):
    def test_italy_explicit(self):
        self.assertTrue(italy_relevant(candidate(1, "Costo del lavoro", country="IT")))

    def test_foreign_explicit_rejected(self):
        self.assertFalse(italy_relevant(candidate(1, "Crescita dell'Italia", country="FR")))

    def test_italian_language_does_not_imply_italy(self):
        self.assertFalse(italy_relevant(candidate(1, "Crescita dei salari in Germania")))

    def test_italian_city_detected_by_word(self):
        self.assertTrue(italy_relevant(candidate(1, "Costo delle case a Roma")))

    def test_foreign_city_no_false_substring(self):
        self.assertFalse(italy_relevant(candidate(1, "Prezzi delle case in Romania")))

    def test_foreign_official_source_blocked(self):
        self.assertFalse(italian_official_url("https://www.oecd.org/abc"))
        self.assertTrue(italian_official_url("https://www.istat.it/dati.csv"))
        self.assertFalse(italian_official_url("https://www.istat.it.evil.example/data.csv"))

    def test_verified_evidence_required_for_draft(self):
        x = candidate(1, "Occupazione in Italia", country="IT", verified=True)
        self.assertTrue(eligible_primary(x))
        x["chart_spec"]["data"] = x["chart_spec"]["data"][:1]
        self.assertFalse(eligible_primary(x))

    def test_media_unverified_never_ai_ready(self):
        x = candidate(1, "Rilevazione occupazione in Italia", country="IT")
        self.assertFalse(eligible_primary(x))
        self.assertEqual(
            select_candidates([x], now=NOW)["selected"][0]["eligible_for_ai_draft"], False
        )

    def test_same_story_with_different_tracking_parameters(self):
        a, b = candidate(1, "Lavoro e salari in Italia"), candidate(2, "Lavoro e salari in Italia")
        a["public_source"]["url"] = "https://www.istat.it/a?utm_source=xyz"
        b["public_source"]["url"] = "https://istat.it/a"
        self.assertTrue(same_story(a, b))

    def test_distinct_stories_not_merged_by_topic(self):
        a = candidate(1, "Inflazione nelle famiglie italiane")
        b = candidate(2, "Occupazione e sicurezza in Lombardia")
        self.assertFalse(same_story(a, b))

    def test_diversity_topic_cap(self):
        stories = [candidate(i, "Italia: indagine sul fenomeno " + str(i),
                             country="IT") for i in range(1, 11)]
        result = select_candidates(stories, limit=20, per_topic=4, now=NOW)
        self.assertEqual(result["selected_count"], 4)

    def test_no_quota_filling_with_foreign_stories(self):
        stories = [
            candidate(1, "Aumento del lavoro a Milano"),
            candidate(2, "Occupazione in Germania"),
        ]
        result = select_candidates(stories, limit=20, now=NOW)
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["selected"][0]["id"], "PULSE-TEST-1")

    def test_score_independent_from_existing_pulse_score(self):
        x = candidate(1, "Lavoro in Italia", country="IT")
        x["pulse_score"] = 100
        a = score(x, NOW)
        x["pulse_score"] = 0
        self.assertEqual(a, score(x, NOW))
        self.assertLessEqual(a["total"], 100)


if __name__ == "__main__":
    unittest.main()
