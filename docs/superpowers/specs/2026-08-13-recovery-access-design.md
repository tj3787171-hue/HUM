# Recovery access and Chromebook boot-unit design

Date: 2026-08-13

## Goal

Give Penguin (this Chromebook), the laptop, and BELL a name-based way to find
SSH/desktop paths when BELL’s IP is unknown, and give the Chromebook a
**exact unit/timer list** for the services that crash boot: `binfmt_misc` and
`fwupd*`, plus `plymouth-quit-wait.service`.

## Hosts

| Name | What it is | Address |
|---|---|---|
| Penguin | Chromebook Crostini (this client) | `192.168.68.52` (planned) |
| BELL | HP Pavilion Slimline s5000, serial `MXX116042G`, product `BV627AA#ABA` | unknown; Docker identity |
| Kali / HUM | Kali desktop host | `192.168.68.53` (inventory) |
| Cloud agent | Writes HUM only | no LAN packets |
| ubuntu-start | Known-working HTTPS start | `https://10.10.2.2:8443` |

## Architecture

Stable identity is `recovery-cursor-agent.service` and its Docker objects, not
DHCP. Cloud commits `scripts/hum-recovery-access.sh`. The on-host recovery unit
pulls HUM and runs it. Penguin/laptop run the same helper read-only.

## Components

- `scripts/hum-recovery-access.sh` — discover, boot-units, plymouth, ssh-hint
- `scripts/hum-recovery-access.units` — exact unit/timer catalog
- Inventory/matrix row for BELL with `access: docker-identity` and empty IP

## Data flow

1. `discover` reads systemd + Docker + `docker0` (no subnet scan).
2. `boot-units` prints each cataloged unit’s `LoadState`/`ActiveState`.
3. `plymouth-start` / `plymouth-stop` touch only `plymouth-quit-wait.service`.
4. `ssh-hint` prints a command from discover output; it does not copy files.
5. `start-hint` / `discover` print `https://10.10.2.2:8443` as the current Ubuntu-start URL.

## Safety

- Never start, enable, mask, or query `institute-hikvision-probe.service`.
- Never copy personal-use files off BELL/Kali.
- `kauditd_printk` is reported from dmesg/journal only (not “disable audit”).
- `binfmt_misc` is reported only in v1 (masking it can break all exec).
- Masking `fwupd*` requires `--i-am-on-chromebook-penguin` and `--mask-fwupd`.
- Cloud VM install must not mask fwupd or binfmt on the Cursor environment.

## Out of scope

- Compose rewrite of the already-running recovery unit
- Hard-coded BELL IP
- Hikvision/camera probing
- Personal-file backup or off-host use
