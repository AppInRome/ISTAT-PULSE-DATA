"""Offline checks: safe refresh must preserve history and reject broken data."""
import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'refresh_daily_safe.py'
spec = importlib.util.spec_from_file_location('refresh_daily_safe', SCRIPT)
pulse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pulse)

class SafeRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old = pulse.DATA
        pulse.DATA = self.root
        pulse.write_tsv(self.root / 'pulse_events.tsv', pulse.EVENT_FIELDS, [
            {**{k:'' for k in pulse.EVENT_FIELDS}, 'id':'A', 'indicator':'test', 'period':'2026-Q2',
             'source_family':'ISTAT', 'source_url':'https://www.istat.it', 'scope':'GREEN'}
        ])
        pulse.write_json(self.root / 'pulse_manifest.json', {'version':'test','feed_events':1})

    def tearDown(self):
        pulse.DATA = self.old
        self.tmp.cleanup()

    def test_new_event_preserves_old(self):
        candidate = {**{k:'' for k in pulse.EVENT_FIELDS}, 'id':'B', 'indicator':'new',
                     'period':'2026-Q3', 'source_family':'ISPRA',
                     'source_url':'https://www.isprambiente.gov.it', 'scope':'GREEN'}
        self.assertEqual(1, pulse.merge_events([candidate]))
        rows = pulse.read_tsv(self.root / 'pulse_events.tsv', pulse.EVENT_FIELDS)
        self.assertEqual({'A','B'}, {x['id'] for x in rows})
        self.assertEqual(2, pulse.read_json(self.root/'pulse_manifest.json')['feed_events'])

    def test_old_period_cannot_downgrade(self):
        candidate={**{k:'' for k in pulse.EVENT_FIELDS}, 'id':'A','indicator':'test',
                   'period':'2025-Q1', 'source_family':'ISTAT',
                   'source_url':'https://www.istat.it', 'scope':'GREEN'}
        self.assertEqual(0, pulse.merge_events([candidate]))
        self.assertEqual('2026-Q2', pulse.read_tsv(self.root/'pulse_events.tsv',pulse.EVENT_FIELDS)[0]['period'])

    def test_broken_event_rejected_without_loss(self):
        candidate={**{k:'' for k in pulse.EVENT_FIELDS}, 'id':'B', 'indicator':'new',
                   'period':'2026-Q3', 'source_family':'ISPRA'}
        with self.assertRaises(ValueError): pulse.merge_events([candidate])
        self.assertEqual(1, len(pulse.read_tsv(self.root/'pulse_events.tsv',pulse.EVENT_FIELDS)))

if __name__=='__main__':
    unittest.main()