#!/usr/bin/env bash

set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo "usage: $0 <path-to-dmg>" >&2
  exit 2
fi

dmg_path="$1"
if [[ ! -f "$dmg_path" ]]; then
  echo "macos_dmg_missing:$dmg_path" >&2
  exit 1
fi

mount_dir="$(mktemp -d "${TMPDIR:-/tmp}/vibe-learner-dmg-verify.XXXXXX")"
device=""

cleanup() {
  if [[ -n "$device" ]]; then
    hdiutil detach "$device" >/dev/null
  fi
  rmdir "$mount_dir"
}
trap cleanup EXIT

hdiutil verify "$dmg_path"
attach_output="$(hdiutil attach -readonly -nobrowse -mountpoint "$mount_dir" "$dmg_path")"
device="$(printf '%s\n' "$attach_output" | awk '/^\/dev\// { print $1; exit }')"
if [[ -z "$device" ]]; then
  echo "macos_dmg_device_missing" >&2
  exit 1
fi

app_paths=("$mount_dir"/*.app)
if [[ "${#app_paths[@]}" -ne 1 || ! -d "${app_paths[0]}" ]]; then
  echo "macos_dmg_app_count_invalid:${#app_paths[@]}" >&2
  exit 1
fi

codesign --verify --deep --strict --verbose=4 "${app_paths[0]}"
echo "Verified macOS bundle signature: ${app_paths[0]}"
