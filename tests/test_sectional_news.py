"""Green and Territori OGGI/IERI must be categorized without claiming API updates."""
import tempfile
import unittest
import json
from pathlib import Path
from scripts.pulse_sectional_news import make_indices,save_indices

class SectionalNewsTests(unittest.TestCase):
    def test_topical_and_territorial_cross_listing(self):
        index={"generated_at":"2026-10-27T18:00:00Z",
               "oggi":["g1","t1","both","national"],
               "ieri":["yesterday"],"archivio":[]}
        def story(sid,title,topic,territories=None):
            return {"id":sid,"headline":title,"topic":topic,
                    "publication_status":"published",
                    "territories":territories or ["italia"],
                    "public_source":{"role":"journalistic_source"},
                    "publication_tier":"reported_by_media_pending_primary_verification"}
        articles=[
          story("g1","Il consumo di suolo italiano aumenta nel 2025","AMBIENTE"),
          story("t1","Nel Lazio 181 mila imprese guidate da donne","ECONOMIA",["lazio"]),
          story("both","Napoli ultima per qualità dell'ambiente urbano","AMBIENTE",["napoli"]),
          story("national","In Italia sono 5,4 milioni in povertà","ECONOMIA"),
          story("yesterday","Nel Veneto turismo in aumento del 5%","ECONOMIA",["veneto"])
        ]
        out=make_indices(articles,index,index["generated_at"])
        self.assertEqual(["g1","both"],out["green"]["oggi"])
        self.assertEqual(["t1","both"],out["territori"]["oggi"])
        self.assertEqual(["yesterday"],out["territori"]["ieri"])
        self.assertEqual(2,out["green"]["counts"]["oggi"])
        self.assertEqual(0,out["territori"]["counts"]["officially_verified_stories"])
        self.assertEqual("editorial_news_index_not_api_observations",out["green"]["type"])
        with tempfile.TemporaryDirectory() as p:
            save_indices(articles,index,Path(p))
            file=json.loads((Path(p)/"green_index.json").read_text())
            self.assertEqual(index["generated_at"],file["generated_at"])

    def test_old_dates_not_changed_and_missing_articles_not_added(self):
        x={"generated_at":"2026-10-27T10:00:00Z",
           "oggi":["no-such-id","g"],"ieri":[],"archivio":[]}
        articles=[{"id":"g","headline":"Emissioni di CO2: 25 tonnellate",
                   "topic":"AMBIENTE","publication_status":"quarantined",
                   "published_at":"2026-10-25T12:00:00Z"}]
        out=make_indices(articles,x,x["generated_at"])
        self.assertEqual([],out["green"]["oggi"])
        self.assertEqual("2026-10-25T12:00:00Z",articles[0]["published_at"])

if __name__=="__main__":
    unittest.main()
