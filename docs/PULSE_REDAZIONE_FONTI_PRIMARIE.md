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
7. **Bozza verificata**: lo script `scripts/pulse_reviewed_drafts.py` produce una bozza da una decisione `approved` che corrisponda esattamente a URL, SHA-256, posizione, indicatore e unità del dossier. Sono obbligatori revisore, data, territorio, dataset e nota metodologica. La bozza ha `publication_status=draft`, `ready_for_publication=false` e viene salvata fuori dal feed pubblico.
8. **Articolo finale**: titolo specifico, occhiello, introduzione, almeno alcuni paragrafi originali fondati sulla fonte, confronti esplicitamente validati, grafico e tabella **dalla stessa serie**, nota metodologica e fonti cliccabili; conclusioni causali soltanto se documentate. Nessun testo statistico generico usato come sostituto dell'indagine.
9. **Pubblicazione**: processo separato, non implementato in questa fase: una approvazione non si può simulare né dedurre dalla sola corrispondenza del titolo. L'indice Android non deve essere modificato durante la fase di ricerca.

## Codice creato
- `scripts/pulse_primary_research.py`: dossier per ogni segnalazione recente. Non muta `data/news/articles.json`, `data/news/index.json`, né le classifiche. Ogni elemento elenca le fonti esaminate e le ragioni dell'eventuale mancata verifica.
- `scripts/pulse_reviewed_drafts.py`: conversione conservativa di dossier con decisioni di revisione esplicite in bozze con serie grafica e tabellare, senza pubblicazione.
- `tests/test_reviewed_drafts.py`: test anti-promozione, provenienza esatta e rifiuto delle approvazioni incomplete.
- `tests/test_primary_research.py`: simulazioni offline con blocco di URL arbitrari, rifiuto di dati senza provenienza e impossibilità di pubblicazione automatica.
- `.github/workflows/pulse-primary-research.yml`: esecuzione giornaliera e manuale, rapporto scaricabile dagli artifact di GitHub Actions, nessuna scrittura in `main`, nessuna APK.

## Comandi
```bash
python -m unittest discover -s tests -p test_primary_research.py -v
python scripts/pulse_primary_research.py --limit 8 --output research-report.json
# Dopo verifica umana del dossier e compilazione di reviewed-decisions.json:
python scripts/pulse_reviewed_drafts.py --dossiers research-report.json --decisions reviewed-decisions.json --output reviewed-drafts.json
```

## Limiti e prossimi interventi indispensabili
- Non sono **ancora** state rese verificabili tutte le notizie: risultati vuoti, siti che impediscono accesso, tabelle ambigue o unità/territorio non disponibili devono restare non verificati.
- Il controllo automatico della presenza di termini simili tra titolo e indicatore è insufficiente per validare una storia: richiede esame editoriale.
- Il convertitore di decisioni esplicite in bozze è implementato; manca il pannello editoriale di revisione e il successivo flusso di pubblicazione, con ulteriori controlli sul contenuto e qualità giornalistica prima di aggiungere una bozza agli indici pubblici. Nessun dossier viene promosso in automatico.
- Le precedenti versioni Android richiedono un lettore che utilizzi davvero il corpo dell'articolo pubblicato; la presente modifica riguarda il backend.
- Una data nuova di controllo non implica un articolo nuovo. Non sovrascrivere periodi o date per riempire OGGI/IERI.

## Misura qualità proposta
Tracciare *per giorno*: lead esaminati, fonti ufficiali raggiunte, documenti con dati strutturati, candidati coerenti, verifiche umane approvate, articoli originali pubblicati, grafici con provenienza e rifiuti motivati. La copertura reale sostituisce gli slogan "tutti gli articoli verificati".

## Formato minimo della decisione di revisione
```json
{
  "reviews": [
    {
      "decision": "approved",
      "article_id": "ID-PRESENTE-NEL-DOSSIER",
      "reviewer": "Nome del revisore",
      "reviewed_at": "2026-11-03T12:00:00+00:00",
      "primary_publication_date": "2026-11-02",
      "territory": "Italia",
      "dataset": "Nome del dataset effettivamente controllato",
      "methodology": "Nota dettagliata su definizioni, copertura e comparabilità",
      "source_url": "URL-ESATTO-DAL-DOSSIER",
      "source_sha256": "SHA256-ESATTO-DAL-DOSSIER",
      "location": "POSIZIONE-ESATTA-DAL-DOSSIER",
      "indicator": "INDICATORE-ESATTO-DAL-DOSSIER",
      "unit": "UNITÀ-ESATTA-DAL-DOSSIER"
    }
  ]
}
```
Non inserire questo file come approvazione automatica: rappresenta il giudizio di una persona che ha letto e controllato il documento originale. Il nome del revisore non deve essere inventato dal software.
