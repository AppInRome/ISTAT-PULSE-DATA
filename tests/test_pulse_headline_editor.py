"""Regression: only displayed headings may change; never prose or graphs.

Uses the 27 *real* previously published INPS official features as corpus, and
does not call any external API or write to the production news feed.
"""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import pulse_headline_editor as titles
from scripts import pulse_automatic_feature_publish as publish

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "news" / "automatic_features.json"


def without_title(x):
    return {k: deepcopy(v) for k, v in x.items()
            if k not in ("headline", "pulse_title")}


class JournalisticHeadlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.feed = json.loads(CORPUS.read_text(encoding="utf-8"))
        cls.corpus = cls.feed["articles"]

    def test_real_verified_articles_get_descriptive_human_titles_only(self):
        count = 0
        seen = set()
        for original in self.corpus:
            if not original.get("verified_series_relevant"):
                continue
            series = original["verified_series_relevant"][0]
            if "Integrazioni Salariali" not in series["indicator"]:
                continue
            with self.subTest(id=original["id"]):
                updated = titles.with_editorial_headline(original)
                # Live GitHub already contains the completed point-1 headings.
                # Both the original and already-corrected state are acceptable;
                # the writer must never rewrite other article fields.
                self.assertEqual(without_title(updated), without_title(original))
                self.assertEqual(updated["headline"], updated["pulse_title"])
                self.assertLessEqual(len(updated["headline"]), 110)
                self.assertNotIn("Numero_", updated["headline"])
                self.assertNotIn("2025-12", updated["headline"])
                self.assertIn("2025", updated["headline"])
                self.assertNotIn(updated["headline"], seen)
                seen.add(updated["headline"])
                self.assertIs(titles.with_editorial_headline(updated),updated)
                count += 1
        self.assertGreaterEqual(count,20)

    def test_never_invent_trends_without_adjacent_period(self):
        # Multi-source newsroom: the first feed item may now be EUROSTAT.
        # This regression specifically tests INPS headline terminology.
        sample=deepcopy(next(item for item in self.corpus
                             if (item.get("public_source") or {}).get("domain") == "INPS"))
        s=sample["verified_series_relevant"][0]
        s["observations"][-2]["period"]="2025-05"
        title=titles.journalistic_headline(sample)
        self.assertIsNotNone(title)
        self.assertNotIn("aumentano",title)
        self.assertNotIn("calano",title)
        self.assertNotIn("stabili",title)

    def test_unverified_media_and_unsupported_measure_unchanged(self):
        # Multi-source newsroom: the first feed item may now be EUROSTAT.
        # This regression specifically tests INPS headline terminology.
        sample=deepcopy(next(item for item in self.corpus
                             if (item.get("public_source") or {}).get("domain") == "INPS"))
        for invalid in (
            {"automatic_review":{"passed":False,"model_used":False}},
            {"editorial_format":"media_radar"},
            {"publication_status":"quarantined"},
            {"public_source":{"domain":"INPS","role":"journalistic_source"}},
        ):
            with self.subTest(invalid=invalid):
                modified=deepcopy(sample)
                modified.update(invalid)
                self.assertIs(titles.with_editorial_headline(modified),modified)
        modified=deepcopy(sample)
        modified["verified_series_relevant"][0]["indicator"]="Numero_totale_inventato"
        self.assertIsNone(titles.journalistic_headline(modified))

    def test_existing_27_are_retitled_without_regenerating_any_article(self):
        with TemporaryDirectory() as d:
            dst=Path(d)/"automatic_features.json"
            dst.write_text(json.dumps(self.feed,ensure_ascii=False),encoding="utf-8")
            before=json.loads(dst.read_text(encoding="utf-8"))
            result=publish.publish(Path(d)/"empty",dst,now="2026-11-14T17:00:00Z")
            after=json.loads(dst.read_text(encoding="utf-8"))
            # Current corpus was already retitled on 14 Nov 2026.
            self.assertEqual(result["retitled_existing"],0)
            self.assertEqual(result["published_new"],0)
            self.assertEqual(len(before["articles"]),len(after["articles"]))
            for o,n in zip(before["articles"],after["articles"]):
                self.assertEqual(without_title(o),without_title(n))
            written=dst.read_bytes()
            second=publish.publish(Path(d)/"empty",dst,now="2026-11-15T17:00:00Z")
            self.assertEqual(second["status"],"unchanged")
            self.assertEqual(written,dst.read_bytes())


if __name__ == "__main__":
    unittest.main()
