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
export SDK_LIBRARY="$(jq -er '.sdk_library' "${options_file}")"

if [[ ! -f "${SDK_LIBRARY}" ]]; then
    echo "FATAL: HCNetSDK library not found at ${SDK_LIBRARY}" >&2
    echo "FATAL: Copy the matching Linux SDK to /share/hikvision_sdk first" >&2
    exit 1
fi

sdk_directory="$(dirname "${SDK_LIBRARY}")"
export LD_LIBRARY_PATH="${sdk_directory}:${sdk_directory}/HCNetSDKCom${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

echo "Starting HCNetSDK bridge for ${DEVICE_HOST}:${DEVICE_PORT}"
exec python3 /opt/hikvision_sdk_bridge/bridge.py
