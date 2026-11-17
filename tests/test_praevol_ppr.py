import unittest,tempfile,zipfile,io,copy
from pathlib import Path
from scripts import praevol_ppr_refresh as mod

class PraevolPprTests(unittest.TestCase):
    def test_median_column_exact_and_age_aggregation(self):
        header='Anno;Sesso;Età;Scenario mediano;Altro'
        rows=['"Previsioni regionali della popolazione residente - base 1.1.2025 - Anni 2025/2080"',
              '"Regione: Lazio"',header]
        for yr in range(2025,2051):
            for sex in ('Maschi','Femmine'):
                for age in range(101):rows.append(f'{yr};{sex};{age};10;999')
        values=mod.csv_records(('\n'.join(rows)+'\n').encode(),2025)
        self.assertEqual((50,50),tuple(values[2025,0]))
        self.assertEqual((60,60),tuple(values[2025,19]))
        with self.assertRaises(ValueError):
            mod.csv_records(('\n'.join(rows)+'\n').encode(),2026)
    def test_missing_age_fails_closed(self):
        rows=['"Previsioni regionali - base 1.1.2025 - Anni 2025/2080"',
              '"Regione: Lazio"','Anno;Sesso;Età;Scenario mediano','2025;Maschi;0;100']
        with self.assertRaises(ValueError):mod.csv_records(('\n'.join(rows)+'\n').encode(),2025)
    def test_source_base_and_download_list_required(self):
        page=b'<h2>Base 1/1/2025</h2> Previsioni-Popolazione_per_eta-Regioni.zip Previsioni-Popolazione_per_eta-Ripartizioni.zip'
        self.assertEqual(2025,mod.base_year(page))
        with self.assertRaises(ValueError):mod.base_year(b'<h2>Base 1/1/2025</h2>')
if __name__=='__main__':unittest.main()
