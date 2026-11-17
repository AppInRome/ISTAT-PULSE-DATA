"""PROXIMA feed production never accepts incomplete or inconsistent data."""
import importlib.util,io,json,gzip,hashlib,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("proxima_family_refresh",Path(__file__).resolve().parents[1]/"scripts"/"proxima_family_refresh.py")
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class ProximaFamilyTests(unittest.TestCase):
    def test_school_parser_schema_required(self):
        with self.assertRaises(ValueError):
            p.school_rows(("foo,bar\n123,abc\n"*4000).encode(),"SCUANAGRAFESTAT")
    def test_school_parser_official_headers(self):
        rows=["CodiceScuola;DenominazioneScuola;IndirizzoScuola;DescrizioneComune;CAPScuola"]
        rows += [f"RM{i:08d};Scuola {i};Via Roma 1;ROMA;00100" for i in range(10000)]
        self.assertEqual(10000,len(p.school_rows("\n".join(rows).encode(),"SCUANAGRAFESTAT")))
    def test_posas_family_requires_sha_and_region_quadrature(self):
        rows=[]
        for i in range(1,21):
            for age in range(101):
                for sex in ("M","F"):
                    rows.append([2026,"REGIONE",f"{i:02d}","Regione",age,sex,100])
        for age in range(101):
            for sex in ("M","F"):
                rows.append([2026,"ITALIA","00","Italia",age,sex,2000])
        national=404000
        counts={"family":"istat_posas_age_sex","source_url":"https://demo.istat.it/","period":"1 gennaio 2026",
                "reference_year":2026,"national_total":national,"observations":rows}
        gz=gzip.compress(json.dumps(counts).encode())
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            old=p.POPULIV
            try:
                p.POPULIV=Path(t)
                (p.POPULIV/"pack.json.gz").write_bytes(gz)
                (p.POPULIV/"manifest.json").write_text(json.dumps({"filename":"pack.json.gz","sha256":hashlib.sha256(gz).hexdigest()}))
                self.assertEqual(national,p.territorial_document()["national_total"])
                counts["national_total"]=111
                with self.assertRaises(ValueError):p.territorial_document() # unchanged archive; cannot slip bad claims
            finally:p.POPULIV=old

if __name__=="__main__":unittest.main()
