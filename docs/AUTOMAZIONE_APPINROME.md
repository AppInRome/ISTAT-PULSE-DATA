# PULSE DATA - automazione giornaliera su AppInRome

Il workflow `.github/workflows/pulse-data-daily.yml`:
- legge le fonti configurate in `data/news_radar_sources.json` (attualmente 17 feed), senza fingere che tutte le 65 fonti editoriali siano gia' integrate;
- cerca e verifica le nuove notizie e ricalcola i contenitori OGGI/IERI/ARCHIVIO con le date reali;
- verifica i connettori numerici per GREEN e le serie ISTAT SDMX per TERRITORI nel controllo della mattina;
- preserva i dati precedenti in caso di errore o acquisizione insufficiente;
- pubblica il registro `data/refresh_status.json` con l'esito di ogni sezione;
- NON compila APK, NON crea artefatti, NON usa la vecchia identita' GitHub.

Orari: 05:17 e 16:17 UTC (ora di Roma +1/+2 a seconda del periodo). GitHub puo' ritardare o saltare le esecuzioni programmate.

**Limiti**: Non tutte le fonti nel catalogo sono connettori attivi e non tutte le serie ufficiali cambiano ogni giorno. La presenza di un controllo non equivale alla pubblicazione di nuovi dati. Gli aggiornamenti dipendono dal corretto funzionamento dei servizi esterni.

**APK**: Le APK precedenti non vengono modificate da questo workflow. Per leggere questi dati, il client Android deve puntare a `https://raw.githubusercontent.com/AppInRome/ISTAT-PULSE-DATA/main/data/` e gestire cache locale e validazione. Restano da verificare i vecchi riferimenti a pierfido89 e a repository editoriali esterni.

In caso di problemi: controllare Actions -> 'PULSE - aggiorna solo dati e notizie' -> ultima esecuzione; leggere `data/refresh_status.json` e i log. Nel progetto GitHub pubblico, i runner standard non prevedono addebiti per minuti; il file non usa `upload-artifact` o cache per evitare l'accumulo che aveva colpito il vecchio profilo.