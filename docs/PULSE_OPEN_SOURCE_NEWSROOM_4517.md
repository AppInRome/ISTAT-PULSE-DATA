# PULSE 4.5.17 — infrastruttura editoriale open source

## Moduli integrati (backend GitHub)
- `trafilatura` (Apache-2.0): lettura del testo completo della pagina giornalistica come **contesto di ricerca**. Non ripubblica il testo del giornale.
- Estrattori PULSE già presenti: HTML, CSV, XLS/XLSX, PDF e SDMX, soltanto osservazioni con indicatore/periodo/unità.
- `pulse_http_cache.py`: evita richieste ripetute per la stessa URL, conserva hash del contenuto e applica almeno 16 secondi tra richieste riconosciute come ISTAT SDMX nello stesso job; non usa proxy, IP rotation o bypass.
- `pulse_open_source_adapters.py`: produce specifiche Vega-Lite dai medesimi dati di `chart_spec` usati da Android. Ha inoltre adattatori **opzionali** per Docling e OpenSDMX.
- `pulse_ai_newsroom.py`: scrittura assistita da modello linguistico **opzionale**, soltanto dopo la verifica dei dati, con verifica delle cifre presenti in testo. Senza un modello configurato resta il testo deterministico da evidenze verificate.

## Attivazione e costi
Il lavoro ordinario su GitHub Actions utilizza la libreria Trafilatura. Non richiede nuove chiavi per i numeri. `Docling` è disattivato di default per il consumo elevato di CPU/RAM; `opensdmx` è un componente sperimentale, richiede Python 3.12 e query SDMX con dimensioni esplicite: non si possono indovinare serie o scaricare l'intero ISTAT senza filtro.

La redazione AI è disabilitata finché non sono configurate:
```
PULSE_LLM_ENDPOINT=https://provider-autorizzato.example/v1/chat/completions
PULSE_LLM_MODEL=modello
PULSE_LLM_API_KEY=chiave_segreta
```
Usare GitHub Actions **Secrets** per la chiave, mai versionarla nel repository. È supportato anche un endpoint Ollama in localhost per esecuzione sul proprio PC, non su runner GitHub. L'esecuzione remota può comportare costi. Non usare `models.github.ai`: GitHub Models è stato ritirato il 30 luglio 2026.

Nessuna app installata localmente potrà usare un modello Ollama sul computer dell'autore a distanza quando questo è spento: per un servizio sempre disponibile è richiesto un endpoint remoto o un backend online.

## Limite ufficiale ISTAT
ISTAT dichiara 5 query SDMX al minuto per indirizzo IP, con possibili blocchi di 1–2 giorni:
https://www.istat.it/classificazioni-e-strumenti/web-services-sdmx/

Il throttle PULSE utilizza un massimo teorico inferiore a 4 richieste al minuto sullo stesso job, cache persistita in GitHub Actions e nessun retry aggressivo in caso di risposta 429. Non può garantire la quota di utenti o processi esterni che usano lo stesso IP: sul limite viene interrotto il download, conservando i dati precedenti.

## Articoli e visualizzazioni
- Il testo non può inserire valori numerici diversi da quelli dell'evidenza elaborata; una proposta AI non conforme viene scartata.
- Grafici Android: `chart_spec`; tabella: `table_spec`; specifica web: `vega_lite_spec`. Per le barre l'asse parte da zero.
- Se non c'è una serie primaria omogenea, non si produce un grafico o una tabella falsi; la notizia rimane attribuita alla stampa.
- L'auto-generazione non garantisce che ogni titolo RSS diventi un reportage completo, né sostituisce una revisione umana delle affermazioni causali.

## Licenze delle dipendenze
Trafilatura Apache-2.0, Docling MIT, OpenSDMX MIT, Vega-Lite BSD-3-Clause. I metadati, le condizioni d'uso dei dataset e i diritti sulle notizie di stampa sono un argomento distinto dalle licenze del software.
