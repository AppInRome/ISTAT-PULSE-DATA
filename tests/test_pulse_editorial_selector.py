"""Offline regressions: novelty, revisions, editorial thresholds, no AI.

All data below are SIMULATED evidence, not published Italian statistics.
"""
from copy import deepcopy
from datetime import datetime,timezone
import unittest

from scripts import pulse_editorial_selector as news

NOW="2026-11-14T18:40:00Z"


def fake(region="Italia",topic="DEMOGRAFIA",before=1000,after=1450,
         year="2025",source_update="2026-11-13T11:00:00+00:00"):
    return {"verified":True,"publisher":"EUROSTAT",
        "source_url":"https://ec.europa.eu/eurostat/databrowser/view/demo_pjan/default/table",
        "dataset_url":"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_pjan?geo=IT",
        "source_sha256":"f"*64,"source_publication_date":source_update,
        "topic":topic,
        "series":{"indicator":"Popolazione al primo gennaio","territory":region,
                  "unit":"persone","population":"Residenti","frequency":"Annuale",
                  "classification_values":{"geo":"IT","sex":"T"},
                  "observations":[{"period":str(int(year)-1),"value":before},
                                  {"period":year,"value":after}]}}
def item(e,i="PULSE-DATA-SIM"):
    return {"id":i,"topic":e["topic"],"published_at":NOW}


class SelectorTests(unittest.TestCase):
    def test_first_discovery_is_not_claimed_new_official_release(self):
        e=fake(source_update=None)
        a=news.assess(item(e),e,None,datetime.fromisoformat(NOW.replace("Z","+00:00")),{})
        self.assertEqual(a["novelty"],"first_seen_by_pulse")
        self.assertEqual(a["tier"],"catalogue")
        self.assertFalse(a["source_release_proven"])

    def test_new_official_period_large_change_selected(self):
        e=fake()
        previous=news._updated_state({**e,"series":{**e["series"],
           "observations":[{"period":"2023","value":900},
                           {"period":"2024","value":1000}]}},None,"2026-09-01T12:00:00Z")
        a=news.assess(item(e),e,previous,
            datetime.fromisoformat(NOW.replace("Z","+00:00")),{"LAVORO":27})
        self.assertEqual(a["novelty"],"new_reference_period")
        self.assertEqual(a["tier"],"feature")
        self.assertGreaterEqual(a["score"],65)

    def test_same_unchanged_data_never_generates_news(self):
        e=fake()
        state=news._updated_state(e,None,NOW)
        a=news.assess(item(e),e,state,
            datetime.fromisoformat(NOW.replace("Z","+00:00")),{})
        self.assertEqual(a["novelty"],"unchanged")
        self.assertEqual(a["tier"],"catalogue")
        self.assertEqual(a["parts"]["newness"],0)

    def test_same_period_revised_requires_review(self):
        e=fake()
        prior=news._updated_state(e,None,NOW)
        e["series"]["observations"][-1]["value"]=1900
        a=news.assess(item(e),e,prior,
            datetime.fromisoformat(NOW.replace("Z","+00:00")),{})
        self.assertEqual(a["novelty"],"revision")
        self.assertEqual(a["tier"],"review_revision")
        self.assertEqual(a["period_reference"],"2025")

    def test_100_percent_relative_small_base_is_not_big_news(self):
        e=fake(before=2,after=4,source_update=None)
        signal,why=news.change_score(e)
        self.assertEqual(signal,0)
        self.assertIn("non_sufficiente",why)

    def test_nonadjacent_period_cannot_claim_a_comparison(self):
        e=fake()
        e["series"]["observations"][0]["period"]="2022"
        signal,_=news.change_score(e)
        self.assertEqual(signal,0)

    def test_quarterly_and_monthly_changes_checked(self):
        self.assertTrue(news.consecutive("2025-12","2026-01"))
        self.assertTrue(news.consecutive("2025-Q4","2026-Q1"))
        self.assertFalse(news.consecutive("2025-Q2","2025-Q4"))

    def test_topic_diversity_and_daily_caps(self):
        inputs=[]
        for i in range(9):
            e=fake(region="Regione"+str(i))
            inputs.append((item(e,i="PULSE-DATA-SIM"+str(i)),e))
        prior={"series":{}}
        for i,e in enumerate(x[1] for x in inputs):
            older=deepcopy(e)
            older["series"]["observations"][-1]["period"]="2024"
            older["series"]["observations"][-2]["period"]="2023"
            prior["series"][news.series_key(e)]=news._updated_state(older,None,NOW)
        result,ledger,byid=news.evaluate(inputs,[],prior,{},NOW)
        self.assertEqual(len(result["features_new"]),2)
        self.assertGreaterEqual(result["catalogue_updates_count"],7)
        self.assertEqual(len(ledger["series"]),9)

    def test_no_duplicate_frontpage_in_same_day_and_no_republish_next_day(self):
        e=fake()
        old=deepcopy(e)
        old["series"]["observations"][-1]["period"]="2024"
        old["series"]["observations"][-2]["period"]="2023"
        ver={"series":{news.series_key(e):news._updated_state(old,None,NOW)}}
        first,vers,_=news.evaluate([(item(e),e)],[],ver,{},NOW)
        self.assertEqual(len(first["features_new"]),1)
        again,vers2,_=news.evaluate([(item(e),e)],[],vers,first,NOW)
        self.assertEqual(again["features_new"],[])
        self.assertEqual(again["featured_article_ids"],first["featured_article_ids"])
        nextday,vers3,_=news.evaluate([(item(e),e)],[],vers2,first,
                                      "2026-11-15T19:30:00Z")
        self.assertEqual(nextday["featured_article_ids"],[])

if __name__=="__main__":unittest.main()
