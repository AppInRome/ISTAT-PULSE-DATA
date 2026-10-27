"""SDMX outage safety: never hammer an IP for the entire dataset batch."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

PATH=Path(__file__).resolve().parents[1]/"scripts"/"generate_sdmx_events.py"
spec=importlib.util.spec_from_file_location("generate_sdmx_events", PATH)
sdmx=importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdmx)

class SDMXBreakerTests(unittest.TestCase):
    def test_stop_after_three_fully_failed_flows(self):
        sdmx._CONSECUTIVE_FAILURES=0
        example={"flow":"TEST_DATAFLOW","start":"2024"}
        with patch.object(sdmx,"wait_for_sdmx_slot"), \
             patch.object(sdmx.time,"sleep"), \
             patch.object(sdmx.urllib.request,"urlopen",side_effect=TimeoutError("request timed out")) as online:
            for _ in range(3):
                with self.assertRaises(TimeoutError):
                    sdmx.fetch(example)
            self.assertEqual(6,online.call_count)
            with self.assertRaisesRegex(RuntimeError,"circuit breaker open"):
                sdmx.fetch(example)
            self.assertEqual(6,online.call_count)
        sdmx._CONSECUTIVE_FAILURES=0

    def test_success_resets_timeout_history(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return b"<GenericData/>"
        sdmx._CONSECUTIVE_FAILURES=2
        with patch.object(sdmx,"wait_for_sdmx_slot"), \
             patch.object(sdmx.urllib.request,"urlopen",return_value=Response()):
            data,url=sdmx.fetch({"flow":"TEST","start":"2024"})
            self.assertEqual(b"<GenericData/>",data)
            self.assertEqual(0,sdmx._CONSECUTIVE_FAILURES)

if __name__=="__main__":
    unittest.main()
