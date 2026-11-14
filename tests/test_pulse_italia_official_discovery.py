"""Offline data discovery tests. Every test value is SYNTHETIC, never published."""
import csv
from datetime import date
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import pulse_italia_official_discovery as discover
from scripts import pulse_italia_auto_pipeline as pipeline


INPS_URL = "https://opendata.inps.it/opendata/dataset/files/test-stat.csv"
PACKAGE = {"id": "dati-di-esempio-2026", "title": "Numero pensionati — esempio fittizio",
           "resources": [{"format": "CSV", "url": INPS_URL}]}
CSV = ("Anno;Territorio;Popolazione;Unita_misura;Numero pensionati\n"
       "2023;Italia;Pensionati;numero;100\n"
       "2024;Italia;Pensionati;numero;111\n"
       "2025;Italia;Pensionati;numero;120\n"
       "2025;Francia;Pensionati;numero;999\n").encode()
# XML shape from official SDMX GenericData 2.1 specification.
SDMX = b'''<GenericData xmlns="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message">
  <DataSet><Series><SeriesKey>
    <Value id="FREQ" value="M"/><Value id="REF_AREA" value="IT"/>
    <Value id="DATA_TYPE" value="UNEM_R"/><Value id="SEX" value="9"/>
    <Value id="AGE" value="Y15-74"/>
  </SeriesKey>
    <Obs><ObsDimension value="2026-08"/><ObsValue value="6.1"/></Obs>
    <Obs><ObsDimension value="2026-09"/><ObsValue value="6.3"/></Obs>
    <Obs><ObsDimension value="2026-10"/><ObsValue value="6.2"/></Obs>
  </Series></DataSet>
</GenericData>'''
ISTAT = {"name": "Tasso di disoccupazione", "flow": "151_874_DF_TEST_1",
         "start": "2024", "required": {"FREQ": "M", "REF_AREA": "IT",
                     "DATA_TYPE": "UNEM_R", "SEX": "9", "AGE": "Y15-74"},
         "preferred": {}, "note": "Disoccupati 15-74 anni, totale sesso."}
SDMX_URL = discover.ISTAT_SDMX + "IT1,151_874_DF_TEST_1/all?startPeriod=2024"


