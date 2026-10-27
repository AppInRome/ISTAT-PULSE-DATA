# ISTAT PULSE - dossier di continuita' - 27 ottobre 2026

Fonte per i dati: repository AppInRome/ISTAT-PULSE-DATA, letto il 27 ottobre 2026.

## DOSSIER DI CONTINUITA'

> Situazione del progetto Android, repository dati, automazioni e interventi richiesti.

> Data del dossier: 27 ottobre 2026. Questo riepilogo raccoglie i risultati verificati su GitHub e le anomalie segnalate dall'utente nelle schermate Android. Non equivale a un collaudo dell'APK.

### Fotografia del motore dati

> NOTIZIE | 39 contenuti OGGI; 33 IERI. OGGI: 35 segnalazioni stampa e 4 analisi PULSE verificate. IERI: 31 segnalazioni stampa e 2 contenuti verificati.

> COPERTURA | 73 feed RSS configurati, 72 raggiunti nell'ultima raccolta; 65 produttori istituzionali censiti e 80 domini ufficiali riconosciuti.

> GREEN | 19 fonti monitorate, 16 con eventi acquisiti e 428 eventi validati; ultimo controllo del 27 ottobre riuscito, nessun nuovo evento nell'ultimo passaggio.

> TERRITORI | 21 serie validate, 5 riacquisite e 16 conservate dalla cache ufficiale nell'ultimo aggiornamento riuscito; archivio da 51.825 osservazioni.

### Problema principale rimasto

> Il motore remoto sta raccogliendo dati e notizie, ma le schermate Android Green, Territorio, Top Italia e Notizie positive mostrano date e volumi non coerenti con gli indici online. La priorita' e' distinguere aggiornamento del server, pubblicazione giornalistica e periodo statistico, poi collegare correttamente gli indici alle interfacce.

> REGOLA DI LAVORO: non confondere codice pubblicato su GitHub, workflow riuscito, sorgenti Android compilabili e APK davvero testata sul telefono. Sono quattro verifiche differenti.

## 1. PROGETTO E REPOSITORY

### Due componenti, da non confondere

- Android: ISTAT PULSE e' l'app con le schermate Notizie, Green, Territori, Pubblicazioni, Top Italia e Notizie positive. La versione-base recuperata e' PULSE 4.5.13.

- Backend: repository GitHub AppInRome/ISTAT-PULSE-DATA, ramo main. Ospita i dati, i radar RSS, gli indici editoriali, i processi SDMX/API, i test e i workflow automatici. Non e' il repository completo dell'app Android.

### Indirizzi fondamentali

`https://github.com/AppInRome/ISTAT-PULSE-DATA`

`https://github.com/AppInRome/ISTAT-PULSE-DATA/actions`

`https://github.com/AppInRome/ISTAT-PULSE-DATA/tree/main/data`

### File essenziali

- data/news/articles.json: archivio editorializzato; data/news/index.json: categorie OGGI, IERI e ARCHIVIO.

- data/news/green_index.json e data/news/territori_index.json: raccolte tematiche gia' pubblicate dal backend, da mostrare nelle rispettive schermate.

- data/pulse_green_status.json: fonti e ultimo controllo Green; data/refresh_status.json e data/live_data_index.json: salute del sistema e percorsi ai dati.

- data/pulse_events.tsv, data/pulse_observations.tsv, data/pulse_observations_manifest.json: segnali e osservazioni statistiche.

- data/news/observer_articles.json e data/observer_refresh_status.json: catalogo Pubblicazioni e sorgenti dirette.

- data/news_radar_sources.json: 73 feed, produttori e domini monitorati.

### Separazione importante

> I nuovi JSON sul repository non aggiornano automaticamente il codice gia' installato sul telefono. Se l'app mantiene cache, URL hardcoded, filtri vecchi o layout statici, puo' continuare a mostrare informazioni obsolete nonostante GitHub abbia dati recenti.

## 2. AUTOMAZIONI E STATO REALE

### Workflow automatico

`.github/workflows/pulse-data-daily.yml`

- Notizie e Pubblicazioni: ogni tre ore, otto scansioni al giorno, programmate in UTC alle 02:17, 05:17, 08:17, 11:17, 14:17, 17:17, 20:17 e 23:17. GitHub Actions puo' ritardare le esecuzioni.

