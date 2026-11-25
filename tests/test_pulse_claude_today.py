"""Offline regression for PULSE Sonnet publisher. No paid calls."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from scripts import pulse_claude_today as editor

class ClaudeNewsTests(TestCase):
    def test_once_only(self):
        with TemporaryDirectory() as directory:
            data=Path(directory)/"articles.json"; index=Path(directory)/"index.json"
            url="https://www.istat.it/comunicato-stampa/example"
            headline="Rapporto statistico ufficiale con data corretta"
            data.write_text(json.dumps({"articles":[{"id":"example",
                "public_source":{"url":url},"headline":headline}]}))
            index.write_text(json.dumps({"oggi":["example"]}))
            class Response:
                status_code=200
                def json(self):return {"text":"X"*200,"source_url":url,"source_headline":headline,
                                        "model":"claude-sonnet-5-5"}
            with patch.object(editor,"text_from_original",return_value="Fonte valida "*100), \
                 patch.object(editor.requests,"post",return_value=Response()) as send:
                first=editor.publish(data,index,"https://worker.test","job")
                self.assertEqual(first["created"],1)
                again=editor.publish(data,index,"https://worker.test","job")
                self.assertEqual(again["created"],0)
                self.assertEqual(send.call_count,1)
                index.write_text(json.dumps({"oggi":[],"ieri":["example"]}))
                self.assertEqual(editor.publish(data,index,"https://worker.test","job")["created"],0)
    def test_google_feed_link_is_not_an_article(self):
        self.assertIsNone(editor.text_from_original("https://news.google.com/rss/articles/demo"))
    def test_no_paid_call_if_disabled(self):
        with patch.dict("os.environ",{"PULSE_CLAUDE_ENABLED":"false"}):
            self.assertEqual(editor.main(),0)

    def test_sections_yesterday_and_shared_deduplication(self):
        with TemporaryDirectory() as directory:
            root=Path(directory); data=root/"articles.json"; index=root/"index.json"
            ids=["news","territory","green","yesterday"]
            headline="Rapporto statistico ufficiale con data corretta"
            url="https://www.istat.it/comunicato-stampa/example"
            data.write_text(json.dumps({"articles":[{"id":i,"public_source":{"url":url},"headline":headline} for i in ids]}))
            index.write_text(json.dumps({"oggi":["news"],"ieri":["yesterday"]}))
            (root/"territori_index.json").write_text(json.dumps({"oggi":["territory","news"]}))
            (root/"green_index.json").write_text(json.dumps({"oggi":["green","territory"]}))
            class Response:
                status_code=200
                def json(self):return {"text":"X"*200,"source_url":url,"source_headline":headline,"model":"claude-sonnet-5-5"}
            with patch.object(editor,"text_from_original",return_value="Fonte valida "*100), patch.object(editor.requests,"post",return_value=Response()) as send:
                self.assertEqual(editor.publish(data,index,"https://worker.test","job")["created"],4)
                self.assertEqual(editor.publish(data,index,"https://worker.test","job")["created"],0)
                self.assertEqual(send.call_count,4)

    def test_failed_responses_count_toward_shared_limit(self):
        with TemporaryDirectory() as directory:
            root=Path(directory); data=root/"articles.json"; index=root/"index.json"
            ids=[str(i) for i in range(25)]
            data.write_text(json.dumps({"articles":[{"id":i,"public_source":{"url":"https://www.istat.it/example"},"headline":"Rapporto statistico ufficiale con data corretta"} for i in ids]}))
            index.write_text(json.dumps({"oggi":ids}))
            class Response:
                status_code=200
                def json(self):return {"text":"invalid"}
            with patch.object(editor,"text_from_original",return_value="Fonte valida "*100), patch.object(editor.requests,"post",return_value=Response()) as send:
                self.assertEqual(editor.publish(data,index,"https://worker.test","job")["created"],0)
                self.assertEqual(send.call_count,20)
