# PULSE — Architettura editoriale verificabile (v2)

**Obiettivo:** produrre *fino a* 30 articoli statistici originali al giorno, con dati e grafici riproducibili. Il numero giornaliero e il costo AI sono obiettivi, **non promesse**. Se le evidenze ufficiali non bastano, la coda rimane sotto quota e PULSE lo dichiara.

## Il flusso: fonti prima, AI dopo

1. **Radar continuo**: `.github/workflows/pulse-data-daily.yml`, 07:17–23:17 Europe/Rome ogni ora, 03:17, e aggiornamento completo 08:17/20:17. Rileva *segnalazioni*; non trasforma notizie di altri in dati certificati.
2. **Selezione territoriale e deduplicazione**: `pulse_italia_newsroom.py` seleziona notizie italiane, individua doppioni, varia temi e segnala le fonti.
3. **Ricerca primaria**: `pulse_auto_sources.py` cerca allegati CSV/JSON/XLSX ufficiali; `pulse_italia_official_discovery.py` interroga ISTAT SDMX e INPS Open Data. Nessuna inferenza a partire dalla sola notizia; una ricerca può restituire **zero** dataset eleggibili.
4. **Acquisizione e provenienza**: `pulse_editorial_engine_v1.py` applica whitelist HTTPS, controlli su redirect e dimensione, estrazione di classificazioni e periodi; i file originali sono controllati con hash SHA-256 prima del loro impiego.
5. **Calcolo statistico**: `pulse_italia_chart_analytics.py` calcola esclusivamente serie osservate, differenze, variazioni relative, indici base 100, medie mobili e confronto con lo stesso periodo precedente. Non imputa mancanti, non mescola frequenze o territori e non spaccia calcoli per misurazioni ufficiali.
6. **Controlli indipendenti**: `pulse_data_story_stack.py` applica strumenti di analisi esterni; `pulse_editorial_architecture_v2.py` confronta ogni valore dei grafici e delle tabelle con la fonte originale; identifica serie duplicate, allegati incoerenti, firme di revisione fittizie e casi senza qualità sufficiente.
7. **Brief editoriali verificati**: la coda contiene indicatore, popolazione, unità di misura, periodi, differenze replicabili, URL delle fonti e impronte SHA. Non contiene articoli inventati. I grafici e le tabelle vengono determinati **prima** di interrogare un modello.
8. **AI opzionale solo per il testo**: `pulse_ai_provider.py` configura **Mistral Small 4, modello `mistral-small-2603`**, via `https://api.mistral.ai/v1/chat/completions`. Mistral redige solo titoli, lead e paragrafi vincolati alle evidenze fornite, in JSON; non modifica i dati o i grafici.
9. **Audit dell'articolo**: `pulse_editorial_audit_v1.py` verifica lunghezza, numeri, distinzioni percentuali/punti percentuali, fonte, digest delle evidenze, duplicazioni evidenti e struttura. Un audit automatico non garantisce verità semantica.
10. **Revisione umana indipendente**: `pulse_italia_reviewed_publish.py` e `.github/workflows/pulse-italia-publish.yml` accettano soltanto pacchetti approvati da revisore e copy editor, con digest della bozza e dell'evidenza. **Nessuna AI può autoapprovare o pubblicare** articoli longform nel feed Android.

## Automazione operativa

- Workflow editoriale: `.github/workflows/pulse-italia-newsroom.yml`, alle **08:47 Europe/Rome** (un'esecuzione/giorno, per non pagare doppia produzione degli stessi testi), più esecuzione manuale.
- In modalità normale crea dossier, grafici, tabelle, brief e report **senza nessuna chiamata AI**.
- In modalità AI, richiede **entrambe** le configurazioni GitHub Actions: secret `PULSE_MISTRAL_API_KEY` e variable `PULSE_EDITORIAL_AI_ENABLED=true`. Non pubblicare mai la chiave in log, PR o chat.
- L'archivio `pulse-italia-editorial-review` allegato a ogni esecuzione contiene `official_data_stories/*/evidence.json`, `preview.json`, `review_required.json` e `editorial_architecture/briefs/*.json` con `editorial_architecture_report.json`.
- Il rapporto dichiara quanti dataset effettivamente disponibili e quanti mancanti rispetto a 30. L'app Android continua a usare il feed esistente; nessun refactoring UI è incluso.

## Prezzo e protezioni

Listino ufficiale Mistral Small 4 (14 novembre 2026): **$0,15/M input, $0,60/M output**. Con 8.000 token input + 2.000 output per articolo si stimano **$2,16 per 900 articoli** (900 x ($0,0012 + $0,0012)) prima delle tasse, senza retry, OCR, ricerca o revisione AI aggiuntiva.

La pipeline riserva prudentemente input a **1 token ogni 2 caratteri** e 2.200 token di output per articolo, limitando ogni esecuzione a **$0,15 di spesa massima stimata** per Mistral. Il calcolo non sostituisce il consumo reale comunicato dal fornitore. **Impostare un limite mensile massimo nella console Mistral**: nessun workflow GitHub può garantire da solo un tetto mensile, in particolare con riavvii, correzioni e richieste concorrenti.

## Rischi aperti (espliciti)

- Il ritrovamento quotidiano di 30 fonti numericamente confrontabili **non è dimostrato**: ogni articolo necessita di evidenze autonome. Il catalogo ufficiale deve crescere in copertura e tempestività prima di aumentare i volumi.
- Le scansioni automatiche non hanno il diritto di inventare data di pubblicazione, popolazione, unità, metodologia o causa di una variazione.
- Alcuni feed ufficiali possono restituire 403 o contenuti non strutturati; il sistema mantiene gli ultimi snapshot validi e segnala i mancanti.
- Le informazioni soltanto in PDF non numerico, tabelle scansionate o immagini richiedono un estrattore aggiuntivo o controllo umano; OCR premium non è incluso nei costi.
- Il controllo numerico non sostituisce il fact-checking semantico e la valutazione editoriale del revisore.
- Quando il fornitore AI non risponde o mancano credenziali, i brief restano disponibili. Nessun dato viene pubblicato come articolo per mascherare un errore.
- GitHub Actions non garantisce l'avvio all'esatto minuto programmato; la zona oraria gestisce l'ora legale, ma il job può subire ritardi.
- Gli artefatti Actions hanno una retention temporanea di 14 giorni. Le pubblicazioni approvate sono conservate separatamente in GitHub.

## Comandi riproducibili (senza AI)

```bash
python -m unittest discover -s tests -p 'test_pulse_editorial_architecture_v2.py' -v
python -m scripts.pulse_italia_auto_pipeline --output-dir editorial_output/official_data_stories --max-sources 30 --no-ai
python -m scripts.pulse_editorial_architecture_v2 --review-root editorial_output/official_data_stories --output-dir editorial_output/editorial_architecture --daily-target 30
```

**Materiale di test:** i test usano fixture dichiaratamente sintetiche; solo i workflow di produzione interrogano dati ufficiali reali.

**Fonti prezzi e API:** https://docs.mistral.ai/models/mistral-small-4-0-26-03 ; https://docs.mistral.ai/inference/conversations/structured-output/json_mode .
