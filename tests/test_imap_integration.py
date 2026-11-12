"""Verify repository-owned converter selection and pipeline wiring without Apollo binaries."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class ImapIntegrationTest(unittest.TestCase):
    def run_cli(self, *args, **kwargs):
        return subprocess.run([str(ROOT / 'imap.sh'), *args], cwd='/tmp',
                              capture_output=True, text=True, **kwargs)

    def test_help_uses_local_source_even_with_other_imap_on_pythonpath(self):
        with tempfile.TemporaryDirectory() as temp:
            fake = Path(temp) / 'imap'
            fake.mkdir()
            (fake / '__init__.py').write_text('raise RuntimeError("wrong imap")')
            result = self.run_cli('--help', env={**os.environ, 'PYTHONPATH': temp})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--sampling', result.stdout)

    def test_invalid_arguments_and_missing_file_fail_before_dependencies(self):
        for args in [('-f',), ('-f', '-i', 'x', '-o', '/tmp/map'),
                     (), ('-m', 'x', '-f', '-i', 'x', '-o', '/tmp/map.bin'),
                     ('-f', '-i', 'x', '-o', '/tmp/map.bin', '-s', '0'),
                     ('-f', '-i', 'x', '-o', '/tmp/map.bin', '-s', 'nan'),
                     ('-f', '-i', '/no/such/input.xodr', '-o', '/tmp/map.bin')]:
            result = self.run_cli(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('Traceback', result.stderr)

    def test_headless_drawing_never_imports_matplotlib(self):
        sys.path.insert(0, str(ROOT))
        try:
            from imap import global_var
            from imap.lib import draw
            global_var._init()
            global_var.set_element_vaule('visualize', False)
            with mock.patch.object(draw, '_plot', side_effect=AssertionError('GUI loaded')):
                draw.draw_line([], 'r')
            self.assertIsNone(draw.fig)
        finally:
            sys.path.remove(str(ROOT))

    def test_real_opendrive_parser_is_available_from_vendored_package(self):
        sys.path.insert(0, str(ROOT))
        try:
            from imap.lib.opendrive.map import Map
            parser = Map()
            source = ROOT / 'opendrive/straight_map/straight.xodr'
            if not source.is_file():
                self.skipTest('straight.xodr is not present in this checkout')
            parser.load(str(source))
            self.assertTrue(parser.roads)
        finally:
            sys.path.remove(str(ROOT))

    def test_pipeline_defaults_to_local_source_and_preserves_overrides(self):
        with tempfile.TemporaryDirectory(prefix='imap integration ') as temp:
            temp = Path(temp)
            source = temp / 'input map.xodr'
            source.write_text('<OpenDRIVE/>')
            log = temp / 'calls'
            tool = temp / 'fake tool'
            tool.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['CALL_LOG'], 'a') as f:
    f.write(json.dumps(args) + '\\n')
if '-o' in args:
    pathlib.Path(args[args.index('-o') + 1]).write_bytes(b'base')
else:
    directory = pathlib.Path(next(a.split('=', 1)[1] for a in args if a.startswith('--map_dir=')))
    for name in ['base_map.txt', 'sim_map.bin', 'routing_map.bin']:
        (directory / name).write_text('stub')
''')
            tool.chmod(0o755)
            env = dict(os.environ, CALL_LOG=str(log), IMAP_PYTHON=str(tool),
                       ROAD_WIDTH_SAMPLE_GENERATOR_BIN=str(tool),
                       SIM_MAP_GENERATOR_BIN=str(tool), TOPO_CREATOR_BIN=str(tool))
            env.pop('IMAP_BIN', None)
            import json
            for override in [False, True]:
                if override:
                    env['IMAP_BIN'] = str(tool)
                log.unlink(missing_ok=True)
                result = subprocess.run(['bash', str(ROOT / 'gen_apollo_map_from_input.sh'),
                                         str(temp), source.name, 'test_map', str(temp / 'output')],
                                        cwd='/tmp', env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = [json.loads(line) for line in log.read_text().splitlines()]
                self.assertEqual(len(calls), 4)
                self.assertEqual(calls[0][:2], ['-f', '-i'] if override else ['-m', 'imap'])
                self.assertIn(str(source), calls[0])
                self.assertTrue(calls[1][0].startswith('--map_dir='))
                self.assertTrue(calls[2][1].startswith('--output_dir='))
                self.assertTrue(calls[3][0].startswith('--flagfile='))

            # A failing converter must stop before any postprocessor runs.
            env['IMAP_BIN'] = '/bin/false'
            log.unlink()
            result = subprocess.run(['bash', str(ROOT / 'gen_apollo_map_from_input.sh'),
                                     str(temp), source.name, 'test_map', str(temp / 'output')],
                                    cwd='/tmp', env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(log.exists())


if __name__ == '__main__':
    unittest.main()