class DiscoveryTests(unittest.TestCase):
    def test_reject_host_injection(self):
        self.assertFalse(discover.allow_data_url(
            "https://opendata.inps.it.evil.com/data.csv", "inps.it"))
        self.assertFalse(discover.allow_data_url(
            "http://opendata.inps.it/data.csv", "inps.it"))

    def test_documented_ckan_catalog_chooses_recent_topics(self):
        ids = ["altro-2013", "pensionati-numero-2026", "lavoro-occupati-2025"]
        got = discover.latest_inps_package_ids(catalog=ids)
        self.assertIn("pensionati-numero-2026", got)

    def test_csv_requires_explicit_italian_territory_and_unit(self):
        result = discover.csv_evidences(CSV, PACKAGE, INPS_URL)
        self.assertEqual(len(result), 1)
        ev = result[0]
        self.assertEqual([x["value"] for x in ev["series"]["observations"]],
                         ["100", "111", "120"])
        self.assertEqual(ev["series"]["territory"], "Italia")
        self.assertEqual(ev["source_sha256"], sha256(CSV).hexdigest())
        self.assertEqual([x["source_row"] for x in ev["source_locations"]], [2, 3, 4])
        self.assertNotIn("999", str(ev))

    def test_csv_rejects_ambiguous_units_and_no_italy(self):
        raw = CSV.replace(b"Numero pensionati", b"Importo").replace(
            b"numero", b"unita sconosciuta")
        self.assertEqual(discover.csv_evidences(raw, PACKAGE, INPS_URL), [])
        self.assertEqual(discover.csv_evidences(
            CSV.replace(b"Italia", b"Francia"), PACKAGE, INPS_URL), [])

    def test_inps_source_months_are_compared_not_aggregated(self):
        monthly = ("Anno;Mese;Territorio;Popolazione;Unita_misura;Numero pensionati\n"
                   "2025;10;Italia;Pensionati;numero;100\n"
                   "2025;11;Italia;Pensionati;numero;111\n"
                   "2025;12;Italia;Pensionati;numero;120\n"
                   "2025;12;Francia;Pensionati;numero;900\n").encode()
        data = discover.csv_evidences(monthly, PACKAGE, INPS_URL)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["series"]["frequency"], "Mensile (anno e mese nelle righe)")
        self.assertEqual([x["period"] for x in data[0]["series"]["observations"]],
                         ["2025-10", "2025-11", "2025-12"])
        self.assertEqual([x["value"] for x in data[0]["series"]["observations"]],
                         ["100", "111", "120"])

    def test_inps_regional_monthly_series_is_real_and_not_mistaken_for_national(self):
        csv_rows = (
            "Anno;Mese;Tipo_intervento;Regione;Numero_lavoratori\\n"
            "2025;01;Ordinaria;Abruzzo;123\\n"
            "2025;02;Ordinaria;Abruzzo;124\\n"
            "2025;03;Ordinaria;Abruzzo;121\\n"
            "2025;03;Ordinaria;Lazio;999\\n"
        ).encode()
        series = discover.csv_evidences(csv_rows, PACKAGE, INPS_URL)
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0]["series"]["territory"], "Abruzzo")
        self.assertEqual([p["period"] for p in series[0]["series"]["observations"]],
                         ["2025-01", "2025-02", "2025-03"])
        self.assertEqual([p["value"] for p in series[0]["series"]["observations"]],
                         ["123", "124", "121"])
        self.assertNotIn("999", str(series))

    def test_sdmx_exact_series_match_and_rows(self):
        e = discover.istat_evidence(SDMX, ISTAT, SDMX_URL)
        self.assertIsNotNone(e)
        self.assertEqual([x["period"] for x in e["series"]["observations"]],
                         ["2026-08", "2026-09", "2026-10"])
        self.assertEqual(e["series"]["unit"], "%")
        self.assertEqual(e["source_sha256"], sha256(SDMX).hexdigest())
        self.assertEqual(e["source_locations"][-1]["sdmx_series_key"]["REF_AREA"], "IT")

    def test_sdmx_strict_metadata_and_unit(self):
        wrong = dict(ISTAT, required={**ISTAT["required"], "AGE": "Y65-99"})
        self.assertIsNone(discover.istat_evidence(SDMX, wrong, SDMX_URL))
        unsupported = dict(ISTAT, name="Numero assoluto")
        self.assertIsNone(discover.istat_evidence(SDMX, unsupported, SDMX_URL))

    def test_inps_discovery_uses_ckan_without_manual_manifest(self):
        def get(url, host):
            self.assertIn(host, ("inps.it", "opendata.inps.it"))
            if "package_show" in url:
                return json.dumps({"success": True, "result": PACKAGE}).encode()
            if url == INPS_URL:
                return CSV
            raise ValueError(url)
        found, checks = discover.scan_inps(
            fetch_fn=get, catalog=[PACKAGE["id"]], limit=1)
        self.assertEqual(len(found), 1)
        self.assertTrue(any("found" in c["status"] for c in checks))

    def test_istat_auto_rotates_official_dataflow_without_manifest(self):
        found, checks = discover.scan_istat(
            fetch_fn=lambda url, host: SDMX,
            datasets=[ISTAT], today=date(2026,11,14))
        self.assertEqual(len(found), 1)
        self.assertEqual(checks[0]["status"], "source_series_found")

    def test_visual_preview_exact_same_source_as_table(self):
        e = discover.istat_evidence(SDMX, ISTAT, SDMX_URL)
        preview = pipeline.build_preview(e)
        v1 = preview["chart_spec"]["data"]
        v2 = preview["table_spec"]["rows"]
        self.assertEqual([(x["period"], x["value"]) for x in v1], [tuple(x) for x in v2])
        self.assertEqual(preview["chart_analyses"]["method"],
                         "exact_original_observations_only")
        self.assertTrue(any(v["id"] == "delta"
                            for v in preview["chart_analyses"]["views"]))
        self.assertEqual(preview["publication_status"], "draft")
        self.assertFalse(preview["publishable_without_review"])
        self.assertEqual(
            preview["verified_series"][0]["extraction_method"],
            "sdmx_xml_explicit_series_dimensions")

    def test_pipeline_produces_review_bundle_never_live(self):
        e = discover.istat_evidence(SDMX, ISTAT, SDMX_URL)
        report = {"sources_considered": [{"provider": "ISTAT", "status": "found"}]}
        with tempfile.TemporaryDirectory() as td, patch.object(
            pipeline, "run_data_tools", return_value={
                k: {"status": "completed"} for k in
                ("data_analyst", "dstory", "data2story_inspector")}):
            doc = pipeline.run_pipeline(
                td, discovery_fn=lambda: ([e], report), ai_enabled=False)
            self.assertEqual(doc["candidate_articles"], 1)
            self.assertEqual(doc["published_articles"], 0)
            entry = doc["results"][0]
            path = Path(td)/entry["id"]
            self.assertTrue((path/"preview.json").exists())
            self.assertTrue((path/"review_required.json").exists())
            self.assertFalse((path/"llama_draft.json").exists())
            data = json.loads((path/"preview.json").read_text())
            self.assertEqual(len(data["table_spec"]["rows"]), 3)
            self.assertEqual(len(data["chart_spec"]["data"]), 3)

    def test_non_raw_press_numbers_never_become_evidence(self):
        self.assertEqual(discover.csv_evidences(
            b"Anno;Valore\n2024;10\n2025;11\n", PACKAGE, INPS_URL), [])


if __name__ == "__main__":
    unittest.main()
