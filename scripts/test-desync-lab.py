"""Runner failure-path checks; not game simulation coverage."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('lab', Path(__file__).with_name('desync-lab.py'))
lab = importlib.util.module_from_spec(spec);spec.loader.exec_module(lab)


class Runner(unittest.TestCase):
    def exercise(self, code, **case):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);binary = root/'build.bin';binary.write_bytes(b'fixture')
            config = {'repeat': 2, 'builds': {'baseline': str(binary), 'candidate': str(binary)},
                      'cases': [dict(name='fixture', argv=['{python}', '-c', code], **case)]}
            path = root/'config.json';path.write_text(json.dumps(config))
            result = lab.run(path, root/'runs')
            self.assertTrue((root/'runs/results.json').exists())
            with self.assertRaises(FileExistsError):lab.run(path, root/'runs')
            return result

    def test_repeats_are_isolated(self):
        r = self.exercise("from pathlib import Path; p=Path(r'{out}')/'marker'; assert not p.exists(); p.write_text('ok')")
        self.assertTrue(r['success']);self.assertEqual(len(r['runs']), 4)

    def test_nonzero_is_failure(self):
        r = self.exercise('raise SystemExit(7)')
        self.assertFalse(r['success']);self.assertTrue(all(x['exitCode']==7 for x in r['runs']))

    def test_timeout_is_not_pass(self):
        r = self.exercise('import time;time.sleep(5)', timeout=0.1)
        self.assertFalse(r['success']);self.assertTrue(all(x['status']=='timeout' for x in r['runs']))

    def test_missing_fresh_trace_is_error(self):
        r = self.exercise('pass', tracePair=['left.zip','right.zip'])
        self.assertFalse(r['success']);self.assertTrue(all(x['status']=='error' for x in r['runs']))


if __name__ == '__main__':unittest.main()