- Green e Territori: acquisizione completa delle API due volte al giorno, alle 05:17 e 17:17 UTC; gli altri passaggi danno priorita' alle notizie.

- Workflow di test separato: verifica sintassi, fonte primaria, notizie giornalistiche attribuite, grafici e tabelle, gestione SDMX e duplicati. Ultimi test automatici indicati come riusciti.

### Snapshot verificato sul repository

> Notiziario: 341 articoli totali; 39 OGGI, 33 IERI. Sono visibili anche articoli in revisione; il numero totale non significa 341 notizie verificate.

> Qualita' di OGGI: 4 articoli con grafico verificato; 35 segnalazioni della stampa senza convalida primaria completa.

> Qualita' di IERI: 2 contenuti verificati; 31 segnalazioni della stampa.

> Green tematico: indice con 8 OGGI, 3 IERI e 2 ARCHIVIO. Territori tematico: 14 OGGI, 9 IERI e 15 ARCHIVIO.

### Date dell'ultimo ciclo controllato

- Green: ultimo successo 27/10/2026 ore 17:54 UTC; 19 fonti, 16 con eventi, 428 eventi validati. Nell'ultimo ciclo: zero eventi nuovi.

- Territori: ultimo successo 27/10/2026 ore 17:55 UTC; 5 serie aggiornate nel passaggio, 16 in fallback e 51.825 osservazioni conservate.

- Pubblicazioni: 5.863 elementi nel catalogo; ultimo controllo 27/10/2026 ore 17:55 UTC, zero novita' aggiunte nel passaggio, tre feed diretti su quattro raggiunti.

> ATTENZIONE: un esito 'ok' del controllo non dimostra che l'anno statistico 2026 sia disponibile per ciascun indicatore.

## 3. REDAZIONE STATISTICA

### Obiettivo concordato

> PULSE deve scoprire notizie statistiche italiane continuamente, non limitarsi agli aggiornamenti ISTAT. Fonti di scoperta: giornali nazionali, economici, agenzie, specializzati, testate locali e Google News. Per ogni notizia trovare, quando possibile, il documento originale, verificare il numero e scrivere un articolo PULSE autonomo.

### Elenco sorgenti proposto dall'utente

> 20 quotidiani e testate economiche: Il Sole 24 Ore, Corriere della Sera, la Repubblica, La Stampa, Il Fatto Quotidiano, Il Messaggero, Il Giornale, Il Tempo, Libero, Il Foglio, Avvenire, Il Manifesto, Domani, Il Riformista, Quotidiano Nazionale, ItaliaOggi, Milano Finanza, Wall Street Italia, Investire Magazine, La Verita'.

> 15 agenzie: ANSA, AGI, Adnkronos, Askanews, LaPresse, Italpress, Dire, Radiocor, Teleborsa, MF Newswires, Agenzia Nova, 9Colonne, Agenparl, Labitalia e GEA.

> 25 specializzate: Lavoce.info, Openpolis, Pagella Politica, Facta, Sky TG24, RaiNews, TGcom24, Fanpage, Today, Open, Money.it, QuiFinanza, Formiche, Startmag, Wired Italia, Agenda Digitale, GreenMe, QualEnergia, Altreconomia, Il Post, Valigia Blu, Scienza in Rete, Sanita' Informazione, Quotidiano Sanita', Tecnica della Scuola.

> Quotidiani locali: Il Mattino, Il Gazzettino, Il Giorno, Il Resto del Carlino, La Nazione, Il Secolo XIX, Il Piccolo, Messaggero Veneto, L'Arena, Bresciaoggi, L'Eco di Bergamo, Giornale di Brescia, Gazzetta del Mezzogiorno, La Sicilia, Giornale di Sicilia, Quotidiano di Puglia, La Nuova Sardegna, L'Unione Sarda, Corriere dell'Umbria e Il Centro.

### Due livelli editoriali obbligatori

- Segnalazione stampa: testata, data, titolo, territorio, link e numeri attribuiti al giornale. Avviso esplicito che il dato non e' ancora verificato; niente grafici inventati.

- Analisi PULSE verificata: fonte primaria puntuale, valore, unita', indicatore, periodo, testo originale, tabella e grafico soltanto quando i numeri sono confrontabili.

> I 73 feed configurati non dimostrano che tutte le ~80 testate siano monitorate singolarmente. La copertura reale va censita testata per testata, con data dell'ultimo successo e numero di articoli scoperti.

