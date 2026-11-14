# PULSE Italia — Llama su Cloudflare (senza Tommy AI)

## Stato al 13 novembre 2026
- Implementazione sul ramo di lavoro PR #11, NON pubblicata e NON collegata al vecchio Worker.
- L'app PULSE Android LAB 0.6 legge il feed degli articoli approvati; il modello gira **su Cloudflare**, non sul telefono.
- Stack testato: Data Analyst Agent, dstory, Data2Story Inspector, usando soltanto dati sintetici etichettati come tali.
- Mancano: un token Workers AI, manifest di dataset italiani verificati e un collaudo reale di generazione prima di attivare la pubblicazione.

## Che cosa deve fare l'utente una volta sola

1. Aprire https://dash.cloudflare.com e andare in **Workers AI → Use REST API → Create a Workers AI API Token**. È sufficiente un token con accesso all'inferenza AI: non concedere permessi per modificare i vecchi Worker o i database. **Non inviare mai il token in chat.**
2. In GitHub, repository AppInRome/ISTAT-PULSE-DATA → Settings → Secrets and variables → Actions, creare il **secret** PULSE_CF_AI_TOKEN contenente quel token.
3. Nello stesso menu, nella scheda **Variables**, creare PULSE_CF_ACCOUNT_ID con l'Account ID indicato nel pannello Workers AI di Cloudflare.

Finché non sono presenti **entrambi**, il programma non invia chiamate AI. Nessun pagamento obbligatorio è richiesto se si resta nelle quote gratuite, ma il consumo deve essere monitorato.

## Configurazione predisposta da PULSE

- Modello Llama ospitato su Cloudflare: @cf/meta/llama-3.3-70b-instruct-fp8-fast.
- API ufficiale: https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1/chat/completions.
- Output massimo per chiamata: 1.400 token.
- Riserva per un solo ciclo quotidiano: massimo circa 8.200 Neurons stimati (in via prudenziale da lunghezza prompt e output massimo).
- Quota Cloudflare Free: 10.000 Neurons **al giorno e per account**, condivisi con altri progetti, quindi non garantiti interamente per PULSE.
- Il numero di articoli è un obiettivo massimo di **20 candidature al giorno**, non 20 uscite garantite. Le chiamate AI vengono tentate solo su dataset italiani con classificazioni e confronti verificati; altrimenti nessun testo viene inventato.

Il budget è **una stima prima della chiamata**, non una lettura del contatore Cloudflare. Una seconda esecuzione manuale, o l'utilizzo di Workers AI da altri progetti, potrebbe consumare quota ulteriore: controllare il dashboard. Sul piano Free, raggiunti i limiti, le richieste successive vengono respinte.

## Tommy AI

Il Worker pulse-tommy-api e il vecchio database pulse-tommy-db NON sono letti, aggiornati, cancellati, riutilizzati né collegati al nuovo sistema. Questo evita di compromettere un progetto preesistente che non fa più parte di PULSE.

## Consegna redazionale

Le bozze e le fonti vengono pubblicate solo come artifact GitHub di test, mai direttamente nel feed pubblico. L'analisi e i grafici restano utilizzabili anche senza Llama. Il motore controlla cifre, denominatori, unità, periodo e URL di fonte; la revisione umana resta obbligatoria per ogni articolo.

Il workflow cron si attiva solo dopo il merge su main e mantiene la sola funzione di **ricerca e preparazione bozze**, senza autorizzazione a pubblicare su Android.
