"""Regression: conversion must not require modules.common_msgs on PYTHONPATH."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from google.protobuf import descriptor_pb2
from imap.proto import map_pb2


class ProtoRuntimeTest(unittest.TestCase):
    def test_conversion_with_conflicting_modules_package(self):
        with tempfile.TemporaryDirectory(prefix='imap standalone ') as directory:
            directory = Path(directory)
            shadow = directory / 'modules'
            shadow.mkdir()
            (shadow / '__init__.py').write_text('raise RuntimeError("external modules must not be imported")')
            output = directory / 'base_map.bin'
            env = {**os.environ, 'PYTHONPATH': str(directory), 'PYTHONNOUSERSITE': '0'}
            env.pop('APOLLO_PYTHON_PATH', None)
            # Deliberately start outside the Apollo tree.
            result = subprocess.run([str(ROOT / 'imap.sh'), '-f', '-i',
                                     str(ROOT / 'opendrive/straight_map/straight.xodr'), '-o', str(output)],
                                    cwd=directory, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            pb = map_pb2.Map.FromString(output.read_bytes())
            self.assertTrue(pb.lane)
            self.assertTrue(pb.signal)
            self.assertTrue(pb.overlap)
            self.assertTrue(output.with_suffix('.txt').is_file())

    def test_snapshot_matches_checked_in_apollo_schemas(self):
        from proto_loader import load_map_protos
        apollo_root = ROOT.parents[2]
        load_map_protos(apollo_root)
        snapshot = descriptor_pb2.FileDescriptorSet.FromString((ROOT / 'imap/proto/map.desc').read_bytes())

        def normalize(proto):
            proto.ClearField('source_code_info')
            proto.syntax = proto.syntax or 'proto2'
            def messages(items):
                for message in items:
                    for field in message.field:
                        field.ClearField('json_name')
                    messages(message.nested_type)
            messages(proto.message_type)
            return proto

        for file in snapshot.file:
            module = sys.modules[file.name.removesuffix('.proto').replace('/', '.') + '_pb2']
            cls = next(value for value in vars(module).values() if isinstance(value, type) and hasattr(value, 'DESCRIPTOR'))
            source = descriptor_pb2.FileDescriptorProto.FromString(cls.DESCRIPTOR.file.serialized_pb)
            self.assertEqual(normalize(file), normalize(source), file.name)


if __name__ == '__main__':
    unittest.main()
