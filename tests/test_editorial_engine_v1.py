"""Offline fixtures are fictional; they are not ISTAT observations."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
import unittest

from scripts import pulse_editorial_engine_v1 as engine
from scripts import pulse_editorial_audit_v1 as auditor


class EditorialEngineTest(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "source_url": "https://www.istat.it/", "dataset_url":"https://www.istat.it/serie-esempio.csv",
            "publisher":"ISTAT", "topic":"LAVORO",
            "schema":{
                "format":"csv", "period_column":"Periodo", "value_column":"Valore",
                "dimensions":{"Indicatore":"Quota esemplificativa (%)", "Territorio":"Italia",
                              "Popolazione":"Persone 14 anni e più", "Unità":"%", "Frequenza":"Annuale"},
                "semantic_columns":{"indicator":"Indicatore", "unit":"Unità","territory":"Territorio",
                                    "population":"Popolazione","frequency":"Frequenza"}
            }
        }
        self.data = ("Indicatore;Territorio;Popolazione;Unità;Frequenza;Periodo;Valore\n"
                     "Quota esemplificativa (%);Italia;Persone 14 anni e più;%;Annuale;2021;10,0\n"
                     "Quota esemplificativa (%);Italia;Persone 14 anni e più;%;Annuale;2022;11,0\n"
                     "Quota esemplificativa (%);Italia;Persone 14 anni e più;%;Annuale;2023;12,0\n"
                     "Quota esemplificativa (%);Italia;Persone 14 anni e più;%;Annuale;2024;13,5\n"
                     "Quota esemplificativa (%);Lazio;Persone 14 anni e più;%;Annuale;2024;52,0\n").encode()
        self.evidence = engine.extract(self.manifest,self.data)
        self.draft = self._make_draft()

    def _make_draft(self):
        # Fictional article for QA only, NEVER publish to a real feed.
        raw = [
          ["L'ultima osservazione della quota esemplificativa indica un valore più alto rispetto al precedente dato pubblicato nella stessa serie statistica.",
           "Il risultato riguarda la popolazione dichiarata nella tabella e non può essere esteso a gruppi diversi senza altre evidenze.",
           "Il confronto è possibile perché la fonte riporta misure con la medesima unità e la stessa definizione dell'indicatore.",
           "Questa continuità è fondamentale per distinguere un cambiamento misurato da una semplice differenza di classificazione."],
          ["L'interpretazione richiede di leggere ciascuna osservazione come parte di una sequenza documentata e non come un numero isolato.",
           "Il primo punto fornisce il riferimento iniziale, mentre quello più recente riassume la situazione nell'ultimo periodo disponibile.",
           "La distanza tra i valori misura una variazione della grandezza, ma non spiega automaticamente da quali fattori dipenda.",
           "Per attribuire cause sarebbe necessario consultare ulteriori indagini che descrivano il meccanismo e il contesto del fenomeno."],
          ["Il grafico rende visibile l'andamento dei valori osservati e consente di seguire gli scostamenti tra periodi consecutivi.",
           "Ogni punto deve mantenere il collegamento alla riga originaria da cui è stato tratto, senza interpolazioni nascoste.",
           "Il lettore può così confrontare la rappresentazione visiva con la tabella e verificare l'esattezza dei dati.",
           "Un eventuale cambiamento nella scala verticale non può cambiare il significato delle misurazioni pubblicate."],
          ["Il dato può essere interessante anche quando non presenta un record, perché descrive il livello effettivamente raggiunto dall'indicatore.",
           "Una notizia affidabile non deve quindi cercare forzatamente una sorpresa o trasformare una differenza numerica in una certezza sociale.",
           "La distinzione tra quanto è stato misurato e quanto resta da spiegare è parte integrante del racconto statistico.",
           "Questa attenzione ai limiti della fonte permette di evitare conclusioni più ampie di quelle sostenute dalle osservazioni."],
          ["Il confronto dei periodi resta consultabile nella tabella originale, insieme alla definizione della popolazione esaminata.",
           "Chi desidera approfondire può consultare l'ente responsabile e controllare le classificazioni utilizzate nella rilevazione.",
           "Il sistema conserva anche l'impronta del documento, in modo che una revisione successiva sia rintracciabile.",
           "La pubblicazione richiede comunque l'approvazione di un revisore umano, distinta dai controlli automatici sui numeri."]
        ]
        draft={"title":"Un dato che cambia: cosa racconta la serie ufficiale sulle quote",
               "lead":"I valori della serie cambiano lungo il periodo osservato, ma una lettura corretta richiede definizioni stabili e attenzione alla popolazione coinvolta.",
               "paragraphs":[" ".join(p) for p in raw],
               "evidence_sha256":auditor.digest(self.evidence),
               "source_url":self.evidence["source_url"],"dataset_url":self.evidence["dataset_url"],
               "publication_status":"draft", "editorial_status":"draft_only"}
        return draft

    def test_exact_classifications_and_series(self):
        self.assertEqual([o["value"] for o in self.evidence["series"]["observations"]],
                         ["10", "11", "12", "13.5"])
        self.assertEqual(len(self.evidence["series"]["observations"]),4)
        self.assertEqual(len(self.evidence["source_locations"]),4)

    def test_unsupported_numeric_claim_rejected(self):
        draft=dict(self.draft)
        draft["paragraphs"]=list(self.draft["paragraphs"])
        draft["paragraphs"][0] += " Il dato raggiunge 99,9%."
        report=auditor.audit(draft,self.evidence)
        self.assertIn("unsupported_numeric_tokens:99.9", report["issues"])

    def test_fictional_manuscript_passes_structure(self):
        report=auditor.audit(self.draft,self.evidence)
        self.assertTrue(report["passed"],report)
        self.assertEqual(report["sentence_count"],21)

    def test_suppressed_datum_is_not_zero(self):
        data=self.data.replace(b"2024;13,5",b"2024;:")
        extracted=engine.extract(self.manifest,data)
        self.assertEqual(len(extracted["series"]["observations"]),3)

    def test_no_series_no_news(self):
        with self.assertRaisesRegex(ValueError,"insufficient_comparable"):
            engine.extract(self.manifest,("Indicatore;Territorio;Popolazione;Unità;Frequenza;Periodo;Valore\n"
                                    "Quota esemplificativa (%);Italia;Persone 14 anni e più;%;Annuale;2024;13,5\n").encode())

    def test_unapproved_never_published(self):
        approval={"decision":"publish","reviewer":"Revisore", "approved_at":"2026-11-13T15:00:00+01:00"}
        with self.assertRaises(ValueError):
            engine.publish_article(self.draft,self.evidence,approval)

    def test_approval_and_feed_merge(self):
        approved={"decision":"publish","reviewer":"Test reviewer", "approved_at":"2026-11-13T15:00:00+01:00",
                  "draft_sha256":auditor.digest(self.draft),"evidence_sha256":auditor.digest(self.evidence),
                  "independent_review_completed":True,"notes":"Test only, not a real ISTAT source"}
        article=engine.publish_article(self.draft,self.evidence,approved)
        root,idx=engine.merge_feeds(article,{"articles":[{"id":"OLD","published_at":"2026-11-10T00:00:00Z"}]},
                                    {"oggi":[],"ieri":[],"archivio":["OLD"]})
        self.assertEqual(len(root["articles"]),2)
        self.assertIn(article["id"], idx["archivio"])
        self.assertEqual(article["chart_spec"]["data"][-1]["value"],13.5)

    def test_manifest_rejects_arbitrary_domains(self):
        bad=json.loads(json.dumps(self.manifest));bad["dataset_url"]="https://evil.test/data.csv"
        with self.assertRaisesRegex(ValueError,"domain_not_in_official_registry"):
            engine.extract(bad,self.data)

    def test_mismatched_dimensions_do_not_mix(self):
        altered=self.data.replace("Quota esemplificativa (%);Italia;".encode(),"Altra quota (%);Italia;".encode())
        with self.assertRaisesRegex(ValueError,"insufficient_comparable"):
            engine.extract(self.manifest,altered)

if __name__=="__main__":unittest.main()
