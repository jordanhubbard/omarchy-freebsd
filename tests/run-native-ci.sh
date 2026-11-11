#!/bin/sh
# Run as a separate shell so the caller's status capture cannot disable -e.
# Disposable FreeBSD guest only; no hardware or release admission.
set -eu
test "$(uname -s)" = FreeBSD
test "$(id -u)" = 0
freebsd-version -ku
pkg install -y bash python312 py312-pygobject node24 jq perl5 coreutils findutils
export OMARCHY_TEST_ROUTER="$(pwd)/omarchy/bin/omarchy"
export OMARCHY_TEST_MENU="$(pwd)/omarchy/default/omarchy/omarchy-menu.jsonc"
export OMARCHY_TEST_BINDINGS="$(pwd)/omarchy/default/hypr/bindings/applications.lua"
cd adapters
/usr/local/bin/python3.12 -c 'import gi; from gi.repository import Gio; print(Gio.AppInfo)'
command -v bash node jq perl
/usr/local/bin/python3.12 -m unittest discover -s tests -v
pw useradd compat_test -m
su -m compat_test -c '/usr/local/bin/bash tests/bluetooth-audio.sh'
