"""Fast newsroom can publish attributed facts, not verified statistical claims."""
import unittest
from datetime import datetime,timezone,timedelta
from email.utils import format_datetime

from scripts.pulse_media_radar import media_brief,eligible

NOW=datetime(2026,10,27,17,0,tzinfo=timezone.utc)
FEED={"name":"Google News - Corriere statistica"}
def item(title,source="Corriere della Sera",when=NOW):
    return {"title":title+" - "+source,
            "url":"https://news.google.com/rss/articles/pulse-report?oc=5",
            "summary":"Analisi sulla situazione statistica italiana e i dati disponibili in Italia",
            "published_raw":format_datetime(when)}

class MediaRadarTests(unittest.TestCase):
    def test_numeric_statistical_report_is_visible_without_false_chart(self):
        record=item("Consumo di suolo in Lombardia, coperti 102 kmq nel 2025")
        article=media_brief(record,FEED,NOW,"AMBIENTE",72,["lombardia"])
        self.assertIsNotNone(article)
        self.assertEqual("published",article["publication_status"])
        self.assertEqual("journalistic_sourced",article["editorial_status"])
        self.assertEqual("journalistic_source",article["public_source"]["role"])
        self.assertEqual("Corriere della Sera",article["public_source"]["domain"])
        self.assertEqual("requires_primary_source",article["chart_spec"]["status"])
        self.assertFalse(article["statistical_claims"][0]["verified"])
        self.assertIn("non è ancora stata verificata",article["summary"])
        self.assertEqual(article["id"],media_brief(record,FEED,NOW,"AMBIENTE",72,["lombardia"])["id"])

    def test_foreign_elections_sports_and_promos_are_not_statistics_of_italy(self):
        rejects=[
          "Israele alle urne, affluenza al 44,9% alle 14 oggi",
          "Venicemarathon 2026 24 mila iscritti da 124 Paesi",
          "Bonus colonnine 2026, lo sportello chiude alle 12",
          "Somec trimestrale aziendale backlog record di 1,3 miliardi"
        ]
        for title in rejects:
            with self.subTest(title=title):
                self.assertIsNone(media_brief(item(title),FEED,NOW,"ALTRO",70,[]))

    def test_old_article_cannot_become_today_on_later_crawl(self):
        old=item("Occupazione in Lombardia al 66,3% nel 2025",
                 when=NOW-timedelta(days=2))
        self.assertTrue(eligible(old,NOW))
        self.assertFalse(eligible(old,NOW+timedelta(days=5)))

    def test_no_source_or_non_numeric_story_kept_out(self):
        self.assertFalse(eligible(item("Alla riunione sono presenti dirigenti e lavoratori"),NOW))
        x=item("Occupazione a Milano: +1,7% nel 2026")
        x["url"]="javascript:alert(1)"
        self.assertIsNone(media_brief(x,FEED,NOW,"LAVORO",70,["milano"]))

if __name__=="__main__":
    unittest.main()
