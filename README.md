# 🌌 Neon Uploader

A lightweight, cyberpunk-styled Flask uploader **and file manager**. Upload, browse, organize, and retrieve your own files in a responsive browser interface. It retains the original single-file application deployment.

## Features

- Drag-and-drop, queued multi-file upload into the folder you're browsing.
- Browse folders with breadcrumbs; see filenames, modification times, and file sizes.
- Search within the current folder and refresh the list.
- Checkboxes, **select all visible**, partial-selection indicator, and keyboard Ctrl/Cmd+A when the file browser is focused.
- Download individual files or selected files/folders together in a ZIP archive.
- Right-click context menu: open folder, download, copy filename, copy file download URL, rename, or delete.
- Create folders, rename entries, and delete multiple items with an explicit confirmation.
- Automatically append `_001`, `_002`, etc. to uploads if filenames collide.
- Server-side path validation blocks traversal, symbolic links, root deletion and accidental overwrites.
- No frontend build process or database required.

## Quick start: automatic dependency installation

**Requires Python 3.9+** (and Python's standard `venv`/`ensurepip` support).
Python itself must already be installed; there is no need to manually run pip.

```bash
git clone https://github.com/ultros/neon-uploader.git
cd neon-uploader
python3 run.py
```

- **Windows:** Double-click `run.bat` or run `py -3 run.py`.
- **Linux/macOS:** Run `sh run.sh` or `python3 run.py`.
- **Existing command:** `python neon-uploader.py` also invokes the bootstrapper automatically when launched directly.

On the **first launch**, the runner creates an isolated `.venv` next to the app and installs the Python packages in `requirements.txt` (Flask and its dependencies, including Werkzeug). On subsequent launches, it checks the already-installed packages and versions; **when all requirements are present and valid, installation is skipped entirely**. If `requirements.txt` changes or packages become missing/broken, pip runs again. No admin privileges, system-wide pip installs, or frontend build tools are required.

If the first install fails (for example, because network access is unavailable), the app stops with an actionable error. On Debian/Ubuntu, a Python installation lacking `venv` may require installing `python3-venv` using your system package manager. The launcher does not silently install operating-system packages or bypass Python's package-management protections.

Press Enter for the default host `127.0.0.1`, port `8080`, and `uploads` folder. Open **http://127.0.0.1:8080/**. Uploaded files are kept on disk. The local `.venv` and `uploads` directory are gitignored.

## Remote access / security

**This is a file manager, including permanent deletion. Do not put an unauthenticated instance on the public internet.** The interactive launcher defaults to loopback only and refuses a non-loopback host without an access token.

For access over a LAN or through a reverse proxy, set a long secret before starting the application:

```bash
# Linux/macOS
export NEON_ACCESS_TOKEN='replace-this-with-a-long-random-secret'
python3 run.py
```

```powershell
# PowerShell
$env:NEON_ACCESS_TOKEN = 'replace-this-with-a-long-random-secret'
python run.py
```

Choose `0.0.0.0` as host only when you actually need network access. Your browser will ask for **username `neon`** and the secret token as its password. HTTP Basic authentication must be used **behind HTTPS** when accessed over an untrusted network. Prefer a VPN or an HTTPS reverse proxy with additional rate limiting. Treat copied download links as authenticated, not public sharing links. The development server is intended for trusted/self-hosted use, not production public hosting.

## Browser behavior

- **Check all** applies to the rows currently visible after filtering. Hidden selected rows remain selected; the selected count is displayed.
- Click a folder name to open it or click a filename to download it. For multiple files or any folder, **Download selected** creates a ZIP.
- Right-click a row to access item-specific actions. Right-clicking an unselected row selects that row; if it's already selected, the existing selection is kept.
- Deletion is permanent and recursively deletes selected folders after browser confirmation. No recycle bin is provided.
- File selections reset when moving to another directory. Upload queue entries remain until uploaded or removed.
- Symbolic links are deliberately not shown, followed, downloaded, or modified.

## API (same-origin; protected by optional access token)

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/files?path=folder` | List the current folder |
| POST | `/upload` (`multipart/form-data`, `path` and `files`) | Upload |
| GET | `/api/download?path=folder/file.txt` | Download one file |
| POST | `/api/download-zip` (`{"paths":[...]}`) | Download ZIP |
| POST | `/api/folders` (`{"path":"folder","name":"new"}`) | Create folder |
| POST | `/api/rename` (`{"path":"folder/file","name":"renamed"}`) | Rename file/folder |
| POST | `/api/delete` (`{"paths":[...],"confirm":true}`) | Permanently delete |

JSON errors use an `error` field. To protect against oversized archive selections, ZIP creation accepts up to 1,000 selected entries and 10,000 contents.

## License

See [LICENSE](LICENSE). Existing license retained.
