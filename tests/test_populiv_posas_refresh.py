import importlib.util,io,json,tempfile,unittest
from pathlib import Path
path=Path(__file__).resolve().parents[1]/"scripts"/"populiv_posas_refresh.py"
spec=importlib.util.spec_from_file_location("populiv_posas_refresh",path)
p=importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class PopulivPosasTests(unittest.TestCase):
    def test_reject_incomplete_source(self):
        import zipfile
        data=b"ISTAT\nCodice comune;Et\xc3\xa0;Maschi;Femmine\n001001;0;40;40\n"
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w") as z:z.writestr("comuni.csv",data)
        reg=("Codice Comune formato alfanumerico;Codice Regione\n"+
             "".join(f"{i:06d};01\n" for i in range(7001))).encode()
        with self.assertRaises(ValueError):
            p.from_istat(2026,b.getvalue(),reg,
                "https://demo.istat.it/data/posas/POSAS_2026_it_Comuni.zip")
    def test_downgrade_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            old=p.OUTPUT
            try:
                p.OUTPUT=Path(tmp)
                (p.OUTPUT/"manifest.json").write_text('{"reference_year":2027,"sha256":"x"}')
                with self.assertRaises(ValueError):
                    p.publish({"reference_year":2026,"observations":[]})
            finally:
                p.OUTPUT=old

if __name__=="__main__":unittest.main()
