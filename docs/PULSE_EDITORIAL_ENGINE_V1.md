# PULSE Editorial Engine v1 — dati ufficiali → articoli con audit → approvazione → feed Android

**Stato:** prototipo eseguibile, non attivato in produzione. Non riscrive `data/news/articles.json` né `data/news/index.json` senza un comando esplicito con destinazioni di output. Non configura GitHub Actions, non contiene credenziali, non pubblica autonomamente.

## Perché è separato dal vecchio Radar

`update_news_radar.py` continua a funzionare con il suo feed. Questo motore affianca il flusso esistente e non promuove automaticamente le segnalazioni giornalistiche a statistiche verificate. La parte Python prepara la notizia, il client PULSE legge `data/news/articles.json`. **Attenzione:** PULSE Android LAB 0.4 legge titolo/sommario/serie dal feed, ma la sua vista Radar non visualizza ancora `pulse_article_body` come articolo completo; serve aggiornare il lettore Android prima di considerare l'esperienza editoriale end-to-end completa.

## Passaggi e invarianti

1. **Fonte primaria.** Un file CSV o JSON è recuperato da dominio ufficiale HTTPS controllato; in alternativa si può usare una copia locale, marcata `retrieval_mode=local_copy`. La fonte originale, l'URL dataset e l'hash SHA-256 sono preservati. Un PDF/HTML può essere una fonte di scoperta, ma questa prima versione *non interpreta arbitrariamente* i suoi numeri: richiede un dataset CSV/JSON ufficiale con colonne esplicite. Per PDF/XLSX resta disponibile il vecchio `pulse_evidence.py` con verifica umana.
2. **Estrazione.** `schema.dimensions` deve indicare **testualmente** le categorie presenti nel dataset, senza riclassificarle. Vengono selezionate solo righe con la stessa popolazione, territorio, unità, frequenza e indicatore. Periodi non presenti, oscurati o ambigui **non diventano zero** e non sono interpolati. Meno di due valori confrontabili → nessun articolo di andamento.
3. **Bozza AI.** Il modello riceve soltanto la serie verificata, i metadati e i confronti computati deterministicamente. Richiesto JSON con titolo, lead e 4–6 paragrafi di 15–25 frasi complessive. Senza modello configurato la pipeline **non finge** di aver scritto un articolo.
4. **Audit indipendente.** Modulo `pulse_editorial_audit_v1.py`, isolato dalla chiamata al modello. Controlla hash evidenza, valori, anni, differenze assolute, variazioni percentuali, struttura, riempitivi noti e numeri non giustificati; ricalcola i fatti. Non è una verifica semantica assoluta: un revisore deve controllare anche attribuzioni, nessi causali, significato dei denominatori, definizioni, titolo e qualità del testo.
5. **Approvazione e feed.** `publish` richiede file di approvazione esplicito con nome revisore, fuso orario, digest della bozza, digest dell'evidenza e `independent_review_completed=true`. Ricontrolla l'articolo e genera **tre file separati:** JSON articolo singolo, `articles.json` aggiornato e `index.json` aggiornato. Gli archivi esistenti restano intatti fino alla pubblicazione intenzionale con commit/PR e verifica Android.

## Manifest di esempio (SOLO schema, senza dati inventati)

```json
{
  "publisher": "ISTAT",
  "source_url": "https://www.istat.it/PERCORSO_REALE_DELLA_PUBBLICAZIONE",
  "dataset_url": "https://www.istat.it/PERCORSO_REALE_DELLA_TABELLA.csv",
  "topic": "LAVORO",
  "schema": {
    "format": "csv",
    "period_column": "Periodo",
    "value_column": "Valore",
    "dimensions": {
      "Indicatore": "ESATTO VALORE PUBBLICATO",
      "Territorio": "Italia",
      "Popolazione": "ESATTA DEFINIZIONE PUBBLICATA",
      "Unità": "%",
      "Frequenza": "Annuale"
    },
    "semantic_columns": {
      "indicator": "Indicatore",
      "unit": "Unità",
      "territory": "Territorio",
      "population": "Popolazione",
      "frequency": "Frequenza"
    }
  }
}
```

