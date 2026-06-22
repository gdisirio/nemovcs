#!/bin/sh
set -eu

src_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../data/nemo/actions" && pwd)"
icons_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../rsc/icons/nemovcs" && pwd)"
data_home="${XDG_DATA_HOME:-"$HOME/.local/share"}"
target_dir="$data_home/nemo/actions"
target_icons_dir="$target_dir/nemovcs-icons/nemovcs"

mkdir -p "$target_dir"
rm -rf "$target_dir/nemovcs-icons"
rm -f "$target_dir"/nemovcs*.nemo_action
mkdir -p "$target_icons_dir"
for action in \
  nemovcs-commit.nemo_action \
  nemovcs-update.nemo_action \
  nemovcs-background-update.nemo_action \
  nemovcs-diff.nemo_action \
  nemovcs-svn-commit.nemo_action \
  nemovcs-svn-update.nemo_action \
  nemovcs-background-svn-update.nemo_action \
  nemovcs-svn-diff.nemo_action
do
  cp "$src_dir/$action" "$target_dir"/
done
cp -R "$icons_dir"/actions "$target_icons_dir"/
cp -R "$icons_dir"/apps "$target_icons_dir"/
cp -R "$icons_dir"/emblems "$target_icons_dir"/
python3 "$(dirname -- "$0")/install-layout.py"

printf 'Installed NemoVCS actions to %s\n' "$target_dir"
printf 'Installed NemoVCS icons to %s\n' "$target_icons_dir"
printf 'Restart Nemo with: nemo --quit\n'
