"""No-network regression tests for PULSE official Observer collector."""
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "update_observer_daily.py"
spec = importlib.util.spec_from_file_location("update_observer_daily", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class ObserverCollectorTests(unittest.TestCase):
    def test_rss_parser_and_domain_filter(self):
        sample = b"""<rss><channel><item><title>Rapporto su dati e imprese</title>
<link>https://www.cna.it/rapporto-imprese</link>
<pubDate>Tue, 27 Oct 2026 08:00:00 GMT</pubDate></item></channel></rss>"""
        self.assertEqual(1, len(mod.items_from_xml(sample)))
        self.assertTrue(mod.host_allowed("https://www.cna.it/pubblicazioni/test", "cna.it"))
        self.assertFalse(mod.host_allowed("https://cna.it.evil.example/article", "cna.it"))

    def test_preserves_last_good_and_adds_only_official(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "observer_articles.json"
            status = Path(tmp) / "observer_refresh_status.json"
            original = {"generated_at": "2026-10-23T10:00:00+00:00",
                        "source_count": 65, "source_stats": {},
                        "articles": [
                            {"id": f"OBS-HIST-{i}", "published_at": "2026-10-03T10:00:00Z",
                             "public_source": {"url": f"https://cna.it/historical/{i}"}}
                            for i in range(1050)]}
            archive.write_text(json.dumps(original), encoding="utf-8")
            feed = (b"""<rss><channel><item><title>Dati e imprese: rapporto nazionale</title>
<link>https://www.cna.it/rapporto-nazionale</link>
<pubDate>Tue, 27 Oct 2026 08:00:00 GMT</pubDate></item></channel></rss>""")
            def fetched(url, domain):
                if domain == "cna.it": return feed
                raise OSError("test offline source not reachable")
            x = mod.update(archive, status, fetcher=fetched,
                           now=datetime(2026, 10, 27, 10, tzinfo=timezone.utc))
            self.assertEqual(1, x["new"])
            self.assertEqual(1051, len(json.loads(archive.read_text())["articles"]))
            self.assertEqual(65, json.loads(archive.read_text())["source_count"])
            self.assertEqual(3, len([k for k,v in json.loads(status.read_text())["sources"].items()
                                     if v["status"] == "error"]))
            # No new items -> original content and generated_at remain unchanged.
            snapshot = archive.read_bytes()
            mod.update(archive, status, fetcher=fetched,
                       now=datetime(2026, 10, 27, 11, tzinfo=timezone.utc))
            self.assertEqual(snapshot, archive.read_bytes())

if __name__ == "__main__":
    unittest.main()
