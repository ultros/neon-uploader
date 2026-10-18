# 🌌 Neon Uploader

Flask file uploader, browser and downloader running on **Raspberry Pi or Linux**, with a **Windows 11 x64 client for one-click Opera GX login**. No Python or additional modules needed on Windows. The Pi manages its own Python dependencies through `run.py`.

## File management

- Drag-and-drop multi-file upload; duplicate names get `_001` etc.
- Browse the **entire configured shared folder tree** (including nested directories and hidden files), search the current folder, select all, rename, create folders and permanently delete with confirmation.
- Download one file or multiple files/folders as ZIP.
- Right-click context menu, keyboard selection and responsive interface.

## Windows 11 native Pi Share Explorer (new)

**You no longer have to use Opera GX to browse the Pi.** The Windows client now opens a **native Windows graphical file browser** by default. It uses the Pi server API: no SMB mapping, mounted drive, new Python installation or browser extension required.

On Windows, keep **`neon-client.bat`, `neon-client.ps1` and `neon-browser.ps1` together**. Double-click `neon-client.bat` (or `neon-browse.bat`). The first time, enter the Pi address and login as `neon` using the password printed on the Pi. The password is saved encrypted for your Windows account using DPAPI. Later launches open the native file browser without another login prompt.

- Left: expandable Pi share folder tree, starting at **Share**.
- Top: **Back / Up / Share / Refresh**, editable share-relative folder path and **Go**.
- Right: folders and files with **Name / Type / Size / Modified** columns, sort by clicking headings, search/filter, multiselection and **Select All** checkboxes.
- **Download** saves a selected file to a Windows path of your choosing. **Download ZIP** saves multiple selected files or whole Pi folders as one archive.
- Double-click a folder to enter it; double-click a file to download. Right-click items for **Open/Download, Download ZIP, Rename, Delete**.
- **New Folder, Rename, Delete** perform those operations on the Pi only after server authentication. Delete requires a confirmation and is permanent.
- The bottom bar shows the actual **Pi share root** and server version so you can immediately spot a wrong or empty directory. An older Pi service lacking share metadata causes a visible error rather than a misleading empty file list.
- **Open in Opera GX** opens the original web file manager via the Windows auto-login flow. You can also run `neon-client.bat -Opera` to open Opera directly, instead of the native window.

### Launch commands on Windows

```bat
neon-client.bat            REM native Windows browser (default)
neon-browse.bat            REM same native browser, desktop-friendly shortcut
neon-client.bat -Opera     REM automatic Opera GX login to Pi web browser
neon-client.bat -Setup     REM change saved Pi URL / username and password
neon-client.bat -InstallStartup   REM keep Opera auto-login at Windows sign-in
```

**Important:** The native browser only exposes the Pi's **configured share root and its descendants**. It is not a file manager for the Windows computer and cannot inspect the Pi's `/etc`, `/home`, or other unrelated directories unless you intentionally choose those as the share root on the Pi. The Pi user running Neon must have filesystem access. On the Pi, update and restart the service with the intended directory:

```bash
cd neon-uploader
git pull origin main
python3 run.py --host 0.0.0.0 --port 8080 --share-root /actual/existing/share
```

The folder must already exist, and a USB/NFS/SMB share must be mounted before the server starts. Do not set the root to `/` without explicitly accepting the consequences of granting remote file-management access to the whole Pi. HTTP transfers are **not encrypted**; use HTTPS or a VPN outside a fully trusted local network.

## Standard download file browser (version 1.5)

The **File browser** is the first section of the Opera GX web application, above the upload panel. It uses a familiar Explorer-style layout with a folder sidebar, **Back / Forward / Up / Share**, a share-relative address bar, clickable folder names and breadcrumbs, sortable **Name / Size / Modified** columns, search filtering, individual **Download** buttons, checkboxes, and **Download selected** for ZIP archives. Right-click actions, uploads, rename, delete and folder creation are preserved. On narrow screens the folder sidebar stacks above the file list.

- **To open a folder:** click its name or **Open** button, or type `Documents/Invoices` into the address bar and press Enter.
- **To download one file:** click its **Download** button, or click the filename.
- **To download many files or an entire folder:** select the checkboxes and click **Download selected**. A ZIP is generated on the Pi for you to save on Windows.
- **To sort:** click Name, Size or Modified. Click again to reverse direction. Folders stay first.
- **To go back:** use Back or Alt+Left; **Up** takes you to the parent within the share. **Share** returns to its root.
- **To verify the correct Pi share:** the browser reports `Pi share: /actual/server/path · version 1.5.0`. A screen still showing only `Home` or `Local file workspace` means you are connected to an old running server process.

