# ISTAT PULSE DATA — AppInRome

Archivio dati e strumenti di produzione **del progetto indipendente ISTAT PULSE**.
Questo repository e' indipendente dal codice Android e non e' un progetto ufficiale ISTAT.

## Origine e stato

Ripristinato **da un backup locale** del precedente progetto `ISTAT-PULSE-DATA`.
Snapshot storico: metadati di generazione datati prevalentemente **23–24 ottobre 2026**.
I file sono una copia di backup, **non sono automaticamente aggiornati oggi**.

- `data/`: dataset e manifest, notizie, misurazioni, segnalazioni e fonti
- `scripts/`: raccolta, verifica e generazione dei file (non eseguita automaticamente)
- `tests/`: controlli preesistenti
- `docs/`: documentazione e nota di provenienza

**Non sono stati copiati** `.git/`, `.github/workflows/`, file di compilazione APK,
chiavi private o gli altri repository annidati nel backup.
Nessuna GitHub Action viene attivata dalla pubblicazione di questo snapshot.

**Attenzione:** il ripristino non configura aggiornamenti automatici. Prima di crearli
servira' validare gli script, le dipendenze, le autorizzazioni e i connettori
che alimentano Notizie, Territori, Green e Pubblicazioni.

Il client Android PULSE deve essere **configurato separatamente** per leggere i nuovi URL
`https://raw.githubusercontent.com/AppInRome/ISTAT-PULSE-DATA/main/data/...`
Non basta creare il repository per aggiornare automaticamente le APK gia' installate.

## Sicurezza e pubblicazione

Prima di pubblicare una copia pubblica, verificare la compatibilita' delle licenze
dei dati di terzi. Non caricare credenziali, token, file `.env`, chiavi, APK o dati privati.
I commit Git usano l'indirizzo GitHub `noreply` dell'account AppInRome.
