#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APOLLO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

usage() {
  cat <<EOF
Usage:
  $(basename "$0") [MAP_ROOT MAP_NAME]

Examples:
  $(basename "$0") /opt/apollo/modules/map/data test_track
  $(basename "$0") ${APOLLO_ROOT}/modules/map/data test_track

With no arguments, the script prompts for MAP_ROOT and MAP_NAME.

Environment overrides:
  SIM_MAP_GENERATOR_BIN=/path/to/sim_map_generator
  TOPO_CREATOR_BIN=/path/to/topo_creator
  ROUTING_CONF=/path/to/routing.conf
EOF
}

fail() {
  echo "[ERROR] $*" >&2
  exit 1
}

resolve_binary() {
  local override="$1"
  local command_name="$2"
  shift 2
  local candidate

  if [[ -n "${override}" ]]; then
    [[ -x "${override}" ]] || fail "Binary is not executable: ${override}"
    printf '%s\n' "${override}"
    return
  fi

  if command -v "${command_name}" >/dev/null 2>&1; then
    command -v "${command_name}"
    return
  fi

  for candidate in "$@"; do
    if [[ -x "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return
    fi
  done

  fail "${command_name} was not found; build it or set its environment override"
}

resolve_routing_conf() {
  local candidate

  if [[ -n "${ROUTING_CONF:-}" ]]; then
    [[ -f "${ROUTING_CONF}" ]] || fail "ROUTING_CONF does not exist: ${ROUTING_CONF}"
    printf '%s\n' "${ROUTING_CONF}"
    return
  fi

  for candidate in \
    "${APOLLO_ROOT}/modules/routing/conf/routing.conf" \
    /apollo_workspace/code/apollo/modules/routing/conf/routing.conf \
    /apollo/modules/routing/conf/routing.conf \
    /opt/apollo/modules/routing/conf/routing.conf; do
    if [[ -f "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return
    fi
  done

  fail "routing.conf was not found; set ROUTING_CONF=/path/to/routing.conf"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if (( $# > 2 )); then
  usage >&2
  exit 2
fi

map_root="${1:-}"
map_name="${2:-}"

if [[ -z "${map_root}" ]]; then
  read -r -p "Apollo map root [${APOLLO_ROOT}/modules/map/data]: " map_root
  map_root="${map_root:-${APOLLO_ROOT}/modules/map/data}"
fi
if [[ -z "${map_name}" ]]; then
  read -r -p "Map name: " map_name
fi

[[ -n "${map_name}" ]] || fail "Map name cannot be empty"
[[ "${map_name}" != */* && "${map_name}" != "." && "${map_name}" != ".." ]] || \
  fail "Invalid map name: ${map_name}"

map_dir="${map_root%/}/${map_name}"
[[ -d "${map_dir}" ]] || fail "Map directory does not exist: ${map_dir}"
[[ -s "${map_dir}/base_map.bin" ]] || fail "base_map.bin does not exist or is empty: ${map_dir}"

sim_map_generator="$(resolve_binary \
  "${SIM_MAP_GENERATOR_BIN:-}" \
  sim_map_generator \
  /opt/apollo/neo/bin/sim_map_generator \
  "${APOLLO_ROOT}/bazel-bin/modules/map/tools/sim_map_generator" \
  /apollo_workspace/bazel-bin/modules/map/tools/sim_map_generator)"

topo_creator="$(resolve_binary \
  "${TOPO_CREATOR_BIN:-}" \
  topo_creator \
  /opt/apollo/neo/bin/topo_creator \
  "${APOLLO_ROOT}/bazel-bin/modules/routing/topo_creator" \
  /apollo_workspace/bazel-bin/modules/routing/topo_creator)"

routing_conf="$(resolve_routing_conf)"
global_flagfile="${APOLLO_ROOT}/modules/common/data/global_flagfile.txt"
[[ -f "${global_flagfile}" ]] || \
  fail "Apollo global flagfile does not exist: ${global_flagfile}"

echo "[INFO] Generating sim map in ${map_dir}"
(
  cd "${APOLLO_ROOT}"
  "${sim_map_generator}" --map_dir="${map_dir}" --output_dir="${map_dir}"
)

echo "[INFO] Generating routing map in ${map_dir}"
(
  cd "${APOLLO_ROOT}"
  # global_flagfile.txt defines a default map_dir. Gflags evaluates options in
  # order, so map_dir must follow flagfile to override that default.
  "${topo_creator}" --flagfile="${routing_conf}" --map_dir="${map_dir}"
)

for output in sim_map.bin routing_map.bin; do
  [[ -s "${map_dir}/${output}" ]] || fail "${output} was not generated"
done

echo "[INFO] Dependency map generation completed: ${map_dir}"