## 4. GREEN: PROBLEMI DA RISOLVERE

### Richiesta grafica esplicita

- Togliere dalla scheda GREEN il blocco duplicato 'Ultime pubblicazioni ufficiali', incluso nel raggruppamento con Pubblicazioni Green, Territorio e Notizie positive. Non eliminare l'archivio Pubblicazioni generale.

- Dopo la rimozione, rialzare tutte le sezioni successive: niente spazio vuoto, rientri inutili o schede enormi.

### Problema della data di aggiornamento

- Il telefono segnala aggiornamento fermo al 23 ottobre, mentre il backend Green e' stato controllato con successo il 27 ottobre alle 17:54 UTC.

- Verificare l'URL dell'app, il refresh manuale e periodico, il file letto, cache e timestamp. Mostrare distintamente 'ultimo controllo API', 'ultima pubblicazione' e 'periodo statistico'. Non etichettare l'anno dei dati come data di aggiornamento.

### Integrazione delle news attuali

- L'indice remoto data/news/green_index.json contiene 8 notizie OGGI e 3 IERI nell'ultimo snapshot: la schermata Green deve leggerlo e visualizzarlo, separando notizie stampa e analisi verificata.

- Non basta aggiornare soltanto il database numerico 428 eventi: Green ha bisogno anche del flusso editoriale 26-27 ottobre su ambiente, energia, consumo di suolo, mobilita', clima e rifiuti.

### Criterio di accettazione

> Al prossimo controllo Green deve mostrare il timestamp reale della sincronizzazione, dati storici con il loro anno esplicito, articoli nuovi con data di pubblicazione e nessuna duplicazione del blocco eliminato.

## 5. TERRITORIO GREEN E API

### Anomalia osservata dall'utente

> Nella sottoscheda Territorio di Green le ultime notizie apparivano ferme a settembre 2026 e i dati erano del 2025. Il problema va analizzato su due livelli: recuperare pubblicazioni 2026 pertinenti e non falsificare il periodo di serie statistiche la cui ultima osservazione ufficiale e' davvero 2025.

### Cosa e' gia' disponibile sul server

> data/news/territori_index.json: 14 notizie OGGI, 9 IERI, 15 ARCHIVIO; quindi il backend ha notizie territoriali molto piu' recenti di settembre.

> SDMX: 21 serie validate, 5 riacquisite nell'ultimo controllo del 27 ottobre e 16 mantenute dalla cache ufficiale. Archivio storico da 51.825 osservazioni.

### Cosa verificare nell'app

- Lettura dell'indice territoriale remoto (non di un vecchio file locale confezionato nell'APK). Eliminare l'eventuale filtro che mostra solo pubblicazioni con grafico verificato.

- Disambiguare le date: 'pubblicata il 27/10/2026' puo' riferirsi a uno studio sul 2025, senza che il dato sia sbagliato. E' sbagliato farlo passare per osservazione 2026.

- Verificare che la richiesta SDMX e i fallback siano riportati con trasparenza. Il successo della pipeline non implica 21 acquisizioni aggiornate: 16 erano in fallback.

- Collegare filtro geografico e categorie coerenti con regioni, province e comuni; evitare articoli generici senza legame territoriale.

### Criterio di accettazione

> Notizie territoriali di OGGI/IERI visibili in Green; visualizzazione differenziata di periodo statistico, data pubblicazione e ultima lettura delle API; vecchi dati non nascosti ma correttamente etichettati.

## 6. TOP ITALIA E NOTIZIE POSITIVE

### Top Italia: situazione osservata

> L'utente vede soltanto sei notizie Top Italia datate dal 7 al 22 ottobre 2026. Questo e' un rilievo della UI, non un conteggio validato su un ranking backend. Va controllato come vengono selezionati, ordinati e conservati i Top: fonte, soglie, punteggio, filtri e limite statico a sei.

### Top 6: modifiche richieste

- Aggiungere una piccola icona/immagine professionale e riconoscibile per ciascun macroargomento, non una grande illustrazione che dilata le schede.

- Categorie da coprire: clima e decarbonizzazione; energia e rinnovabili; economia circolare; acqua e suolo; natura e biodiversita'; mobilita' sostenibile. Se esistono altre categorie, mantenere coerenza di stile.

