from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path
import unittest

from scripts.pulse_editorial_recovery_guard import (
    audit_news_archive, clean_observer_article, repair_observer_archive,
    evidence_ledger, stage_ai_draft)

FIXTURES = json.loads((Path(__file__).parent / 'fixtures/three_historical_samples.json').read_text(encoding='utf-8'))
RADAR = 'PULSE-34DFAF8E1B8027FD'
OBSERVER = 'OBS-B8D28ACD8CD8F501DB'
FALLBACK = 'OBS-19C815C20A50F4BBE6'


def verified_series():
    src='https://www.istat.it/dati/comunicato'
    return {'id':'PULSE-SAMPLE-001','publication_status':'published',
            'published_at':'2026-09-16T08:00:00+00:00',
            'editorial_status':'verified_primary_match',
            'verification_tier':'verified_comparable_series',
            'public_source':{'role':'primary_statistical_source','url':src},
            'verified_series_relevant':[{'indicator':'Indice prezzi','unit':'%',
                'source_url':src,'territory':'Italia',
                'observations':[{'period':'2026-07','value':3.1},{'period':'2026-08','value':3.3}]}],
            'chart_spec':{'status':'verified','data':[{'period':'2026-07','value':3.1},
                                                     {'period':'2026-08','value':3.3}]},
            'summary':'Testo verificato'}


class HistoricalRegression(unittest.TestCase):
    def test_radar_citizenship_is_not_published_as_untyped_numbers_article(self):
        old=deepcopy(FIXTURES[RADAR])
        new,report=audit_news_archive([old])
        self.assertEqual(report['source_cards_reclassified'],1)
        self.assertEqual(new[0]['editorial_format'],'source_card')
        self.assertNotIn('Valori individuati:',new[0]['summary'])
        self.assertEqual(new[0]['id'],old['id'])
        self.assertEqual(new[0]['published_at'],old['published_at'])
        self.assertEqual(new[0]['public_source'],old['public_source'])
        self.assertEqual(new[0]['publication_status'],'published')
        # A genuine primary-source link does not bind numbers to indicators.
        self.assertFalse(evidence_ledger(old)['verified'])

    def test_decidipresto_removes_related_article_titles(self):
        old=deepcopy(FIXTURES[OBSERVER])
        self.assertEqual(len(old['pulse_article_body']),6)
        cleaned,issues=clean_observer_article(old)
        self.assertIn('related_page_headlines_removed',issues)
        self.assertEqual(len(cleaned['pulse_article_body']),1)
        self.assertIn('208 milioni',cleaned['pulse_article_body'][0])
        self.assertNotIn('Women in STEM',cleaned['pulse_summary'])
        self.assertEqual(cleaned['key_figures'],[])
        self.assertEqual(cleaned['editorial_format'],'source_card')
        self.assertEqual(cleaned['public_source'],old['public_source'])
        self.assertEqual(cleaned['published_at'],old['published_at'])

    def test_observer_boilerplate_is_demoted_not_invented(self):
        old=deepcopy(FIXTURES[FALLBACK])
        repaired,issues=clean_observer_article(old)
        self.assertIn('boilerplate_observer_article_demoted',issues)
        self.assertEqual(repaired['pulse_article_body'],[old['pulse_summary']])
        self.assertEqual(repaired['editorial_format'],'source_card')

    def test_archive_cleaner_is_idempotent(self):
        source=[deepcopy(FIXTURES[OBSERVER]),deepcopy(FIXTURES[FALLBACK])]
        once,report=repair_observer_archive(source)
        twice,report2=repair_observer_archive(once)
        self.assertEqual(report['changed'],2)
        self.assertEqual(report2['changed'],0)
        self.assertEqual(twice,once)

    def test_safe_multisection_article_stays_untouched(self):
        old=deepcopy(FIXTURES[OBSERVER])
        old['pulse_article_body']=[
            'Il documento analizza le politiche industriali e gli investimenti, con dati del territorio di riferimento.'
        ]+['La ricerca propone una lettura dei progetti di formazione professionale.']*4
        repaired,issues=clean_observer_article(old)
        self.assertEqual(issues,[])
        self.assertEqual(repaired,old)

    def test_verified_ledger_requires_typed_primary_series(self):
        article=verified_series()
        ledger=evidence_ledger(article)
        self.assertTrue(ledger['verified'])
        self.assertEqual(len(ledger['observations']),2)
        self.assertEqual(ledger['observations'][1]['indicator'],'Indice prezzi')
        self.assertEqual(ledger['observations'][1]['period'],'2026-08')
        self.assertEqual(ledger['observations'][1]['unit'],'%')
        article['verified_series_relevant'][0]['source_url']='https://wrong.example'
        self.assertFalse(evidence_ledger(article)['verified'])

    def test_ai_draft_is_private_pending_and_does_not_auto_approve(self):
        article=verified_series()
        proposed={**article,'headline':'Un titolo approfondito su un indice verificato',
                  'summary':'Una descrizione dettagliata delle statistiche pubblicate',
                  'pulse_article_body':[{'heading':'','text':'Testo giornalistico controllabile.'}],
                  'editorial_format':'ai_assisted_evidence_checked',
                  'editorial_review':{'automatic_numeric_validation':True,
                                      'human_editorial_review':False}}
        candidate=stage_ai_draft(article,proposed,at='2026-11-09T18:00:00Z')
        self.assertFalse(candidate['publication_allowed'])
        self.assertEqual(candidate['review_status'],'human_review_required')
        self.assertNotIn('publication_status',candidate)
        self.assertEqual(candidate['article_id'],article['id'])
        self.assertEqual(article['publication_status'],'published')

    def test_ai_unverified_series_is_rejected(self):
        article=verified_series()
        article['verified_series_relevant']=[]
        with self.assertRaises(ValueError):
            stage_ai_draft(article,{'editorial_format':'ai_assisted_evidence_checked'})


if __name__=='__main__':
    unittest.main()
