"""Offline tests; never contact Claude."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from scripts import pulse_claude_today as editor

class ClaudeNewsTests(TestCase):
    def test_quality(self):
        good="\n\n".join([("parola "*85).strip()+"." for _ in range(3)])
        self.assertTrue(editor.editorial_ok(good))
        self.assertFalse(editor.editorial_ok(good[:-1]))
        self.assertFalse(editor.editorial_ok("Testo breve."))
    def test_canonical(self):
        self.assertEqual(editor.canonical_url("https://EXAMPLE.org/a/?utm_source=x#foo"),"https://example.org/a")
    def test_no_paid_call_if_disabled(self):
        with patch.dict("os.environ",{"PULSE_CLAUDE_ENABLED":"false"}), patch.object(editor.requests,"post") as send:
            self.assertEqual(editor.main(),0)
            send.assert_not_called()
    def test_archive_and_dedup(self):
        with TemporaryDirectory() as directory:
            root=Path(directory); data=root/"articles.json"; index=root/"index.json"
            url="https://www.istat.it/example"
            headline="Rapporto statistico ufficiale con data corretta"
            data.write_text(json.dumps({"articles":[{"id":i,"headline":headline,"public_source":{"url":url}} for i in ["a","b"]]}))
            index.write_text(json.dumps({"oggi":["a"]}))
            (root/"green_index.json").write_text(json.dumps({"oggi":["b"]}))
            class Response:
                status_code=200
                def json(self):return {"text":"\n\n".join([("parola "*85).strip()+"." for _ in range(3)]),"stop_reason":"end_turn","model":"claude-sonnet-5-5","source_url":url,"source_headline":headline}
            with patch.object(editor,"text_from_original",return_value="Fonte valida "*100),patch.object(editor.requests,"post",return_value=Response()) as send:
                self.assertEqual(editor.publish(data,index,"https://worker.test","job")["created"],1)
                self.assertEqual(editor.publish(data,index,"https://worker.test","job")["created"],0)
                self.assertEqual(send.call_count,1)
                self.assertTrue((root/"ai_published_archive.json").exists())
                self.assertTrue((root/"ai_attempts.json").exists())
    def test_truncation_never_published(self):
        with TemporaryDirectory() as directory:
            root=Path(directory); data=root/"articles.json"; index=root/"index.json"
            url="https://www.istat.it/example"
            headline="Rapporto statistico ufficiale con data corretta"
            data.write_text(json.dumps({"articles":[{"id":"a","headline":headline,"public_source":{"url":url}}]}))
            index.write_text(json.dumps({"oggi":["a"]}))
            class Response:
                status_code=200
                def json(self):return {"text":"\n\n".join([("parola "*85).strip()+"." for _ in range(3)]),"stop_reason":"max_tokens","model":"claude-sonnet-5-5","source_url":url,"source_headline":headline}
            with patch.object(editor,"text_from_original",return_value="Fonte valida "*100),patch.object(editor.requests,"post",return_value=Response()) as send:
                self.assertEqual(editor.publish(data,index,"https://worker.test","job")["created"],0)
                self.assertEqual(editor.publish(data,index,"https://worker.test","job")["created"],0)
                self.assertEqual(send.call_count,1)
