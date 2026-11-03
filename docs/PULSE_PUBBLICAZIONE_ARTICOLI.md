# PULSE — pubblicazione editoriale con prove statistiche

La filiera è disponibile nel repository dati, senza modifiche all'APK Android.

1. Raccolta notizie: `update_news_radar.py` conserva la data originaria della notizia e la fonte giornalistica.
2. Ricerca: `pulse_primary_research.py` cerca pagine ufficiali e allegati. I possibili dati diventano dossier con URL, hash del documento, posizione, unità, periodo e indicatore.
3. Revisione: `pulse_reviewed_drafts.py` crea bozze solo da evidenze approvate con controllo esplicito della fonte.
4. Redazione: il giornalista prepara un testo originale specifico (titolo, occhiello, almeno cinque paragrafi e 360 parole, nota di verifica), senza copiare il testo della testata.
5. Pubblicazione: `pulse_editorial_publish.py` verifica provenienza, autorizzazione, lunghezza, tabella, grafico e coerenza della data, producendo `data/news/approved_features.json`.
6. Aggiornamento: `update_news_radar.py` applica gli articoli approvati nella normale rigenerazione conservando ID e data; `refresh_daily_safe.py` li passa al processo isolato. Un articolo approvato non viene duplicato in OGGI.
7. Protezione: un archivio di approvazioni obsoleto o incoerente non blocca il normale aggiornamento della rassegna.

### Esecuzione manuale documentata

```bash
python -m unittest discover -s tests -p test_primary_research.py -v
python -m unittest discover -s tests -p test_reviewed_drafts.py -v
python -m unittest discover -s tests -p test_editorial_publish.py -v

python scripts/pulse_primary_research.py --limit 8 --output research-report.json
# La decisione di revisione NON è prodotta automaticamente dal software.
python scripts/pulse_reviewed_drafts.py --dossiers research-report.json --decisions reviewed-decisions.json --output reviewed-drafts.json
python scripts/pulse_editorial_publish.py --drafts reviewed-drafts.json --edits editorial-copy.json --output data/news/approved_features.json
python scripts/refresh_daily_safe.py --mode news
```

Il file `editorial-copy.json` contiene `articles` con `article_id`, `decision: publish`, `reviewer`, `copy_editor`, `approved_at` ISO 8601 con fuso, `headline`, `lead`, `paragraphs` (lista di paragrafi narrativi originali) e `independent_verification_note`.

### Garanzie e limiti

- Non si pubblicano grafici o tabelle con dati ricavati soltanto da titoli di giornale.
- Il sistema non inventa approvazioni, fonti, statistiche o testo giornalistico specifico quando l'evidenza manca.
- Articoli approvati conservano identità e cronologia; gli altri restano segnalazioni attribuite.
- L'articolo BES 2026 in `data/editorial_casefiles.json` contiene una versione giornalistica estesa basata sulle due fonti ISTAT segnalate nel dossier; il generatore ora aggiorna anche un caso già presente nell'archivio.
- L'infrastruttura di controllo non significa che centinaia di segnalazioni siano state già verificate o riscritte: ogni articolo richiede dati e testi effettivi.
