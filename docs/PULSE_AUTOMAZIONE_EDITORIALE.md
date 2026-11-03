# PULSE – filiera editoriale automatica permanente

La funzione è parte del normale refresh delle notizie: non si avvia manualmente
per ogni articolo e non richiede una nuova APK. Il codice è in
`scripts/update_news_radar.py`, `scripts/pulse_auto_promotion.py`,
`scripts/pulse_primary_research.py`, `scripts/pulse_original_editorial.py`.

## Dalla notizia al pezzo quantitativo

1. I feed RSS individuano una notizia con data e titolo della testata.
2. Viene registrata come **segnalazione stampa** attribuita. I numeri RSS
   non sono ancora presentati come osservazioni statistiche indipendenti.
3. Ogni refresh prende un piccolo gruppo di segnalazioni ancora da verificare
   (due per esecuzione, per rispettare le quote gratuite e i timeout). Le
   segnalazioni non processate restano in coda per i cicli successivi; una
   ricerca fallita viene ritentata dopo 36 ore.
4. Si cercano pubblicazioni specifiche su domini istituzionali configurati,
   con tentativi limitati, download circoscritti, tabelle HTML/CSV/Excel/PDF
   e allegati omogenei. Ricerca e download sono separati da pubblicazione.
5. La promozione automatica è possibile soltanto quando la tabella originale
   ha indicatore, periodi e unità espliciti, almeno due osservazioni,
   localizzazione della riga, SHA256 del documento e un numero del titolo
   o dell'estratto che coincide con un valore ufficiale. Anche indicatore,
   eventuali anni citati e unità percentuale devono essere compatibili.
6. Il controllo di qualità editoriale respinge testi ripetitivi, prefabbricati, troppo brevi o senza riferimenti numerici al grafico.
7. Da questi **stessi valori** vengono generati titolo e analisi originale
   basata sui confronti, grafico e tabella. Le fonti rimangono consultabili,
   con una distinzione esplicita tra verifica strutturale automatica e
   revisione editoriale umana.
8. Si mantiene l'ID e la data della notizia, senza ricreare artificialmente
   la notizia in OGGI. Se manca una verifica, rimane un breve di stampa
   attribuito, senza grafici o tabelle inventati.
9. I reportage scritti e approvati individualmente prevalgono sempre
   sulle analisi automatiche; la comparsa di un RSS non cancella i pezzi
   già verificati.

## Che cosa NON promette il sistema

- La verifica strutturale di due celle e di un titolo **non equivale**
  a un fact-check giornalistico completo o a un'inchiesta originale.
- Alcune notizie non avranno serie quantitative confrontabili e resteranno
  segnalazioni documentate; non si producono grafici fittizi.
- Una corrispondenza numerica ambigua, un formato non supportato o un
  documento inaccessibile non provocano la promozione.
- Il limite di due ricerche a refresh non garantisce la verifica immediata
  di ogni nuova segnalazione: è una coda permanente con risorse limitate.
- Per articoli interpretativi complessi, la redazione manuale rimane
  il livello qualitativo superiore. Non vengono simulate firme o
  approvazioni umane.

## Controlli

```bash
python -m unittest discover -s tests -p test_auto_promotion.py -v
python -m unittest discover -s tests -p test_original_editorial.py -v
python scripts/refresh_daily_safe.py --mode news
```

Il report `data/news/editorial_quality_status.json` contiene
`automatic_primary_research`: tentativi, promozioni e coda del ciclo.
La ricerca è persistente nei singoli articoli attraverso i campi
`primary_research_last_attempt_at` e `primary_research_status`.
