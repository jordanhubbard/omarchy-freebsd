#!/usr/local/bin/bash
# Real OSS/PipeWire bridge test. The Bluetooth transport is deliberately replaced
# by /dev/null; this cannot qualify pairing, codecs, radio playback or reconnect.
set -euo pipefail
[[ $(uname -s) == FreeBSD && $EUID != 0 && -n ${XDG_RUNTIME_DIR:-} ]] || exit 1
here=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
root() {
  if [[ -n ${SUDO_ASKPASS:-} ]]; then sudo -A "$@"; else sudo "$@"; fi
}
cleanup() {
  root /usr/local/bin/bash "$work/backend" stop >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT
[[ ! -e /dev/dsp.daemonarchy_qa ]] || { echo 'QA audio device already exists' >&2; exit 1; }
mkdir "$work/run" "$work/state"
sed -e '/^case ${1:-}/,$d' -e 's|%%PREFIX%%|/usr/local|g' \
  -e 's|dsp.daemonarchy_bt|dsp.daemonarchy_qa|g' \
  -e 's|daemonarchy\.bluetooth|daemonarchy.bluetooth.qa|g' \
  "$here/freebsd-bin/omarchy-bluetooth" >"$work/functions"
# Override only the transport endpoint, not the OSS device or PipeWire adapter.
cat >"$work/backend" <<'BACKEND'
set -euo pipefail
work=$(dirname "$0")
source "$work/functions"
STATE_DIR=$work/state RUN_DIR=$work/run
eval "$(declare -f audio_start | sed 's|/dev/bluetooth/\$addr|/dev/null|g')"
case $1 in
  start) audio_start 00:11:22:33:44:55 ;;
  stop) audio_stop ;;
  *) exit 1 ;;
esac
BACKEND
root /usr/local/bin/bash "$work/backend" start
[[ $(stat -f %Lp "$work/run/audio.log") == 600 ]]
source "$work/functions"
STATE_DIR=$work/state RUN_DIR=$work/run
previous=$(pactl get-default-sink)
audio_route 00:11:22:33:44:55
[[ $(pactl get-default-sink) == daemonarchy.bluetooth.qa ]]
audio_route 00:11:22:33:44:55
[[ $(audio_node_ids | wc -l | tr -d ' ') == 1 ]]
dd if=/dev/zero of="$work/silence.raw" bs=192000 count=1 2>/dev/null
timeout 10 pw-cat --playback --raw --target daemonarchy.bluetooth.qa \
  --rate 48000 --channels 2 --format s16 "$work/silence.raw"
audio_unroute 00:11:22:33:44:55
root /usr/local/bin/bash "$work/backend" stop
[[ ! -e /dev/dsp.daemonarchy_qa && ! -e $STATE_DIR/audio-output ]]
[[ -z $(audio_node_ids) ]]
pactl set-default-sink "$previous"
echo 'PASS: native virtual OSS creation, desktop sink/default, repeated route, PCM write and cleanup (null transport only)'
