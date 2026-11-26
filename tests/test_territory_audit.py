import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import refresh_daily_safe as refresh

class TerritoryAuditTests(unittest.TestCase):
    def test_period_order(self):
        self.assertGreater(refresh.period_key("2026-10"),refresh.period_key("2026-Q2"))
        self.assertGreater(refresh.period_key("2026-Q3"),refresh.period_key("2026-07"))
        self.assertGreater(refresh.period_key("2026-01"),refresh.period_key("2025"))
    def test_manifest_recomputes_and_retains_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            with patch.object(refresh,"DATA",base):
                def event(id_,period,family,scope):
                    row={key:"" for key in refresh.EVENT_FIELDS}
                    row.update(id=id_,period=period,indicator=id_,source_family=family,source_url="https://example.org/data",scope=scope)
                    return row
                refresh.write_tsv(base/"pulse_events.tsv",refresh.EVENT_FIELDS,[
                    event("a","2026-Q2","SDMX","GENERAL"),
                    event("b","2026-10","SDMX","GENERAL"),
                    event("c","2025","ISPRA","GREEN")])
                refresh.refresh_manifest()
                first=json.loads((base/"pulse_manifest.json").read_text())
                self.assertEqual(first["latest_period"],"2026-10")
                self.assertEqual(first["events_by_source"],{"SDMX":2,"ISPRA":1})
                self.assertEqual(first["green_events"],1)
                refresh.refresh_manifest()
                second=json.loads((base/"pulse_manifest.json").read_text())
                self.assertEqual(first["generated_at"],second["generated_at"])
                self.assertEqual(first["feed_sha256"],second["feed_sha256"])
    def test_invalid_observation_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            with patch.object(refresh,"DATA",base):
                row={key:"x" for key in refresh.OBS_FIELDS}
                row["value"]="2"
                refresh.write_tsv(base/"pulse_observations.tsv",refresh.OBS_FIELDS,[row])
                before=(base/"pulse_observations.tsv").read_bytes()
                with self.assertRaises(ValueError):
                    refresh.merge_observations([{**row,"value":"NaN"}])
                self.assertEqual(before,(base/"pulse_observations.tsv").read_bytes())

if __name__=="__main__":
    unittest.main()
