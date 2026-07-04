# HIDE

HIDE is a local privacy tool that routes traffic through Tor and applies a set of system-level leak protections.

It is meant for people who want a stricter Tor setup than a browser alone: DNS leak protection, a kill switch, hardened browser settings, telemetry blocking, UTC timezone, bridge rotation, and a quick way to undo the network changes if something goes wrong.

HIDE changes real system settings. Read this first, and use the dry run if you are not sure.

## What HIDE Does

When installed, HIDE:

- installs or finds Tor and obfs4proxy
- writes a Tor config with isolated SOCKS ports and obfs4 bridge support
- routes DNS through Tor where supported
- blocks direct DNS fallback
- adds a kill switch so traffic stops if Tor is down
- hardens Firefox, Chrome, Chromium, and Brave settings where supported
- blocks common telemetry domains in the hosts file
- randomizes hostname and MAC address where the OS and hardware allow it
- syncs time over Tor and sets the timezone to UTC
- rotates Tor circuits and bridges
- writes an integrity manifest for the project files
- installs background services so protection starts again after reboot

Some protections are best-effort. For example, MAC randomization can fail on some Windows network drivers, and hostname changes may require a reboot.

## Install

### macOS and Linux

Open Terminal:

```bash
git clone https://github.com/plastral/Hide.git
cd Hide
chmod +x bootstrap.sh
sudo ./bootstrap.sh
```

### Windows

Open PowerShell or Command Prompt as Administrator:

```powershell
git clone https://github.com/plastral/Hide.git
cd Hide
.\install.bat
```

If you do not have Git, download the ZIP from GitHub, extract it, then right-click `install.bat` and choose **Run as administrator**.

## Run

macOS and Linux:

```bash
sudo python3 hide.py
```

Windows, from an Administrator shell:

```powershell
python hide.py
```

The menu:

```text
[1] Install
[2] Remove
[3] Reinstall
[4] Status
[5] Private Browser
[6] Dry Run
[7] Rescue
[8] Capabilities
[q] Quit
```

For command-line help:

```bash
python3 hide.py --help
```

## Capability Report

Before installing, you can ask HIDE what it can support on the current machine.

```bash
python3 hide.py --capabilities
```

On Windows:

```powershell
python hide.py --capabilities
```

This does not change system settings. It reports package manager availability, service support, firewall method, DNS method, browser policy support, and best-effort areas such as MAC randomization.

## Dry Run

Dry run prints what HIDE would do without changing system settings.

```bash
python3 hide.py --dry-run install
python3 hide.py --dry-run remove
python3 hide.py --dry-run rescue
python3 hide.py --dry-run status
python3 hide.py --dry-run capabilities
```

On Windows, use `python` instead of `python3`.

## Emergency Restore

If your network is broken or Tor is stuck, run rescue.

macOS and Linux:

```bash
sudo python3 hide.py --rescue
```

Windows, from an Administrator shell:

```powershell
python hide.py --rescue
```

Rescue does not uninstall HIDE. It only tries to restore normal networking:

- stops HIDE background services
- stops Tor
- opens the firewall
- removes HIDE DNS rules
- restores DNS settings
- removes the HIDE hosts-file block
- re-enables system time sync
- restores the timezone if a backup exists

After rescue, you can run the menu again and choose Remove for a full uninstall.

## Status

Status checks the main things that matter:

- Tor process is running
- SOCKS proxy is reachable
- Tor bootstrap completed
- firewall and DNS rules are present
- telemetry block is present
- integrity manifest exists
- timezone is UTC
- macOS FileVault and SIP checks, where available

Run it from the menu or directly:

```bash
python3 hide.py --dry-run status
```

For the live check, use menu option `[4] Status`.

## Private Browser

The private browser option opens a separate browser profile routed through Tor. It does not use your normal profile, bookmarks, cookies, or extensions.

Supported browsers:

- Firefox
- Chrome
- Chromium
- Brave

Tor must already be running for this to work.

## Remove

Remove unloads HIDE services and reverses the system changes HIDE knows about:

- firewall rules
- DNS redirects
- hosts-file telemetry block
- browser policies
- timezone backup
- app support files and logs

Use the normal Remove option when you want a clean uninstall. Use Rescue only when you need the network back quickly.

## Things To Know

- Your ISP can still see that you are connecting to Tor or Tor bridges.
- HIDE does not make unsafe browsing safe.
- Local network traffic, such as printers and local file shares, is not the goal of this tool.
- Some protections need administrator/root access.
- Some Windows changes may need a reboot to fully take effect.
- If a hardware driver refuses MAC randomization, HIDE will skip it rather than breaking the adapter.

## Files

```text
hide.py                  menu, install, remove, status, rescue
core/                    Tor setup, bootstrap, control, kill switch
privacy/                 DNS, telemetry, MAC, hostname, timezone, NTP, padding
browser/                 browser policy and WebRTC hardening
system/                  platform adapters, services, logging, integrity
security/                macOS SIP/FileVault checks
launchd/                 macOS service templates
```

## License

MIT

made by plastral
