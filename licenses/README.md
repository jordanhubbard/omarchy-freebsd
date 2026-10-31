# Licenses in omarchy-freebsd

This repository is part of the Daemonarchy project (see `../LICENSE` and the repository map in HACKING.md of https://github.com/jordanhubbard/daemonarchy). Daemonarchy-original work here is under BSD-2-Clause; files derived from Omarchy keep Omarchy's MIT license and its upstream copyright notice.

Daemonarchy-original work carries the license terms only, with no copyright notice. Third-party and upstream-derived components keep the upstream notices, which are retained as their licenses require.

This list makes no claim that the licenses of transitive dependencies are represented. It lists the components of this repository and the licenses verified for them, with the evidence for each. Packages and sources that other repositories take from upstream carry their own license metadata, which is not reproduced here unless it is listed below.

## What this repository is

omarchy-freebsd is the repository that the `x11-wm/omarchy` port in daemonarchy-ports builds from, as a second distfile beside Omarchy itself (`GH_TUPLE= jordanhubbard:omarchy-freebsd:<commit>:freebsd` in `x11-wm/omarchy/Makefile`, where Omarchy itself is `GH_ACCOUNT= basecamp`). It was created by "Initial import from the x11-wm/omarchy port's files" (commit 1e6b785) and its previous `LICENSE` was the MIT text with two notice lines, `Copyright (c) David Heinemeier Hansson` and a Daemonarchy line. It is a companion to Omarchy, not a fork of Omarchy's history. Some commands in `freebsd-bin/` are FreeBSD rewrites of Omarchy commands of the same name, which is where Omarchy-derived content is.

## Table

| Component or path | License | File under licenses/ | Upstream notice and evidence |
|---|---|---|---|
| `freebsd-bin/*` files listed under "Omarchy-derived commands" below | MIT | `MIT.txt` | `Copyright (c) David Heinemeier Hansson`, from Omarchy's own `LICENSE`. Evidence: each file has an Omarchy command of the same name in `bin/` of the Omarchy checkout; line comparison shows shared lines for all but `omarchy-launch-browser` (name match only). Listing these as derived is a conservative reading and needs owner confirmation. |
| All other files: `freebsd-bin/` files with no Omarchy namesake (`freebsd-bin/omarchy-agent-install-linux`, `freebsd-bin/omarchy-bluetooth`, `freebsd-bin/omarchy-dev-sync`, `freebsd-bin/omarchy-wifi`, `freebsd-bin/omarchy-wifi-enterprise`), `compat/*`, `systemd-user/*`, `freebsd/*`, `seed-user`, `profile-omarchy.sh`, `env-freebsd`, `audio-default`, `pulse-client.conf`, `polkit-omarchy.rules`, `pdeathsig.c`, `session-reaper.c`, `tests/*`, `README.md` | BSD-2-Clause | `BSD-2-Clause.txt` | Daemonarchy-original, on the operator's instruction. Evidence: no file of that name in Omarchy; git history shows only Jordan Hubbard / jkh as author. No license header or SPDX tag was found in any file. |
| `freebsdize.in` | BSD-2-Clause, UNDETERMINED: needs owner review | `BSD-2-Clause.txt` | It rewrites Omarchy sources; the script is original text but encodes Omarchy path knowledge. No Omarchy namesake exists. |
| Anything not listed above | BSD-2-Clause if it has no license header of its own | `BSD-2-Clause.txt` | Rule for unlisted files: a file with its own license header or SPDX tag is under that license; otherwise it is Daemonarchy-original. |

## Omarchy-derived commands (MIT)

- `freebsd-bin/omarchy-battery-present`
- `freebsd-bin/omarchy-bluetooth-device`
- `freebsd-bin/omarchy-bluetooth-power`
- `freebsd-bin/omarchy-cmd-terminal-cwd`
- `freebsd-bin/omarchy-dev-link`
- `freebsd-bin/omarchy-hw-laptop`
- `freebsd-bin/omarchy-hw-laptop-closed`
- `freebsd-bin/omarchy-launch-browser`
- `freebsd-bin/omarchy-launch-webapp`
- `freebsd-bin/omarchy-mise-install`
- `freebsd-bin/omarchy-network-status`
- `freebsd-bin/omarchy-pkg-add`
- `freebsd-bin/omarchy-pkg-aur-add`
- `freebsd-bin/omarchy-pkg-aur-install`
- `freebsd-bin/omarchy-pkg-drop`
- `freebsd-bin/omarchy-pkg-install`
- `freebsd-bin/omarchy-pkg-missing`
- `freebsd-bin/omarchy-pkg-present`
- `freebsd-bin/omarchy-pkg-remove`
- `freebsd-bin/omarchy-power-present`
- `freebsd-bin/omarchy-snapshot`
- `freebsd-bin/omarchy-system-stats`
- `freebsd-bin/omarchy-theme-set-browser-policy`
- `freebsd-bin/omarchy-update`
- `freebsd-bin/omarchy-update-analyze-logs`
- `freebsd-bin/omarchy-update-aur-pkgs`
- `freebsd-bin/omarchy-update-available`
- `freebsd-bin/omarchy-update-confirm`
- `freebsd-bin/omarchy-update-firmware`
- `freebsd-bin/omarchy-update-keyring`
- `freebsd-bin/omarchy-update-lock`
- `freebsd-bin/omarchy-update-orphan-pkgs`
- `freebsd-bin/omarchy-update-pacman-guard`
- `freebsd-bin/omarchy-update-pkg-prune`
- `freebsd-bin/omarchy-update-requires-free-space`
- `freebsd-bin/omarchy-update-restart`
- `freebsd-bin/omarchy-update-stay-awake`
- `freebsd-bin/omarchy-update-system-pkgs`
- `freebsd-bin/omarchy-update-time`
- `freebsd-bin/omarchy-version`
- `freebsd-bin/omarchy-version-channel`
- `freebsd-bin/omarchy-version-pkgs`

## Texts and their sources

- `BSD-2-Clause.txt`: the SPDX BSD-2-Clause text from spdx/license-list-data (commit 31846481de7ea17d92f2f46fad76abe58b2e9bb0, `text/BSD-2-Clause.txt`), with the template line `Copyright (c) <year> <owner>` removed on the operator's instruction, because no copyright holder is named for Daemonarchy-original work. The rest is unchanged.
- `MIT.txt`: byte-for-byte the `LICENSE` file of Omarchy (https://github.com/omacom/omarchy, formerly basecamp/omarchy; identical to the `LICENSE` at the head of that repository on 2026-10-31, checked via the GitHub API). It differs from the SPDX MIT template only in its notice line and whitespace.
