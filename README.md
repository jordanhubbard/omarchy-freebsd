# omarchy-freebsd

The FreeBSD compatibility layer for the [Omarchy](https://omarchy.org) desktop, installed by the FreeBSD port [`x11-wm/omarchy`](https://github.com/jordanhubbard/freebsd-ports/tree/omarchy/x11-wm/omarchy) together with Omarchy's own sources. Omarchy is written for Arch Linux; this is what lets it run, unchanged apart from these adaptations, on FreeBSD.

## Contents

- `freebsdize.in`: the adaptation of Omarchy's sources, as one script. The port runs it on the release it packages, and `omarchy dev link` runs it on a git checkout, so both get the same result: Arch paths to FreeBSD ones, pacman to pkg(8), GNU tools where Omarchy needs them, and the rest.
- `compat/`: stand-ins for the systemd and Linux tools Omarchy calls: `systemctl` (user units under daemon(8), system units through rc(8)), `uwsm`, `journalctl`, `timedatectl`, `brightnessctl`, `powerprofilesctl`, and others.
- `freebsd-bin/`: FreeBSD versions of Omarchy commands built on pacman, `/sys`, NetworkManager or BlueZ, among them `omarchy-wifi` (wpa_supplicant) and `omarchy-bluetooth` (FreeBSD's Bluetooth stack), which drive the shell's network and Bluetooth panels.
- `systemd-user/`: the session's PipeWire and keyring units, and the default-sound-device oneshot.
- `seed-user`, `profile-omarchy.sh`, `env-freebsd`, `audio-default`: session setup.
- `pdeathsig.c`, `session-reaper.c`: small helpers that stand in for systemd's process supervision.
- `polkit-omarchy.rules`, `pulse-client.conf`: system configuration.
- `freebsd/pkgmap`, `freebsd/pkg.sh`: Arch package names mapped to FreeBSD ports, for Omarchy's install commands.

Files carry `%%PREFIX%%`, `%%LOCALBASE%%` and `%%DATADIR%%` placeholders, which the port fills in. Changes to Omarchy's own files stay patches in the port.

Releases use [semantic versioning](https://semver.org) on their own; the port records which Omarchy release each one is for.

This is not an official Omarchy project.

## Bluetooth audio development

The native Bluetooth backend detects the A2DP Audio Sink service and starts
FreeBSD's base `virtual_oss` with `audio/virtual_oss_bluetooth`. The desktop
account creates a PipeWire OSS adapter named `daemonarchy.bluetooth`, which
appears in the normal audio output selector. Connecting selects it; disconnect,
forget and power-off remove it. The last connected backend is restored at
login without overriding a different saved output choice. HID-only devices
keep their existing path. No Linux/BlueZ service is involved.

The intended profile is stereo A2DP/SBC playback, with one Bluetooth output
active at a time. Microphone/HFP, AAC and simultaneous Bluetooth outputs are
not implemented. Backend diagnostics are root-only at
`/var/run/omarchy-bluetooth/audio.log`.

`bash tests/bluetooth-audio.sh` checks HID isolation, A2DP detection, startup
failures and user-session routing. On FreeBSD, run
`bash tests/bluetooth-audio-native.sh` as the logged-in desktop user with sudo
available and `virtual_oss_bluetooth` installed. It exercises real virtual OSS,
PipeWire default-output selection, a PCM write and cleanup, replacing only
the Bluetooth transport with `/dev/null`. This bridge test passed on the
selected October 12 snapshot; it does not qualify radio audio. Real headset
pairing, playback/volume, disconnect/reconnect and reboot tests remain pending.

Daemonarchy installations expose `daemonarchy` as the desktop command center
(`daemonarchy --help`, `daemonarchy commands`, `daemonarchy update`). Its
routes and help use Daemonarchy's name while retaining the upstream command
metadata and internal `omarchy-*` binaries. `daemonarchy version` reports the
installed Daemonarchy package version. The upstream router stays available
for compatibility.

`daemonarchy wifi enterprise 'Network name'` configures PEAP/MSCHAPv2 or
EAP-TLS using a trusted CA and authentication-server DNS domain. The desktop
panel opens that form for unfamiliar enterprise networks. Passwords travel
through stdin and the private supplicant socket; certificate imports and
profile files are root-only. The same helper validates and transfers the live
installer's enterprise profile to the target. Native profile/parser and
rollback tests are included; real access-point/EAP and reboot qualification
remain separate acceptance requirements.

The FreeBSD browser launcher uses XDG desktop application lookup, including
`/usr/local/share/applications`, and defaults to `chromium-browser.desktop`.
First-session setup supplies missing MIME defaults without overwriting user
choices. The stock local-Docker launcher and Docker setup menu entries are
omitted: this desktop configures neither a Docker VM nor a remote engine.

For desktop policy tests, set `OMARCHY_TEST_ROUTER` to Omarchy's upstream
`bin/omarchy` (or use the installed `/usr/local/bin/omarchy`) and run
`python3 -m unittest discover -s tests -v`.
