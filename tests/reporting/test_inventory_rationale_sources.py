import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('validate_inventory', ROOT / 'scripts/catalogue/validate_inventory.py')
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


class RationaleSourceTests(unittest.TestCase):
    def test_local_source_must_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = {'source': 'rationale.md'}
            with self.assertRaisesRegex(AssertionError, 'missing candidate rationale'):
                inventory.check_candidate_source(root, row)
            (root / 'rationale.md').write_text('rationale')
            inventory.check_candidate_source(root, row)

    def test_archived_source_requires_repository_commit_and_byte_hash(self):
        prefix = 'https://github.com/butahlecoq/controlled-systems-lab/blob/'
        source = prefix + '797b606faee21d9cc22004c882fc7e120113be20/docs/research/audit.md'
        row = {'source': source, 'source_sha256': '6ceb1153879f4cc6c94060ba8afdaec32cc9a366b283cab90f41e57e174513ff'}
        inventory.check_candidate_source(ROOT, row)
        for invalid in (source.replace('797b606faee21d9cc22004c882fc7e120113be20', 'main'),
                        source.replace('github.com', 'example.org')):
            with self.subTest(source=invalid), self.assertRaises(AssertionError):
                inventory.check_candidate_source(ROOT, {**row, 'source': invalid})
        with self.assertRaisesRegex(AssertionError, 'byte hash'):
            inventory.check_candidate_source(ROOT, {'source': source})
