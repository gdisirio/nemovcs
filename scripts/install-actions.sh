#!/bin/sh
set -eu

src_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../data/nemo/actions" && pwd)"
icons_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../rsc/icons/rabbitvcs" && pwd)"
data_home="${XDG_DATA_HOME:-"$HOME/.local/share"}"
target_dir="$data_home/nemo/actions"
target_icons_dir="$target_dir/nemovcs-icons/rabbitvcs"

mkdir -p "$target_dir"
rm -rf "$target_icons_dir"
mkdir -p "$target_icons_dir"
cp "$src_dir"/*.nemo_action "$target_dir"/
cp -R "$icons_dir"/actions "$target_icons_dir"/
cp -R "$icons_dir"/apps "$target_icons_dir"/
python3 "$(dirname -- "$0")/install-layout.py"

printf 'Installed NemoVCS actions to %s\n' "$target_dir"
printf 'Installed NemoVCS icons to %s\n' "$target_icons_dir"
printf 'Restart Nemo with: nemo --quit\n'
