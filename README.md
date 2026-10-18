# 🌌 Neon Uploader

Flask file uploader, browser and downloader running on **Raspberry Pi or Linux**, with a **Windows 11 x64 client for one-click Opera GX login**. No Python or additional modules needed on Windows. The Pi manages its own Python dependencies through `run.py`.

## File management

- Drag-and-drop multi-file upload; duplicate names get `_001` etc.
- Browse directories, search, select all, rename, create folders and permanently delete with confirmation.
- Download one file or multiple files/folders as ZIP.
- Right-click context menu, keyboard selection and responsive interface.

## Raspberry Pi: server setup

```bash
git clone https://github.com/ultros/neon-uploader.git
cd neon-uploader
python3 run.py
```

Choose **`0.0.0.0`** for Host to allow other devices on your LAN, default port `8080` and an upload folder. Port `8080` must be permitted through the Pi's firewall. Find the Pi's LAN IP with `hostname -I`. The service runs until you close its terminal. For unattended Pi service, configure a systemd unit separately.

On the first network-enabled run, the Pi generates a secure random **persistent password** and saves it in `~/.config/neon-uploader/access-token` (mode `0600` on Linux). Its value is also printed to the Pi terminal so you can enter it once on Windows. On subsequent restarts, the same password is reused. Keep this file private and back it up if you need to preserve Windows credentials across Pi replacement. **Never put the password in the public GitHub repository.** You may instead supply your own `NEON_ACCESS_TOKEN` environment variable before starting the Pi app.

The server's remote username is **`neon`**. Connecting directly via `http://PI-LAN-IP:8080/` with Opera GX's ordinary HTTP authentication prompt remains supported.

## Windows 11 x64: automatic Opera GX login

Copy **`neon-client.bat` and `neon-client.ps1`** to the same folder on your Windows computer. Do **not** run the Pi Python server on Windows. To open the app:

1. Double-click **`neon-client.bat`**. On first use, enter the Pi URL, for example `http://192.168.1.50:8080`, and then username `neon` and the password from the Pi terminal.
2. If using plain HTTP, confirm the one-time trusted-LAN security warning. The client saves the address under `%APPDATA%\NeonUploader\pi-url.txt` and a **DPAPI-encrypted Windows-user credential** under `%APPDATA%\NeonUploader\credential.xml`.
3. The launcher asks the Pi for a short-lived, one-use browser sign-in ticket, opens **Opera GX**, and signs the browser in automatically. On subsequent launches, no prompt is needed unless your Pi password has changed or your Windows credential store is unavailable.

To change the saved URL/password:

```bat
neon-client.bat -Setup
```

To **enable automatic opening whenever you sign in to Windows**, run once:

```bat
neon-client.bat -InstallStartup
```

To remove that Startup shortcut:

```bat
neon-client.bat -RemoveStartup
```

Opera GX is detected at the usual `%LOCALAPPDATA%\Programs\Opera GX` and `%ProgramFiles%\Opera GX` installations. If it isn't found, the launcher falls back to your default browser. All Windows actions use built-in Windows PowerShell 5.1 and DPAPI; the Windows launcher requires no pip installs, Python runtime, drivers, Opera extensions, browser debugging ports, or hard-coded passwords. The Windows Startup shortcut points to the `.bat` file's location, so keep the two scripts in that folder.

### How browser sign-in works

The client sends HTTP Basic credentials directly to the Pi only to request a short-lived login ticket through `POST /api/auth/ticket`. The ticket is valid for 90 seconds and one redemption. Opera GX receives `http(s)://PI/__neon_login#ticket=...`: the fragment after `#` stays within the browser and is not sent in the HTTP GET request or ordinary server access logs. The login page clears the fragment and exchanges the ticket for an **HttpOnly, SameSite=Strict** browser session cookie, which expires after 12 hours. Tickets and browser sessions are held only in Pi server memory, and are bound to the original client IP. A Pi server restart invalidates old browser sessions, but the Windows launcher can generate fresh ones automatically using its encrypted saved credentials.

The original HTTP Basic login also remains supported for remote browsers that are not using the Windows launcher.

### Network security

**Password authentication prevents casual unauthenticated connections but does not encrypt network traffic.** HTTP Basic authentication and session cookies are exposed to interception over plain HTTP; a trusted LAN cannot guarantee protection from a compromised router/device or an on-path attacker. For any untrusted network, use HTTPS via a trusted reverse proxy or a VPN (such as WireGuard/Tailscale), and set up appropriate firewall rules. Never forward port 8080 directly to the public Internet. Auto-login does not grant anonymous network access. No tokens are sent to third-party services.

If the Pi is behind a reverse proxy, ensure ticket issuance and browser ticket redemption appear to Flask from the same client IP, or adjust the deployment accordingly. This tool does not trust unsolicited forwarding headers. Session cookies use `Secure` only when Flask sees the request as HTTPS; configure trusted proxy security and TLS correctly.

## Python dependencies and tests

On the Pi, `run.py` creates an isolated `.venv`, checks `requirements.txt`, and installs only missing or broken dependencies. Later starts skip pip when the environment is healthy. Run tests on a machine with Flask installed using:

```bash
python3 -m unittest discover -p 'test_*.py'
```

## HTTP API

| Method | URL | Meaning |
| --- | --- | --- |
| GET | `/api/files?path=...` | List directory |
| POST | `/upload` | Multi-file upload |
| GET | `/api/download?path=...` | Download file |
| POST | `/api/download-zip` | Download selections as ZIP |
| POST | `/api/folders` | Create a folder |
| POST | `/api/rename` | Rename file/folder |
| POST | `/api/delete` | Permanently delete selected items |
| POST | `/api/auth/ticket` | Issue one-use browser ticket after HTTP Basic authentication |
| GET/POST | `/__neon_login` | Public bootstrap page/one-use ticket exchange; no file data |

## License

See [LICENSE](LICENSE).
