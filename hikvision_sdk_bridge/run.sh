#!/usr/bin/env bash

set -euo pipefail

readonly options_file="/data/options.json"
if [[ ! -f "${options_file}" ]]; then
    echo "FATAL: Home Assistant add-on options were not found" >&2
    exit 1
fi

export DEVICE_HOST="$(jq -er '.device_host' "${options_file}")"
export DEVICE_PORT="$(jq -er '.device_port' "${options_file}")"
export DEVICE_USERNAME="$(jq -er '.username' "${options_file}")"
export DEVICE_PASSWORD="$(jq -er '.password' "${options_file}")"

readonly sdk_library="${SDK_LIBRARY:-/opt/hikvision_sdk_bridge/lib/libhcnetsdk.so}"
export SDK_LIBRARY="${sdk_library}"

if [[ ! -f "${sdk_library}" ]]; then
    echo "FATAL: bundled HCNetSDK library not found at ${sdk_library}" >&2
    echo "FATAL: reinstall the add-on image for this host architecture" >&2
    exit 1
fi

sdk_directory="$(dirname "${sdk_library}")"
export LD_LIBRARY_PATH="${sdk_directory}:${sdk_directory}/HCNetSDKCom${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

echo "Starting HCNetSDK bridge for ${DEVICE_HOST}:${DEVICE_PORT}"
exec python3 /opt/hikvision_sdk_bridge/bridge.py
