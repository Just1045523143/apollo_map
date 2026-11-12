"""Repository-owned imap command entry point."""
import sys
import shlex
from pathlib import Path

from imap.main import main

if __name__ == '__main__':
    try:
        sys.exit(main())
    except ImportError as error:
        requirements = Path(__file__).resolve().parents[1] / 'requirements.txt'
        print(f'[ERROR] Cannot load Python dependency: {error}. '
              f'Install dependencies with: {shlex.quote(sys.executable)} -m pip install '
              f'-r {shlex.quote(str(requirements))}', file=sys.stderr)
        sys.exit(1)
