#!/bin/sh
set -eu

data_home="${XDG_DATA_HOME:-"$HOME/.local/share"}"
target_dir="$data_home/nemo/actions"

mkdir -p "$target_dir"
rm -rf "$target_dir/nemovcs-icons"
rm -f "$target_dir"/nemovcs*.nemo_action
python3 "$(dirname -- "$0")/install-layout.py"

printf 'Removed legacy NemoVCS actions from %s\n' "$target_dir"
printf 'Restart Nemo with: nemo --quit\n'
