#!/usr/bin/env bash
# Backend policy tests; these do not claim a real Bluetooth audio exchange.
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
eval "$(sed '/^case ${1:-}/,$d' "$here/freebsd-bin/omarchy-bluetooth")"
STATE_DIR=$work/state RUN_DIR=$work/run
mkdir -p "$STATE_DIR" "$RUN_DIR"
addr=00:11:22:33:44:55
hci_node() { echo ubt0hci; }
acl_failure=false existing_link=false
hcc() {
  case $1 in
    create_connection) if $acl_failure; then return 1; fi ;;
    read_connection_list) if $existing_link; then printf '%s 42\n' "$addr"; fi ;;
  esac
}
service() { :; }
record_state() { touch "$work/recorded"; }
timeout() { shift; "$@"; }
sdpcontrol() {
  [[ $* == "-a $addr search 110b" ]]
  if $audio_device; then echo 'Audio Sink (0x110b)'; else echo 'Human Interface Device (0x1124)'; fi
}
audio_start() { printf '%s\n' "$1" >>"$work/started"; return "$start_status"; }
audio_device=false start_status=0
connect "$addr"
[[ ! -f $work/started && -f $work/recorded ]]
rm "$work/recorded"
acl_failure=true
if connect "$addr"; then echo 'FAIL: link failure was masked'; exit 1; fi
[[ ! -f $work/recorded ]]
existing_link=true
connect "$addr"
[[ -f $work/recorded && ! -f $work/started ]]
acl_failure=false
audio_device=true
connect "$addr"
[[ $(cat "$work/started") == "$addr" ]]
rm "$work/recorded"
start_status=1
if connect "$addr"; then echo 'FAIL: audio failure was masked'; exit 1; fi
[[ ! -f $work/recorded ]]

# Exercise routing as the desktop user; root intentionally never owns its node.
if ((EUID == 0)); then echo 'Run this portable test as a non-root desktop user.' >&2; exit 1; fi
printf '%s\n' "$addr" >"$RUN_DIR/audio-address"
printf '[]\n' >"$work/nodes"
pw-dump() { cat "$work/nodes"; }
pactl() {
  [[ $* == info || $* == 'set-default-sink daemonarchy.bluetooth' || $* == 'list short sinks' ]]
  printf '%s\n' "$*" >>"$work/pactl"
  if [[ $* == 'list short sinks' ]]; then printf '42\tdaemonarchy.bluetooth\tPipeWire\n'; fi
}
pw-cli() {
  case $1 in
    create-node)
      [[ $2 == adapter ]]
      jq -e '."factory.name" == "freebsd-oss.sink" and
        ."api.freebsd-oss.dsp-path" == "/dev/dsp.daemonarchy_bt" and
        ."media.class" == "Audio/Sink" and ."object.linger" == true' <<<"$3" >/dev/null
      echo create >>"$work/node-operations"
      printf '%s\n' '[{"id":42,"type":"PipeWire:Interface:Node","info":{"props":{"node.name":"daemonarchy.bluetooth"}}},{"id":43,"type":"PipeWire:Interface:Node","info":{"props":{"node.name":"other-output"}}}]' >"$work/nodes"
      ;;
    destroy) [[ $2 == 42 ]]; echo destroy >>"$work/node-operations" ;;
    *) exit 1 ;;
  esac
}
audio_route "$addr"
audio_route "$addr"
audio_route "$addr" false
[[ $(grep -c '^set-default-sink ' "$work/pactl") == 2 ]]
[[ $(grep -c '^create$' "$work/node-operations") == 1 ]]
audio_unroute 'AA:BB:CC:DD:EE:FF'
(( $(wc -l <"$work/node-operations") == 1 ))
audio_unroute "$addr"
grep -qx destroy "$work/node-operations"
grep -qx 'set-default-sink daemonarchy.bluetooth' "$work/pactl"
echo 'PASS: HID isolation, A2DP detection, startup failure, user routing, reconnect reuse and targeted removal'
