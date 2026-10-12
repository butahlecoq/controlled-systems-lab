"""Typed native report adapters preserve producer identity and evidence scope."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'reports'))
import registered_reports as registered

FIXTURES = Path(__file__).parent / 'fixtures' / 'registered'


class RegisteredKindTests(unittest.TestCase):
    def test_opt05_adapter_keeps_measured_scope_and_no_comparator(self):
        result = registered.adapt(FIXTURES / 'opt05-hull-20261012-d1c211c2')
        self.assertEqual(result.kind, 'opt05-hull')
        self.assertEqual(result.report_id, 'opt05-hull-20261012-d1c211c2')
        self.assertIn('trial', result.measured_scope.lower())
        self.assertIn('no comparator', result.evidence_limits.lower())

    def test_geo03_adapter_preserves_native_payload_digest_and_limitations(self):
        result = registered.adapt(FIXTURES / 'geo03-20261012-37c3fb484e0d')
        self.assertEqual(result.kind, 'geo03-hv')
        self.assertEqual(result.report_id, 'geo03-20261012-37c3fb484e0d')
        self.assertEqual(result.payload_sha256, '37c3fb484e0da72e4710cdc8f1e5ebe27b906c2ecd3b3396c43f67d0b8e4196c')
        self.assertIn('56', result.measured_scope)
        self.assertTrue(result.evidence_limits)

    def test_unregistered_schema_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unregistered'):
            registered.adapt_payload({'schema': 'csl.future/1', 'report_id': 'future'})

    def test_geo_tampered_payload_is_rejected(self):
        record = json.loads((FIXTURES / 'geo03-20261012-37c3fb484e0d' / 'records.json').read_text())
        record['payload']['summary'][0]['failures'] = 1
        record['payload_sha256'] = registered._digest(record['payload'])
        with self.assertRaises(ValueError):
            registered.adapt_payload(record)


if __name__ == '__main__':
    unittest.main()
