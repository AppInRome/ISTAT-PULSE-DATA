# PULSE — Redazione statistica: ricerca, evidenze, revisione, articolo

## Problema riscontrato
Il radar raccoglie molte segnalazioni RSS; `pulse_media_radar.py` genera brevi schede attribuite alla stampa. Il cambiamento grafico nell'APK NON le trasforma in reportage. `pulse_original_editorial.py` è utilizzabile solo se l'articolo dispone di una fonte primaria con osservazioni coerenti.

## Flusso editoriale implementato — primo livello

1. **Acquisizione notizia**: conserva ID, titolo e data pubblicazione originali della fonte giornalistica. Non assegnare mai il timestamp della ricerca come data della notizia.
2. **Ricerca primaria**: usa eventuali collegamenti istituzionali già presenti e risultati di ricerca; accetta soltanto HTTPS e domini esplicitamente configurati in `data/news_radar_sources.json`. I risultati dei motori sono *indizi*, non fonti statistiche.
3. **Download controllato**: URL con percorso specifico, timeout, dimensione massima, analisi di pagina e massimo tre allegati dello stesso host. Formati disponibili: HTML, PDF, CSV, Excel (con i parser esistenti).
4. **Estrazione**: numeri soltanto da tabelle strutturate con indicatore, unità e anno; si registrano URL, hash SHA-256 del documento, localizzazione della riga, metodo di estrazione e osservazioni originali.
5. **Abbinamento prudente**: il candidato deve almeno condividere il tema/indicatore con il titolo. Questa corrispondenza lessicale NON prova che la fonte sostenga la notizia: il dossier resta `manual_primary_review_required`.
6. **Decisione umana**: controllo *obbligatorio* di titolo del documento, autore, data di pubblicazione della fonte, periodo statistico, territorio, popolazione, definizioni, unità, aggiornamenti metodologici, base temporale, eventuale discordanza con la notizia di stampa e completezza della serie. Solo dopo si può approvare una pubblicazione originale PULSE.
7. **Articolo finale**: titolo specifico, occhiello, introduzione, almeno alcuni paragrafi originali fondati sulla fonte, confronti esplicitamente validati, grafico e tabella **dalla stessa serie**, nota metodologica e fonti cliccabili; conclusioni causali soltanto se documentate. Nessun testo statistico generico usato come sostituto dell'indagine.
8. **Pubblicazione**: processo separato, non implementato in questa fase: una approvazione non si può simulare né dedurre dalla sola corrispondenza del titolo. L'indice Android non deve essere modificato durante la fase di ricerca.

## Codice creato
- `scripts/pulse_primary_research.py`: dossier per ogni segnalazione recente. Non muta `data/news/articles.json`, `data/news/index.json`, né le classifiche. Ogni elemento elenca le fonti esaminate e le ragioni dell'eventuale mancata verifica.
- `tests/test_primary_research.py`: simulazioni offline con blocco di URL arbitrari, rifiuto di dati senza provenienza e impossibilità di pubblicazione automatica.
- `.github/workflows/pulse-primary-research.yml`: esecuzione giornaliera e manuale, rapporto scaricabile dagli artifact di GitHub Actions, nessuna scrittura in `main`, nessuna APK.

## Comandi
```bash
python -m unittest discover -s tests -p test_primary_research.py -v
python scripts/pulse_primary_research.py --limit 8 --output research-report.json
```

## Limiti e prossimi interventi indispensabili
- Non sono **ancora** state rese verificabili tutte le notizie: risultati vuoti, siti che impediscono accesso, tabelle ambigue o unità/territorio non disponibili devono restare non verificati.
- Il controllo automatico della presenza di termini simili tra titolo e indicatore è insufficiente per validare una storia: richiede esame editoriale.
- Va realizzato un pannello/repository di decisioni di revisione con approvazione esplicita e audit, più un convertitore di dossier approvati in articoli lunghi e originali. Questo non è ancora implementato; niente pubblicazioni automatiche mascherate.
- Le precedenti versioni Android richiedono un lettore che utilizzi davvero il corpo dell'articolo pubblicato; la presente modifica riguarda il backend.
- Una data nuova di controllo non implica un articolo nuovo. Non sovrascrivere periodi o date per riempire OGGI/IERI.

## Misura qualità proposta
Tracciare *per giorno*: lead esaminati, fonti ufficiali raggiunte, documenti con dati strutturati, candidati coerenti, verifiche umane approvate, articoli originali pubblicati, grafici con provenienza e rifiuti motivati. La copertura reale sostituisce gli slogan "tutti gli articoli verificati".
