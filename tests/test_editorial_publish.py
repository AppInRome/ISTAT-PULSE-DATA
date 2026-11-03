"""PULSE newsroom gate regression: no fake dates, charts, approval or duplicate IDs."""
import unittest
from scripts.pulse_editorial_publish import validate_feature, merge_features

URL = "https://www.istat.it/rapporto/esempio"
DRAFT = {
    "id": "PULSE-MEDIA-EXAMPLE", "published_at": "2026-11-01T09:00:00+00:00",
    "publication_status": "draft", "verification_tier": "verified_comparable_series",
    "origin_kind": "pulse_media_radar", "topic": "ECONOMIA",
    "public_source": {"role": "primary_statistical_source", "url": URL},
    "discovery": {"role": "journalistic_radar", "original_url": "https://news.example/story"},
    "chart_spec": {"status": "verified", "source_url": URL,
                   "data": [{"period": "2024", "value": 12.0}, {"period": "2025", "value": 13.0}]},
    "table_spec": {"status": "verified", "source_url": URL,
                   "rows": [["2024", "12", "%"], ["2025", "13", "%"]]},
    "editorial_review": {"reviewer": "Revisore Test", "source_sha256": "a"*64,
                          "source_location": "table:1:row:3"}
}
PARA = ("Questo paragrafo racconta una situazione documentata attraverso la serie ufficiale. "
        "Il confronto fra i periodi deve rispettare la definizione dell'indicatore, "
        "il territorio osservato e la metodologia dichiarata. "
        "Una differenza tra due valori, da sola, non dimostra quali cause "
        "abbiano determinato il cambiamento rilevato nel documento.")
EDIT = {
    "article_id": "PULSE-MEDIA-EXAMPLE", "decision": "publish",
    "reviewer": "Revisore Test", "copy_editor": "Redattore Test",
    "approved_at": "2026-11-03T13:00:00+00:00",
    "headline": "I numeri dell'economia nei dati ufficiali del biennio",
    "lead": "Questa è un'introduzione analitica sufficientemente ampia per inquadrare il dato ufficiale, senza ricavare conclusioni dal solo titolo di stampa.",
    "paragraphs": [PARA + f" Approfondimento documentato {i}." for i in range(8)],
    "independent_verification_note": "Confronto effettuato sulla medesima tabella ufficiale, indicatore, unità e periodi."
}


class PublisherTests(unittest.TestCase):
    def test_publish_with_reviewer_preserves_source_and_date(self):
        item = validate_feature(DRAFT, EDIT)
        self.assertEqual(item["publication_status"], "published")
        self.assertEqual(item["editorial_format"], "individually_edited_longform")
        self.assertEqual(item["published_at"], DRAFT["published_at"])
        self.assertEqual(item["id"], DRAFT["id"])
        self.assertEqual(item["chart_spec"], DRAFT["chart_spec"])
        self.assertEqual(item["table_spec"], DRAFT["table_spec"])
        self.assertEqual(item["discovery"]["evidence_gate"], "strong_primary_match")
        self.assertTrue(item["editorial_review"]["ready_for_publication"])

    def test_reject_unapproved_short_or_incorrect_copy(self):
        invalid = [
            {"decision": "pending"}, {"reviewer": "Fake"},
            {"paragraphs": ["Breve."] * 7}, {"approved_at": "2026-11-03"},
            {"independent_verification_note": ""}, {"article_id": "BAD"}
        ]
        for override in invalid:
            with self.subTest(override=override):
                with self.assertRaises(ValueError):
                    validate_feature(DRAFT, {**EDIT, **override})

    def test_reject_unverified_chart_or_table(self):
        for draft in (
            {**DRAFT, "chart_spec": {"status": "requires_primary_source"}},
            {**DRAFT, "table_spec": {"status": "requires_primary_source"}},
            {**DRAFT, "public_source": {"role": "journalistic_source", "url": URL}},
        ):
            with self.assertRaises(ValueError):
                validate_feature(draft, EDIT)

    def test_merge_does_not_create_new_article_or_change_date(self):
        feature = validate_feature(DRAFT, EDIT)
        press = {"id": DRAFT["id"], "published_at": DRAFT["published_at"], "headline": "Old title"}
        out = merge_features([press], [feature])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["headline"], feature["headline"])
        with self.assertRaises(ValueError):
            merge_features([], [feature])
        with self.assertRaises(ValueError):
            merge_features([press], [feature, feature])
        with self.assertRaises(ValueError):
            merge_features([{**press, "published_at": "2026-11-02"}], [feature])


if __name__ == "__main__":
    unittest.main()
