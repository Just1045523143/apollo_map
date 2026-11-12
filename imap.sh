#!/usr/bin/env bash
# Always load the vendored imap, independently of the working directory or pip.
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
exec "${IMAP_PYTHON:-python3}" -m imap "$@"
