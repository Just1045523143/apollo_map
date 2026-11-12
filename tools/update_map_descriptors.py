#!/usr/bin/env python3
"""Regenerate imap's protobuf descriptor snapshot with protoc (or grpc_tools)."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    editor_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apollo-root', type=Path, default=editor_root.parents[2])
    parser.add_argument('--protoc', help='Path to a protoc executable')
    args = parser.parse_args()
    executable = args.protoc or shutil.which('protoc')
    command = [executable] if executable else [sys.executable, '-m', 'grpc_tools.protoc']
    output = editor_root / 'imap/proto/map.desc'
    # Write separately so a failed compiler never removes the working snapshot.
    temporary = output.with_suffix('.desc.tmp')
    try:
        subprocess.run(command + [f'--proto_path={args.apollo_root}',
                       f'--descriptor_set_out={temporary}', '--include_imports',
                       'modules/common_msgs/map_msgs/map.proto'], check=True)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
