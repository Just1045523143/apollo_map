#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if (( $# > 1 )); then
  echo "Usage: $(basename "$0") [OUTPUT_ROOT]" >&2
  exit 2
fi
# Use the same conversion/postprocessing pipeline as custom OpenDRIVE maps.
# An optional argument selects the output root; defaults to modules/map/data.
for index in $(seq -w 1 12); do
  input="${SCRIPT_DIR}/opendrive/town${index}/Town${index}.xodr"
  if [[ -f "${input}" ]]; then
    "${SCRIPT_DIR}/gen_apollo_map_from_input.sh" \
      "$(dirname "${input}")" "$(basename "${input}")" "town${index}" "$@"
  else
    echo "[INFO] Skipping missing map: ${input}"
  fi
done
