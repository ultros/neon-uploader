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

## Quick start

Requires Python 3.9+.

```bash
git clone https://github.com/ultros/neon-uploader.git
cd neon-uploader
python3 -m pip install -r requirements.txt
python3 neon-uploader.py
```

Press Enter to use `127.0.0.1`, port `8080`, and an `uploads` folder. Open **http://127.0.0.1:8080/**. Uploaded files remain on disk inside the chosen upload folder.

## Remote access / security

**This is a file manager, including permanent deletion. Do not put an unauthenticated instance on the public internet.** The interactive launcher defaults to loopback only and refuses a non-loopback host without an access token.

For access over a LAN or through a reverse proxy, set a long secret before starting the application:

```bash
# Linux/macOS
export NEON_ACCESS_TOKEN='replace-this-with-a-long-random-secret'
python3 neon-uploader.py
```

```powershell
# PowerShell
$env:NEON_ACCESS_TOKEN = 'replace-this-with-a-long-random-secret'
python neon-uploader.py
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
