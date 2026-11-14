# PULSE Italia — redazione automatica e lettore Android LAB 0.6

**Stato:** esperimento su un ramo GitHub e pull request non unita. Nessuna pubblicazione automatica in produzione.

## Riferimento esterno, senza copia di codice

Progetto studiato: https://github.com/AlessioRepetto/automated_press_review

Automated Press Review ha ispirato l'architettura editoriale: raccolta di fonti italiane, raggruppamento delle notizie, priorità, narrazione in italiano con un LLM e report programmati tramite GitHub Actions. **Non sono state copiate parti del suo codice.** Il progetto non ha una licenza di riutilizzo riconoscibile dai metadati consultati. PULSE non è affiliata al progetto esterno.

## Perimetro

**Solo Italia**: articoli che riguardano l'Italia e i suoi territori. Non bastano un testo in italiano o un giornale italiano. Le voci di paese estero esplicito sono escluse. Le fonti quantitative devono essere primarie e italiane (ISTAT, INPS, INAIL, Banca d'Italia, ISPRA, ACI, MEF ecc.). Una notizia giornalistica senza fonte primaria resta una candidatura, non un dato ufficiale.

## Componenti implementati sul ramo

- scripts/pulse_italia_newsroom.py: filtra il perimetro Italia, elimina duplicati per URL e titolo, valuta la priorità, applica un massimo di 20 candidature con bilanciamento tematico e produce una coda JSON;
- scripts/pulse_editorial_engine_v1.py: estrae una serie CSV/JSON classificata dalla fonte primaria, prepara una bozza AI di 15–25 frasi;
- scripts/pulse_editorial_audit_v1.py: verifica indipendente di valori, variazioni, unità e struttura del testo;
- scripts/pulse_italia_newsroom.py draft: genera bozze solo da manifest già verificati collocati in data/editorial_italia/manifests;
- .github/workflows/pulse-italia-newsroom.yml: costruisce la coda e, se configurato, le bozze, salvandole come artifact senza scrivere feed di produzione;
- tests/test_pulse_italia_newsroom.py: prove di geografia, deduplicazione e blocco delle fonti non verificate.

## Prova manuale

Dalla radice del repository:

    python -m unittest discover -s tests -p 'test_pulse_italia_newsroom.py' -v
    python -m unittest discover -s tests -p 'test_editorial_engine_v1.py' -v
    python scripts/pulse_italia_newsroom.py rank --articles data/news/articles.json --output italian_queue.json --limit 20

Per scrivere una bozza è necessario creare prima manifest con URL reali di dataset ufficiali, secondo docs/PULSE_EDITORIAL_ENGINE_V1.md.

    python scripts/pulse_italia_newsroom.py draft --manifests-dir data/editorial_italia/manifests --output-dir editorial_output/drafts --limit 20

## Collegamento sicuro a Cloudflare Llama

Il vecchio Worker Cloudflare `pulse-tommy-api` e il relativo database sono **ritirati dal progetto PULSE**: non usarli, non recuperarne il token, non modificarli e non cancellarli automaticamente. L'integrazione usa **direttamente l'API Workers AI ufficiale**, senza creare un nuovo Worker.

Configurare una sola volta nel repository GitHub, menu **Settings → Secrets and variables → Actions**:

- **Secret** `PULSE_CF_AI_TOKEN`: token Cloudflare nuovo, limitato a Workers AI; non usare `PULSE_CLIENT_TOKEN` né `OPENAI_API_KEY` del Worker dismesso.
- **Variable** `PULSE_CF_ACCOUNT_ID`: identificatore dell'account Cloudflare, non credenziale segreta.

Il modulo `scripts/pulse_cloudflare_llama.py` sceglie autonomamente l'endpoint ufficiale `/ai/v1/chat/completions` e il modello `@cf/meta/llama-3.3-70b-instruct-fp8-fast`. Non serve configurare `PULSE_LLM_ENDPOINT` o `PULSE_LLM_MODEL` a mano. **Non copiare token in chat, codice, APK o commit.**

Solo dopo aver collaudato il token e un dataset reale si può proporre il merge della PR. I workflow GitHub non pubblicano automaticamente articoli; 20 candidature al giorno non equivalgono a 20 articoli verificati.

### Costi e protezioni

Workers AI Free dichiara una quota di 10.000 Neurons/giorno. Un limite locale prenota al massimo 8.200 Neurons per esecuzione programmata, **calcolati per stima** (non è un contatore ufficiale Cloudflare): eventuali consumi da altri servizi dello stesso account o differenze nella tokenizzazione potrebbero esaurire prima la quota. Il modello può rispondere con errore quando la quota gratuita è terminata. Evitare di abilitare un piano a pagamento senza decisione esplicita.

Sorgenti documentali: https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/ e https://developers.cloudflare.com/workers-ai/platform/pricing/.


## Flusso editoriale vincolato

1. Selezione: la notizia italiana entra in coda; non si finge che una cifra di giornale sia verificata.
2. Evidenza: si recupera una serie ufficiale con periodo, popolazione, territorio, unità e definizione.
3. Bozza AI: scrive soltanto dai numeri verificati o rifiuta per evidenza insufficiente.
4. Audit numerico: blocca nuove cifre non supportate, variazioni errate e vecchi paragrafi standard.
5. Approvatore umano: controlla significato e fonte; l'autorizzazione è separata dal modello.
6. Distribuzione: solo una pubblicazione intenzionale di articles.json e index.json consente all'Android di leggere l'articolo verificato.

**20 è un massimo desiderato, non una quota obbligatoria.**

## Android LAB 0.6

L'APK autonomo conserva header VALE e schede Notizie, Territori, Pubblicazioni, Altro. Il lettore applica un controllo di pertinenza Italia alle voci del feed. I testi AI non vengono generati sul telefono; il client scarica le pubblicazioni approvate come nella LAB 0.5.

## Limiti

- Non è un fork o una copia di Automated Press Review: solo un'implementazione originale del flusso.
- Una fase di ricerca automatica del dataset a partire da ogni RSS non è ancora completa.
- Senza API configurata non vengono generate bozze AI.
- Il workflow in un ramo non predefinito non si attiva automaticamente con il solo cron.
- Il processo non esegue push, merge o pubblicazione automatica.
- Revisione umana necessaria per verificare la semantica oltre all'audit dei numeri.
- La grafica Android ha scorrimento dei valori; lo zoom X/Y non è ancora completo.
