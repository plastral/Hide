# HIDE

Your internet connection, locked down. HIDE routes everything through Tor, kills tracking at the source, and puts a hard stop on any data leaving your machine that shouldn't be.

Made by plantiral with love.

---

## What actually happens when you run it

The moment you install HIDE, it quietly takes over your network stack. Your traffic gets tunnelled through Tor using obfs4 bridges — bridges that make Tor look like normal HTTPS traffic so it slips past censorship and deep packet inspection. Your browser gets reconfigured to kill WebRTC leaks. Your MAC address and hostname get randomised. Every Apple, Google, and Microsoft telemetry domain gets blocked at the system level. Your clock syncs anonymously through Tor. A kill switch sits in the background watching — the second Tor drops, all traffic stops dead rather than falling back to your real IP.

It all runs as a background service that starts on boot. You don't have to think about it once it's set up.

---

## Getting started

**macOS and Linux** — open Terminal

```bash
curl -fsSL https://github.com/plastral/Hide/archive/refs/heads/main.tar.gz | tar -xz && cd Hide-main && chmod +x bootstrap.sh && sudo ./bootstrap.sh
```

**Windows** — open Command Prompt as Administrator and paste this single line

```
powershell -ExecutionPolicy Bypass -Command "Invoke-WebRequest https://github.com/plastral/Hide/archive/refs/heads/main.zip -OutFile $env:TEMP\hide.zip; Expand-Archive $env:TEMP\hide.zip -DestinationPath $env:TEMP\Hide -Force; Set-Location $env:TEMP\Hide\Hide-main; .\bootstrap.ps1"
```

No git required on either platform. Python is installed automatically if needed. On macOS, Homebrew is set up too.

Once the bootstrap finishes, the HIDE menu appears and you choose what to do from there.

---

## The menu

Once installed, just run:

```bash
sudo python3 hide.py
```

```
[1]  Install
[2]  Remove
[3]  Reinstall
[4]  Status
[5]  Private Browser
[0]  Exit
```

**Install** sets everything up from scratch. **Remove** undoes every single change — firewall rules, browser settings, hostname, timezone, all of it — and puts your machine back exactly how it was. **Status** shows you what's running and whether Tor is healthy. **Private Browser** opens a hardened browser window with its own isolated Tor connection.

---

## What it protects you from

| What | How |
|------|-----|
| IP tracking | All traffic exits through Tor across three isolated SOCKS ports |
| Censorship and DPI | obfs4 bridges disguise Tor as normal HTTPS |
| Network drop leaks | Kill switch blocks everything if Tor goes offline |
| DNS leaks | DNS is forced through Tor's local resolver, system fallback is blocked |
| WebRTC leaks | WebRTC disabled in Firefox and all Chromium-based browsers |
| Browser fingerprinting | Canvas, WebGL, battery, geolocation, and device APIs all hardened |
| MAC tracking | Fresh randomised MAC address on every install |
| Hostname exposure | Machine name replaced with a random word combination |
| Telemetry | Hundreds of tracking domains blocked at the hosts file level |
| Clock fingerprinting | System time synced anonymously via Tor, locked to UTC |
| Traffic analysis | Randomised cover traffic sent at irregular intervals |
| Circuit tracing | Tor circuits rotated every 10 minutes automatically |
| Guard discovery attacks | Entry guards hardened and given extended lifetimes |
| Jurisdiction exposure | High-risk exit node countries excluded by default |
| File tampering | SHA-256 integrity manifest watches every file |
| Log forensics | Logs securely overwritten with multiple passes before deletion |

---

## Good to know

- **Your ISP can still see that you're using Tor.** HIDE protects what you do online, not the fact that you're using it. The obfs4 bridges make Tor harder to block, but your ISP will still see encrypted traffic going somewhere.
- **Local network traffic is not routed through Tor.** Things like printers, NAS drives, and local services still work normally. Only traffic going out to the internet is affected.
- **Video calls on your local network are unaffected.** STUN and WebRTC are only blocked for public internet endpoints, not for LAN.
- **You need to run as root.** Firewall rules and MAC randomisation require elevated privileges — there's no way around this.
- **Uninstalling is clean.** Every change HIDE makes is tracked and reversed on remove. Your original timezone, hostname, browser settings, and network state all come back.

---

## License

MIT