- Organizzare Top Italia per ANNO e MESE, non avere una lista fissa tutta a ottobre. Prevedere anche il filtro settimanale e un archivio storico.

- Un 'Top 6' puo' mostrare le sei notizie migliori del periodo scelto, ma non deve limitare a sei tutto il patrimonio editoriale; serve 'vedi tutte'.

### Notizie positive

> L'utente osserva due notizie della settimana e sei del mese. La quantita' e' plausibilmente insufficiente, ma prima di aumentarla va verificato che il sistema non scarti report positivi solo per assenza di un grafico immediato.

- Fare ranking separati per settimana, mese, anno, territorio e tema. Periodi e numero di contenuti devono essere reali, non hardcoded nell'interfaccia.

- Definire un criterio positivo verificabile: progresso anno su anno, riduzione di un fenomeno negativo, superamento di un benchmark, recupero ambientale o miglioramento documentato.

- Distinguere contenuti stampa in attesa di verifica dai risultati ufficiali: una dichiarazione ottimistica o una previsione non e' di per se' una notizia statistica positiva.

### Criterio di accettazione

> Filtri anno/mese/settimana operativi, sei immagini piccole e leggibili nei Top, volumi dinamici e nessun duplicato. Le date devono riflettere la pubblicazione, non il momento del crawl.

## 7. PUBBLICAZIONI E FONDI DATI

### Catalogo Pubblicazioni

> Ultimo archivio: 5.863 pubblicazioni indicizzate; quattro feed diretti, tre raggiunti (CNR, SVIMEZ, SINAB) e uno bloccato (CNA: HTTP 403). Ultimo controllo senza nuove acquisizioni.

> Il catalogo numeroso non dimostra che ogni ente importante pubblichi oggi su PULSE. Il censimento di 65 produttori non equivale a 65 feed documentali direttamente connessi.

### Esempi di fonti primarie da ricondurre agli articoli

> ISTAT, Eurostat, Banca d'Italia, INPS, INAIL, Unioncamere, MEF, Ragioneria generale, Censis, Caritas, Fondazione Migrantes, Save the Children, ISS, ISPRA, SNPA, ENEA, GSE, ARERA, ACI, OMI, Terna, Coldiretti, Confcommercio, Confartigianato, Nomisma, CRIF e altri.

### Come deve funzionare

- Ogni articolo candidato conserva URL della scoperta, nome della testata, data esatta, fonte primaria, anno o trimestre statistico, territorio, misura e stato della verifica.

- Una fonte con accesso bloccato non deve fermare tutto il refresh: si registra l'errore, si conservano gli ultimi contenuti validi e si cerca un'alternativa ufficiale consentita.

- L'app non deve ripubblicare integralmente contenuti protetti dei giornali: i testi PULSE devono essere originali, con link e attribuzione della scoperta.

### Avvertenza tecnica

> Per immagini, grafici, PDF, CSV e API e' indispensabile distinguere integrita' del download, metadati, periodo della tabella e licenze. Mai inventare un andamento da un solo valore.

## 8. SEI INTERVENTI PRIORITARI

### Backlog concordato, da eseguire senza cambiare il resto

- P1 - GREEN: rimuovere 'Ultime pubblicazioni ufficiali', recuperare subito lo spazio verticale e riordinare la schermata.

- P2 - SINCRONIZZAZIONE: verificare URL, cache, timestamp e aggiornamento dell'app. Mostrare il corretto ultimo controllo API distinto dal periodo dei dati.

- P3 - INDICI TEMATICI: collegare data/news/green_index.json e data/news/territori_index.json alle due schermate Android, conservando fonte e date.

- P4 - RANKING: progettare e pubblicare classifiche backend per Top Italia e Notizie positive, con periodo settimana/mese/anno e punteggi riproducibili.

- P5 - DUE LIVELLI: distinguere le segnalazioni stampa dalle analisi verificate; i soli numeri con fonte primaria affidabile autorizzano grafici e tabelle.

- P6 - COLLAUDO: verificare materialmente tutte le schede su emulatori o telefono, con screenshot, date, conteggi, duplicati, dimensioni delle icone e assenza di spazi vuoti.

### Ulteriori richieste esplicite

- Top 6: icone piccole e realistiche/professionali per tema; storico selezionabile per anno e mese.

- Notizie positive: verificare l'apparente scarsita' (2 settimana, 6 mese) e recuperare le notizie verificabili dalle fonti nazionali e locali.