I nomi delle colonne e i valori qui sono un esempio di **mappatura**, da adattare alla struttura reale del dataset scaricato. Non inserire classi, territori o denominatori non pubblicati.

## Uso (dalla radice di `ISTAT-PULSE-DATA`)

```bash
# 1. Fonte ufficiale: usa l'URL dataset nel manifest.
python scripts/pulse_editorial_engine_v1.py extract --manifest manifest.json --output lavoro/evidence.json

# Variante offline verificabile: utile per una copia scaricata da sito ufficiale.
python scripts/pulse_editorial_engine_v1.py extract --manifest manifest.json --source-file dataset.csv --output lavoro/evidence.json

# 2. Scrittura AI, API compatibile chat completions (OpenAI/Ollama).
# Configurare PULSE_LLM_ENDPOINT, PULSE_LLM_MODEL, e quando necessario PULSE_LLM_API_KEY
# via variabili d'ambiente/private secrets (NON commit).
python scripts/pulse_editorial_engine_v1.py draft --evidence lavoro/evidence.json --output lavoro/draft.json

# 3. Revisione umana fuori dal programma; creare lavoro/approval.json come sotto.
# 4. Preparare un feed candidato, non pubblicare direttamente in main.
python scripts/pulse_editorial_engine_v1.py publish \
  --evidence lavoro/evidence.json --draft lavoro/draft.json --approval lavoro/approval.json \
  --articles data/news/articles.json --index data/news/index.json \
  --output-articles lavoro/articles.candidato.json \
  --output-index lavoro/index.candidato.json \
  --output-article lavoro/articolo.candidato.json

python -m unittest discover -s tests -p 'test_editorial_engine_v1.py' -v
```

Esempio file `approval.json` (hash da **calcolare** sulle versioni esaminate, non copiarli da un esempio):

```json
{
  "decision": "publish",
  "reviewer": "NOME REVISORE REALE",
  "approved_at": "2026-11-13T17:00:00+01:00",
  "independent_review_completed": true,
  "draft_sha256": "DIGEST DELLA BOZZA SENZA CAMPO audit",
  "evidence_sha256": "DIGEST DELL'EVIDENZA",
  "notes": "Revisione di fonte, serie, grafico, calcoli, testo e conclusioni completata"
}
```

Gli hash si calcolano con la funzione `digest` del modulo di audit (normalizza JSON, chiavi ordinate, UTF-8), come riportato nei test. **Non inserire un'approvazione automatica negli script né abilitare workflow pianificati prima del collaudo reale.**

## JSON PULSE e grafici

L'articolo prodotto include `headline`, `summary`, `pulse_article_body`, `published_at` UTC, `public_source`, `verified_series`, `chart_spec`, `table_spec` ed evidenza SHA-256. Il grafico riporta SOLO i valori originali; `chart_spec` conserva tutti i punti, `verified_series` espone fino agli ultimi 12 per compatibilità con il parser attuale di Android LAB 0.4. I metadati `chart_spec.interaction=pan_zoom_tooltip` descrivono l'interazione desiderata: **non rendono automaticamente interattiva l'interfaccia Android**, che necessita di implementazione/QA dedicata.

Il client esistente filtra gli articoli per `id` presente in `index.json`: per questo `publish` prepara insieme sia `articles.json` sia `index.json`. La classificazione Oggi/Ieri/Archivio viene ricalcolata dal client con fuso Europe/Rome.

## Limiti dichiarati

- Il motore **non trova automaticamente** il CSV corretto a partire da un articolo libero sul web: accetta un URL di dataset ufficiale esplicito nel manifest; il reperimento del collegamento richiede una fase di discovery/approvazione a monte. Si possono usare le componenti storiche `pulse_primary_research.py` per proporre candidati, senza trattarli come verificati.
- Le prove offline usano dati **puramente simulati**: nessuna quota di prova va presentata come osservazione ISTAT reale.
- L'audit blocca numeri fuori dal dossier, non garantisce che un numero consentito sia stato contestualizzato correttamente; la revisione umana resta obbligatoria.
- L'elaborazione e l'approvazione sono due azioni separate: nessuna chiamata AI deve poter scrivere direttamente sui feed di produzione.
- Credenziali LLM soltanto in env/secrets, mai nei commit o nell'app Android.