**Start from the real, existing share, not a new uploads directory:**

```bash
cd neon-uploader
git pull origin main
python3 run.py --host 0.0.0.0 --port 8080 --share-root /path/to/your/existing/share
```

The selected root is saved in `~/.config/neon-uploader/share-root`; future runs reuse it. The startup script refuses to manufacture a missing directory, and will not silently change shares. To find the real Samba share path, check `testparm -s` or `/etc/samba/smb.conf` on the Pi. If it is a USB/SMB/NFS *mountpoint*, set `NEON_REQUIRE_MOUNT=1` to fail startup when the mount is offline, instead of showing an empty underlying directory. **The program never wipes the share at startup; it will only delete files when you explicitly use Delete.**

## Raspberry Pi: server setup

```bash
git clone https://github.com/ultros/neon-uploader.git
cd neon-uploader
python3 run.py
```

Choose **`0.0.0.0`** for Host to allow other devices on your LAN, default port `8080`, and **enter the absolute path to your Raspberry Pi shared directory** (for example `/srv/share` or `/mnt/storage/share`) when prompted for **Share filesystem root**. The browser begins at that location and navigates every subdirectory beneath it, including dotfiles. It can upload/download, create folders, rename and delete anywhere inside the share where the Pi server account has permission. Paths above or outside this root are rejected; directory symlinks are not followed.

The Pi remembers your chosen root at `~/.config/neon-uploader/share-root` and offers it again on future starts. To change it, enter a different absolute directory at the prompt. For **unattended/server startup** set `NEON_SHARE_ROOT` instead of answering the prompt:

```bash
NEON_SHARE_ROOT=/srv/share python3 run.py
```

The directory must already exist for explicit share paths. The launcher deliberately refuses to silently create a missing share directory (which could be a typo or an unavailable mount). If the share is mounted over NFS, SMB/CIFS, or USB storage, mount it **before** starting Neon Uploader. `uploads` remains the first-run fallback if you do not select a share root. Port `8080` must be permitted through the Pi's firewall. Find the Pi's LAN IP with `hostname -I`. The service runs until you close its terminal. For unattended Pi service, configure a systemd unit separately.

On the first network-enabled run, the Pi generates a secure random **persistent password** and saves it in `~/.config/neon-uploader/access-token` (mode `0600` on Linux). Its value is also printed to the Pi terminal so you can enter it once on Windows. On subsequent restarts, the same password is reused. Keep this file private and back it up if you need to preserve Windows credentials across Pi replacement. **Never put the password in the public GitHub repository.** You may instead supply your own `NEON_ACCESS_TOKEN` environment variable before starting the Pi app.

The server's remote username is **`neon`**. Connecting directly via `http://PI-LAN-IP:8080/` with Opera GX's ordinary HTTP authentication prompt remains supported.

The browser's breadcrumb starts at **Share**. Clicking into a directory navigates further down the Pi's filesystem beneath the share; clicking **Share** returns to its root. All file operations use share-relative paths, not absolute Pi paths. The Windows launcher does not need changes to use this capability.

## Windows 11 x64: setup and optional Opera GX login

Copy **`neon-client.bat`, `neon-client.ps1`, and `neon-browser.ps1`** to the same folder on your Windows computer. `neon-browse.bat` is an optional convenience shortcut. Do **not** run the Pi Python server on Windows. To open the native browser:

1. Double-click **`neon-client.bat`**. On first use, enter the Pi URL, for example `http://192.168.1.50:8080`, and then username `neon` and the password from the Pi terminal.
2. If using plain HTTP, confirm the one-time trusted-LAN security warning. The client saves the address under `%APPDATA%\NeonUploader\pi-url.txt` and a **DPAPI-encrypted Windows-user credential** under `%APPDATA%\NeonUploader\credential.xml`.
3. The launcher opens the **native Pi Share Explorer** directly and authenticates API requests using your Windows-encrypted saved credentials. Use **Open in Opera GX** inside the window or `neon-client.bat -Opera` for the browser auto-login flow. Subsequent launches do not prompt again unless the saved Pi credentials change.

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
| GET | `/api/files?path=...` | List any directory within configured share root |
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
