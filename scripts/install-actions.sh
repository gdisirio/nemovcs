#!/bin/sh
set -eu

src_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../data/nemo/actions" && pwd)"
data_home="${XDG_DATA_HOME:-"$HOME/.local/share"}"
target_dir="$data_home/nemo/actions"

mkdir -p "$target_dir"
cp "$src_dir"/*.nemo_action "$target_dir"/
python3 "$(dirname -- "$0")/install-layout.py"

printf 'Installed NemoVCS actions to %s\n' "$target_dir"
printf 'Restart Nemo with: nemo --quit\n'
