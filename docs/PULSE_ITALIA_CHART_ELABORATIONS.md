# PULSE Italia — elaborazioni automatiche dei grafici

I calcoli statistici sono implementati nel codice Python
\`scripts/pulse_italia_chart_analytics.py\` ed esposti in:
- \`scripts/pulse_italia_auto_pipeline.py\` nel file di anteprima \`preview.json\`;
- \`scripts/pulse_editorial_engine_v1.py\` nei soli articoli approvati e pubblicati, campo \`chart_analyses\`;
- PULSE Android LAB 0.8: scelta delle viste sopra il grafico nel lettore Notizie. L'app calcola nuovamente le elaborazioni dai propri valori originali verificati.

## Sei viste, senza inventare dati

| Modalità | Calcolo | Quando è ammessa |
|---|---|---|
| Valori ufficiali | valore nella tabella originale | Solo osservazioni effettivamente estratte da fonti ufficiali |
| Differenza | valore(t) − valore(t−1) | Periodi effettivamente consecutivi; per tassi percentuali è in **punti percentuali** |
| Variazione relativa | (valore(t) − valore(t−1))/abs(valore(t−1)) × 100 | Periodi consecutivi, valore precedente diverso da zero |
| Indice base 100 | valore(t) / primo valore × 100 | Primo valore osservato diverso da zero |
| Media mobile 3 | media aritmetica di tre osservazioni consecutive | Nessun salto o periodo mancante nella finestra |
| Variazione su anno precedente | valore(t) − valore(stesso mese/trimestre un anno prima) | Esistono entrambe le osservazioni, stessa serie e classificazioni |

Nessun riempimento di lacune, stima, regressione, interpolazione o previsione.
Una variazione relativa **non** si confonde mai con una differenza di punti percentuali.

Tutte le viste registrano l'elenco preciso dei periodi usati
(\`based_on\`), il nome della formula e \`kind=calculated\`.
L'unica serie indicata come \`kind=observed\` è quella originale.
L'app mostra due colonne distinte: valore **UFFICIALE** e valore
**ELABORATO** da PULSE, e indica quando un calcolo non è possibile.

\`scripts/pulse_italia_reviewed_publish.py\` verifica che ogni
\`chart_analyses\` venga ricalcolato correttamente dalla stessa serie
ufficiale usata dal grafico/tabella: eventuali alterazioni vengono
rifiutate.

## Controlli

\`tests/test_pulse_italia_chart_analytics.py\`: unità, differenze, periodo mancante, base zero, confronti esatti mese/anno e trimestre/anno.

\`tests/test_pulse_italia_reviewed_publish.py\`: valori grafici e tabelle identici, rifiuto di elaborazioni manomesse e mantenimento degli articoli nel feed tra aggiornamenti.

PULSE LAB 0.8 contiene \`PulseChartCalculations.kt\`, il selettore delle elaborazioni e i test di logica numerica Kotlin. La compilazione APK richiede Windows/JDK/Android SDK e il BAT allegato.

## Limite editoriale

La matematica di PULSE può descrivere un andamento; **non può attribuire
automaticamente cause, previsioni o spiegazioni economiche/sanitarie**.
La redazione AI deve continuare a usare soltanto numeri auditati e una
revisione editoriale umana, senza pubblicazione autonoma.
