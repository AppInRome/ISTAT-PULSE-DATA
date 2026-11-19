# PULSE — Integrazione del recupero editoriale (9 novembre 2026)

## Ambito

Solo il backend **AppInRome/ISTAT-PULSE-DATA**. Nessuna alterazione del codice Android, dei menu, dei feed preesistenti nella fase di installazione, della cronologia o delle GitHub Actions. L'intervento lavora sul repository corrente, non sul vecchio sorgente 4.3.6 del backup.

## Problemi accertati su tre casi originali

1. **Radar (ISTAT, permessi di soggiorno 2025)** — il testo del record `PULSE-34DFAF8E1B8027FD` enumerava cifre senza associarle a indicatori, unità e periodi. Il nuovo guard, quando rileva la formula legacy e nessuna serie tipizzata collegata, conserva identificativo/data/fonte ma usa una **scheda fonte**, senza chiamarla analisi verificata.
2. **Osservatori (Confindustria «DecidiPRESTO!»)** — `OBS-B8D28ACD8CD8F501DB` mescolava il primo paragrafo corretto con cinque titoli correlati alla pagina. Un filtro conservativo elimina la coda **solo se almeno tre paragrafi consecutivi sono riconoscibili come titoli di link**, mantenendo la prima descrizione e il link ufficiale. Le figure numeriche estratte indiscriminatamente dall'HTML vengono azzerate, senza cancellare le cifre nel testo fonte.
3. **Redazione AI (prezzi agosto 2026)** — il vecchio laboratorio creava bozze ragionate e auditate che richiedevano approvazione. Il PULSE DATA corrente ha `pulse_ai_newsroom.py`, che può sostituire il testo dopo una verifica numerica automatica: questa integrazione disabilita la **pubblicazione diretta** di quella sostituzione e aggiunge una CLI per generare **solo una bozza privata** con pacchetto di evidenze tipizzate e controlli umani pendenti.

## Cosa cambia in produzione, SOLO dopo un'eventuale approvazione e merge

- `scripts/update_news_radar.py`: aggiunge `audit_news_archive()` prima della generazione degli indici, conserva ID e `published_at`, rende visibile l'etichetta `editorial_format=source_card` per le vecchie sintesi non contestualizzate e allega un ledger alle serie statistiche valide. Disattiva solo l'inserimento automatico di prosa AI senza approvazione, non la raccolta delle notizie o il calcolo del Radar.
- `scripts/update_observer_daily.py`: prima di aggiornare l'archivio, corregge i fallback descrittivi e i titoli correlati già contaminanti; anche quando non ci sono nuove notizie salva le correzioni una volta. Le nuove schede RSS ufficiali vengono etichettate come `source_card`.
- `scripts/pulse_editorial_recovery_guard.py`: libreria di guardie e funzioni pure senza rete.
- `scripts/pulse_editorial_recovery_draft_cli.py`: editor AI opzionale, privato, senza autosubmission nel feed; richiede che il modello sia già configurato e che ci sia una serie primaria realmente verificata. Non memorizza token o bozze in un repository pubblico.
- `scripts/pulse_editorial_recovery_audit_cli.py`: anteprima statistica e opzione `--apply` con backup separato dei due JSON; **non richiesta nell'installazione**.

## Compatibilità e criteri di blocco

- Usa il ramo **corrente** del repository pubblico DATA e richiede le funzioni esistenti `compose_verified`, `pulse_ai_newsroom`, `update_observer_daily`; gli ancoraggi non validi impediscono la modifica.
- Niente nuove dipendenze di runtime, Python 3.11+.
- Non cambia `published_at`, URL della fonte né ID degli articoli.
- Il metadata `editorial_evidence_ledger` nasce da serie già filtrate dal motore: **non costituisce una seconda verifica indipendente dei documenti**. Sono necessari sia dati ufficiali contestualizzati sia controllo semantico/revisione prima dell'approvazione.
- La bozza AI è separata da `articles.json`, e non viene salvata su `ISTAT-PULSE-DATA` (repo pubblico).
- Lo standard completo di generazione 250–400 parole **non può essere garantito se le fonti non contengono una serie verificata o se non è configurato un LLM**: niente testi finti per raggiungere una quota di parole.

## Test e risultati sul backup

- 8 test di regressione locale passati: tre casi originali, idempotenza, fonte e data invarianti, ledger tipizzato, bozza non pubblicata, rifiuto fonte non valida.
- Sweep su snapshot storico: **5.859** record Osservatori, **2.419** fallback standard convertibili in schede fonte, **26** record con coda di titoli estranei riconosciuta con soglia conservativa. 210 record Radar, **14** sintesi numeriche non contestualizzate convertibili in schede. Sono conteggi del backup del 23 ottobre 2026, **non** dello stato attuale su GitHub.
- Test da eseguire contro il backend attuale: `python -m unittest discover -s tests -p test_editorial_recovery_guard.py -v`; poi i test CI già presenti in PULSE-DATA e una verifica in anteprima prima del merge.

## Installazione e pubblicazione controllata

1. Eseguire `INSTALLA_PULSE_EDITORIALE.bat`: clona il DATA attuale in una cartella separata, crea il ramo locale `feat/editorial-recovery-20261109`, copia gli script e avvia i test. **Non esegue alcun push**.
2. Ispezionare il risultato e il report in console.
3. Solo quando soddisfatti, eseguire `CARICA_RAMO_TEST_GITHUB.bat`: il programma chiede conferma e pubblica solo il ramo di collaudo, **non main**. Le CI di test potrebbero partire sul ramo, ma nessun workflow di pubblicazione dati viene attivato da questa operazione.
4. Eseguire la CI completa e una verifica dei tre casi, poi valutare l'eventuale merge su `main`. Il merge potrebbe influenzare le notizie alla prossima esecuzione schedulata; per questo non è automatico.
5. Le bozze AI private richiedono `PULSE_LLM_ENDPOINT` e `PULSE_LLM_MODEL`; si generano con `GENERA_BOZZA_AI_PRIVATA.bat` in `Documenti\PULSE_BOZZE_PRIVATE`, fuori dal repository. Nessuna garanzia di approvazione o pubblicazione automatica.

## Limiti reali

Questo rilascio **non trasforma automaticamente schede povere in articoli eccellenti**. Prima blocca le forme di bassa qualità provate; conserva la generazione deterministica basata su serie valide; infine prepara le bozze AI per revisione sicura. Un motore longform automatico con controlli semantici e approvazione richiede ulteriore integrazione e collaudo end-to-end su fonti web reali. Un corpus storico non prova che il comportamento live sia identico.
