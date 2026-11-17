import importlib.util,json,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
p=Path(__file__).resolve().parents[1]/"scripts"/"pulse_health_monitor.py"
spec=importlib.util.spec_from_file_location("pulse_health_monitor",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Health(unittest.TestCase):
    def fixture(self,root,now,news_hours=1,observer_hours=3):
        data={"last_check_at":(now-timedelta(hours=news_hours)).isoformat(),"sections":{
            "notizie":{"status":"ok","last_success_at":(now-timedelta(hours=news_hours)).isoformat(),
                       "feeds_reached":68,"feeds_configured":73}}}
        observer={"checked_at":(now-timedelta(hours=observer_hours)).isoformat(),
                  "feeds_reached":2,"feeds_configured":4,"articles_new":0,
                  "sources":{"CNA":{"status":"error","error":"HTTP 403"},"CNR":{"status":"ok"},
                             "SINAB":{"status":"error","error":"HTTP 403"},"SVIMEZ":{"status":"ok"}}}
        at=(now-timedelta(hours=news_hours)).isoformat()
        files={"refresh_status.json":data,"observer_refresh_status.json":observer,
               "news/index.json":{"generated_at":at,"oggi":[],"ieri":[],"archivio":["x"],"counts":{"oggi":0,"ieri":0,"archivio":1}},
               "news/articles.json":{"generated_at":at,"articles":[{"id":str(x)} for x in range(100)]}}
        for name,payload in files.items():
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(json.dumps(payload))
    def test_no_new_article_does_not_mean_down(self):
        now=datetime(2026,11,17,18,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root,now)
            result=m.inspect(root,now)
            self.assertTrue(result["healthy"])
            self.assertEqual(0,result["observer_new_publications"])
            self.assertTrue(result["warnings"])
    def test_stale_news_alerts(self):
        now=datetime(2026,11,17,18,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root,now,news_hours=28)
            result=m.inspect(root,now)
            self.assertFalse(result["healthy"])
            self.assertTrue(any("backend_stale" in e for e in result["errors"]))
    def test_no_observer_feed_alerts(self):
        now=datetime(2026,11,17,18,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root,now)
            x=json.loads((root/"observer_refresh_status.json").read_text())
            x["feeds_reached"]=0;(root/"observer_refresh_status.json").write_text(json.dumps(x))
            self.assertFalse(m.inspect(root,now)["healthy"])

if __name__=="__main__":unittest.main()
