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
PARAGRAPHS = [
    "Nel rapporto dimostrativo la prima osservazione del 2024 raggiunge il 12 per cento e rende possibile un punto di partenza. Non basta, tuttavia, per ricostruire le condizioni dei singoli cittadini: l'indicatore riguarda un aggregato definito dalla fonte e conserva i propri limiti di misurazione. Il valore deve essere accompagnato dalla descrizione del fenomeno rilevato.",
    "La rilevazione successiva indica 13 per cento nel 2025. Fra i due anni la distanza è di un punto percentuale, non del tredici per cento, perché il confronto riguarda due quote omogenee. Nell'esempio non viene suggerita alcuna causa: la serie documenta il movimento osservato, non i meccanismi che potrebbero spiegarlo.",
    "Il calendario è altrettanto importante dei numeri. La prima colonna si riferisce al 2024 e la seconda al 2025; la data in cui viene pubblicato un articolo non modifica il periodo a cui appartengono le osservazioni. Un titolo che chiamasse questo fenomeno un cambiamento di novembre confonderebbe il lavoro giornalistico con l'anno statistico.",
    "Per leggere la differenza correttamente bisogna mantenere identico il denominatore, la popolazione osservata e l'unità di misura. Il confronto è appropriato soltanto quando la fonte conferma che le definizioni dei due anni sono compatibili. Se cambiasse il metodo di rilevazione, la crescita apparente potrebbe dipendere da quella rottura e richiederebbe un chiarimento.",
    "Una crescita dell'indicatore non prova automaticamente che siano migliorate le condizioni economiche delle famiglie. Prima di adottare un'interpretazione sociale servirebbero ulteriori variabili, disaggregazioni per territorio e informazioni sulla distribuzione degli esiti. Il dato aggregato riassume una misura, ma può nascondere situazioni differenti tra gruppi della popolazione.",
    "La visualizzazione serve a mettere in relazione i due valori, non a enfatizzare un cambiamento piccolo. Una coppia di colonne confrontabili mostra i periodi e le quote effettivamente documentate: una scala sbagliata potrebbe amplificare la distanza fra le due misure. La tabella riporta gli stessi numeri con le etichette originali della fonte.",
    "Il documento originale resta il riferimento per valutare la qualità della conclusione. PULSE non ricava dati da un titolo giornalistico e non attribuisce a una testata la responsabilità di un confronto ricostruito altrove. Tutti i passaggi, dalla verifica del documento alla scelta degli indicatori, devono restare riconoscibili anche dopo la pubblicazione del pezzo.",
    "Il risultato finale è dunque circoscritto: nell'esempio di test un indicatore passa dal dodici al tredici per cento nell'arco di un anno. Questa informazione è utile soltanto se spiegata insieme a definizione, limiti e fonti, evitando di trasformarla in un racconto di successo o di crisi senza elementi sufficienti."
]
EDIT = {
    "article_id": "PULSE-MEDIA-EXAMPLE", "decision": "publish",
    "reviewer": "Revisore Test", "copy_editor": "Redattore Test",
    "approved_at": "2026-11-03T13:00:00+00:00",
    "headline": "Un indicatore economico sale di un punto fra i due anni",
    "lead": "Nel dataset dimostrativo un indicatore passa dal 12 al 13 per cento tra il 2024 e il 2025. Il confronto è illustrativo e serve a verificare il controllo editoriale del sistema.",
    "paragraphs": PARAGRAPHS,
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