- Territorio in Green: eliminare l'apparenza di notizie ferme a settembre; valorizzare le notizie pubblicate nel 2026 senza alterare gli anni dei dataset.

### Ordine raccomandato

> 1) Ispezione sorgenti Android e mapping URL; 2) correzione flussi e date; 3) ranking backend e contratti JSON; 4) interfaccia e icone; 5) test end-to-end; 6) compilazione e archivio finale soltanto quando richiesto.

## 9. SORGENTI WINDOWS, BAT E RAR

### Base Android recuperata

> File disponibile nella Libreria dei file ChatGPT: PULSE_4.5.13_APPINROME_CORRETTA_COMPLETA_WINDOWS.zip (circa 161 MB). Include il progetto Android completo per Windows secondo l'archivio recuperato, ma il suo contenuto non e' stato ricollaudato in questa sessione.

> Patch separata gia' presente: PULSE_4513_CORREZIONI_SOLO_SORGENTI_NO_APK.zip (circa 36 KB). Contiene modifiche Kotlin per leggere notizie e dati remoti; l'integrazione e la compilazione completa vanno verificate.

### Script Windows su GitHub

`tools/windows/COMPILA_APK.bat`

`tools/windows/CREA_RAR_PULSE.bat`

> COMPILA_APK.bat richiede gradlew.bat, gradle/wrapper/gradle-wrapper.jar, sorgenti app Android, JDK e Android SDK; esegue :app:assembleDebug e copia il risultato in APK_GENERATA. CREA_RAR_PULSE.bat richiede WinRAR e una cartella radice Android completa.

> Non e' mai stato consegnato un archivio RAR completo e collaudato in questa conversazione. I BAT esistono come file separati nel repository dati, ma non sostituiscono da soli i sorgenti Android.

### Prossimo confezionamento corretto

- Recuperare 4.5.13, integrare patch e ultime modifiche UI dopo il collaudo, verificare compilazione Gradle senza errori e includere BAT nella radice del progetto.

- Generare archivio RAR verificato su Windows (o ZIP se RAR non disponibile), con README, versione, changelog, istruzioni e checksum. Escludere chiavi private, token, .env, keystore e build temporanee.

- Un'APK debug compilata localmente non equivale a un'APK release firmata; custodire le chiavi di firma separatamente.

## 10. TESTO PER LA NUOVA CHAT

> Incollare il seguente incarico e allegare questo PDF:

> Stiamo lavorando all'app Android ISTAT PULSE, versione sorgente 4.5.13, e al repository GitHub AppInRome/ISTAT-PULSE-DATA. Leggi questo dossier prima di intervenire e verifica sul repository lo stato piu' recente.

> Obiettivi principali: correggere in Green la sezione duplicata 'Ultime pubblicazioni ufficiali' e risalire il layout; risolvere data e cache non aggiornate; integrare indici OGGI/IERI di Green e Territori; riqualificare Top Italia e Notizie positive con filtri per settimana/mese/anno e icone piccole dei 6 temi; rendere le fonti statistiche e i periodi trasparenti.

> Verifica le notizie realmente disponibili in data/news, le 73 fonti RSS (non tutte individualmente verificate), 19 sorgenti Green e il fallback territoriale SDMX; confrontale con quanto visualizza il telefono. Se trovi regressioni non aggiungere nuove funzionalita' prima di ripararle.

> Non dichiarare completata una modifica solo perche' e' presente su GitHub. Effettua test automatici e poi controlli Android sul dispositivo/emulatore. Conserva dati validati, citazioni e licenze. Prima di generare APK o RAR verifica esplicitamente le istruzioni dell'utente nella nuova chat.

### Documentazione di riferimento

`https://github.com/AppInRome/ISTAT-PULSE-DATA`

`data/refresh_status.json; data/news/index.json; data/news/green_index.json`

`data/news/territori_index.json; data/pulse_green_status.json`

`data/live_data_index.json; .github/workflows/pulse-data-daily.yml`

### Criterio di successo finale

> Una PULSE che non mostri date di aggiornamento false, usi fonti italiane ampie, abbia schede Green e Territorio recenti, classifica Top Italia navigabile per anno/mese, notizie positive pertinenti, immagini coerenti e layout compatto. APK e RAR solo dopo validazione del progetto.
