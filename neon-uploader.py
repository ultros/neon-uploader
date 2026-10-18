"""Neon Uploader: a small, self-hosted upload and file browsing application."""

import datetime
import os
import secrets
import shutil
import tempfile
import zipfile
from pathlib import Path

# CLI compatibility: direct `python neon-uploader.py` now uses the same
# isolated, install-if-needed launcher as `python run.py`.
if __name__ == "__main__" and os.environ.get("NEON_BOOTSTRAPPED") != "1":
    from run import main as launch
    raise SystemExit(launch())

from flask import Flask, abort, jsonify, render_template_string, request, send_file
from werkzeug.utils import secure_filename


MAX_SELECTION = 1000
MAX_ARCHIVE_FILES = 10000


def human_readable_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB", "TB")
    i = min(len(units) - 1, max(0, (size_bytes.bit_length() - 1) // 10))
    return f"{size_bytes / (1024 ** i):.2f} {units[i]}"


def generate_unique_filename(directory, filename):
    """Find a name that does not currently exist; exclusive creation is still required."""
    base, ext = os.path.splitext(filename)
    counter = 1
    name = filename
    while (Path(directory) / name).exists() or (Path(directory) / name).is_symlink():
        name = f"{base}_{counter:03d}{ext}"
        counter += 1
    return name


def valid_new_name(name):
    """Validate a single portable filename, preserving human-friendly spaces."""
    if (not isinstance(name, str) or not name or name in (".", "..")
            or len(name.encode("utf-8")) > 255 or name.strip(" .") != name
            or any(c in name for c in '/\\\0<>:"|?*')
            or any(ord(c) < 32 for c in name)):
        abort(400, description="Invalid name")
    return name


def create_app(upload_folder="uploads", access_token=None):
    """Factory makes routes testable without prompting for console input."""
    app = Flask(__name__)
    root = Path(upload_folder).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    token = access_token if access_token is not None else os.environ.get("NEON_ACCESS_TOKEN", "")

    def resolve_path(relative="", kind=None):
        if not isinstance(relative, str) or relative.startswith("/") or "\\" in relative:
            abort(400, description="Invalid path")
        parts = [] if not relative else relative.split("/")
        if any(part in ("", ".", "..") or "\0" in part for part in parts):
            abort(400, description="Invalid path")
        candidate = root
        for part in parts:
            candidate = candidate / part
            # No symlinks, including intermediate directories or a final file.
            if candidate.is_symlink():
                abort(403, description="Symbolic links cannot be accessed")
        if not candidate.exists():
            abort(404, description="File or folder not found")
        if kind == "file" and not candidate.is_file():
            abort(400, description="A file is required")
        if kind == "dir" and not candidate.is_dir():
            abort(400, description="A folder is required")
        return candidate

    def relative_name(path):
        return path.relative_to(root).as_posix()

    def require_paths(data, allow_root=False):
        raw = data.get("paths")
        if not isinstance(raw, list) or not raw or len(raw) > MAX_SELECTION:
            abort(400, description=f"Select between 1 and {MAX_SELECTION} items")
        if any(not isinstance(value, str) or (not value and not allow_root) for value in raw):
            abort(400, description="Invalid selection")
        paths = [resolve_path(value) for value in raw]
        return list(dict.fromkeys(paths))

    @app.before_request
    def check_access():
        if token:
            auth = request.authorization
            if not (auth and auth.type.lower() == "basic"
                    and secrets.compare_digest(auth.username or "", "neon")
                    and secrets.compare_digest(auth.password or "", token)):
                return ("Authentication required", 401,
                        {"WWW-Authenticate": 'Basic realm="Neon Uploader"'})
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("Origin")
            if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
                abort(403, description="Cross-origin write rejected")

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(413)
    def handle_error(error):
        return jsonify(error=error.description), error.code

    @app.get("/")
    def index():
        return render_template_string(HTML_FORM)

    @app.get("/api/files")
    def list_files():
        folder = resolve_path(request.args.get("path", ""), kind="dir")
        items = []
        for entry in folder.iterdir():
            if entry.is_symlink():
                continue
            try:
                stat = entry.stat()
                if not (entry.is_file() or entry.is_dir()):
                    continue
            except OSError:
                continue
            items.append({
                "name": entry.name,
                "path": relative_name(entry),
                "type": "directory" if entry.is_dir() else "file",
                "size": None if entry.is_dir() else stat.st_size,
                "modified": datetime.datetime.fromtimestamp(
                    stat.st_mtime, datetime.timezone.utc).isoformat(),
            })
        items.sort(key=lambda item: (item["type"] != "directory", item["name"].casefold()))
        return jsonify(path=relative_name(folder) if folder != root else "", items=items)

    @app.post("/upload")
    def upload_files():
        folder = resolve_path(request.form.get("path", ""), kind="dir")
        incoming = request.files.getlist("files")
        saved, skipped = [], []
        for incoming_file in incoming:
            raw = incoming_file.filename or ""
            name = secure_filename(raw.replace("\\", "/").split("/")[-1])
            if not name:
                skipped.append(raw)
                continue
            # Exclusive creation prevents duplicate overwrite and symlink races.
            base, ext = os.path.splitext(name)
            counter = 0
            while True:
                candidate = name if not counter else f"{base}_{counter:03d}{ext}"
                try:
                    with open(folder / candidate, "xb") as destination:
                        incoming_file.save(destination)
                    break
                except FileExistsError:
                    counter += 1
            saved.append(candidate)
            print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] Uploaded: {relative_name(folder / candidate)}")
        return jsonify(saved=saved, skipped=skipped), (200 if saved else 400)

    @app.get("/api/download")
    def download_file():
        target = resolve_path(request.args.get("path", ""), kind="file")
        return send_file(target, as_attachment=True, download_name=target.name,
                         conditional=True)

    @app.post("/api/download-zip")
    def download_zip():
        paths = require_paths(request.get_json(silent=True) or {})
        archive = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
        seen = set()
        try:
            with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=3, allowZip64=True) as bundle:
                for selected in paths:
                    if selected.is_dir():
                        candidates = [selected]
                        for parent, folders, files in os.walk(selected, followlinks=False):
                            folders[:] = [f for f in folders if not (Path(parent) / f).is_symlink()]
                            candidates.extend(Path(parent) / name for name in folders + files)
                    else:
                        candidates = [selected]
                    for candidate in candidates:
                        if candidate.is_symlink() or not candidate.exists():
                            continue
                        name = relative_name(candidate)
                        if name in seen:
                            continue
                        seen.add(name)
                        if len(seen) > MAX_ARCHIVE_FILES:
                            abort(413, description="Archive exceeds file count limit")
                        if candidate.is_dir():
                            bundle.writestr(name + "/", b"")
                        elif candidate.is_file():
                            bundle.write(candidate, arcname=name)
            archive.seek(0)
            response = send_file(archive, as_attachment=True,
                                 download_name="neon-selection.zip",
                                 mimetype="application/zip")
            response.call_on_close(archive.close)
            return response
        except Exception:
            archive.close()
            raise

    @app.post("/api/folders")
    def make_folder():
        data = request.get_json(silent=True) or {}
        parent = resolve_path(data.get("path", ""), kind="dir")
        name = valid_new_name(data.get("name"))
        try:
            (parent / name).mkdir()
        except FileExistsError:
            abort(409, description="This name already exists")
        return jsonify(name=name), 201

    @app.post("/api/rename")
    def rename_item():
        data = request.get_json(silent=True) or {}
        target = resolve_path(data.get("path", ""))
        if target == root:
            abort(400, description="Cannot rename upload root")
        name = valid_new_name(data.get("name"))
        destination = target.with_name(name)
        if destination == target:
            return jsonify(name=name)
        if destination.exists() or destination.is_symlink():
            abort(409, description="This name already exists")
        # Never replace an existing file on platforms where os.rename can overwrite.
        # A lock is not a substitute for restricting local filesystem writers.
        target.rename(destination)
        return jsonify(name=name)

    @app.post("/api/delete")
    def delete_items():
        data = request.get_json(silent=True) or {}
        if data.get("confirm") is not True:
            abort(400, description="Explicit confirmation is required")
        selected = require_paths(data)
        # Parent folders cover their children; deleting a child first can cause partial failures.
        selected.sort(key=lambda path: len(path.parts))
        kept = []
        for item in selected:
            if not any(parent in item.parents for parent in kept):
                kept.append(item)
        for item in kept:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        return jsonify(deleted=len(kept))

    return app


def main():
    host = input("Host [127.0.0.1]: ").strip() or "127.0.0.1"
    port_input = input("Port [8080]: ").strip()
    try:
        port = int(port_input) if port_input else 8080
        if port < 1 or port > 65535:
            raise ValueError
    except ValueError:
        port = 8080
    folder = input("Upload folder [uploads]: ").strip() or "uploads"
    token = os.environ.get("NEON_ACCESS_TOKEN", "")
    if host not in ("127.0.0.1", "localhost", "::1") and not token:
        raise SystemExit("Refusing network exposure without NEON_ACCESS_TOKEN. Set a long token first.")
    app = create_app(folder, access_token=token)
    print(f"Server running on http://{host}:{port}/")
    print(f"Files stored at: {Path(folder).expanduser().resolve()}")
    print("For remote access, use HTTPS via a trusted reverse proxy.")
    app.run(host=host, port=port, debug=False)


# The inline template keeps deployment to a single Python file.
HTML_FORM = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Neon Uploader · File manager</title>
  <style>
    :root{color-scheme:dark;--bg:#090e16;--panel:#101b2a;--panel2:#0c1521;--edge:#274159;--text:#eaf4ff;--muted:#9eb1c5;--blue:#66e0ff;--violet:#b372ff;--pink:#ff84ad;--green:#67e8bc}
    *{box-sizing:border-box} body{margin:0;min-height:100vh;padding:28px 16px 60px;background:radial-gradient(900px 570px at 90% 0%,#50306342,transparent 70%),radial-gradient(850px 500px at 0% 70%,#17678630,transparent 75%),var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
    button,input{font:inherit}button{cursor:pointer}button:focus-visible,input:focus-visible{outline:2px solid var(--blue);outline-offset:3px}
    .wrap{max-width:1100px;margin:auto}.header{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:24px}.brand{display:flex;align-items:center;gap:13px}.logo{width:47px;height:47px;display:grid;place-items:center;border-radius:14px;color:#04141b;font-size:25px;font-weight:900;background:linear-gradient(135deg,var(--blue),var(--violet));box-shadow:0 4px 30px #66e0ff33}
    h1{font-size:1.65rem;margin:0;letter-spacing:.02em}.subtitle{color:var(--muted);margin:3px 0 0}.top-pill{border:1px solid var(--edge);border-radius:999px;padding:6px 12px;color:var(--green);font-size:.83rem}
    .card{border:1px solid var(--edge);border-radius:17px;background:linear-gradient(160deg,#17253aa8,var(--panel2));box-shadow:0 18px 50px #0005;padding:20px;margin-bottom:17px}
    .section-title{font-weight:700;font-size:1.03rem;margin:0 0 13px}.upload-row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.dropzone{min-width:220px;flex:1;display:flex;align-items:center;gap:12px;padding:17px;border:1px dashed #52809a;border-radius:12px;background:#122337;transition:background .15s,border-color .15s;cursor:pointer}.dropzone.over{background:#183c53;border-color:var(--blue)}.dropzone input{display:none}.dropzone small{display:block;color:var(--muted)}.drop-icon{font-size:27px;color:var(--blue)}
    .btn{border:1px solid var(--edge);border-radius:10px;padding:9px 13px;color:var(--text);background:#18283b;font-weight:650;white-space:nowrap}.btn:hover:not(:disabled){border-color:var(--blue);background:#20384b}.btn.primary{color:#061522;background:linear-gradient(90deg,var(--blue),var(--violet));border:0;padding:13px 21px}.btn.ghost{background:transparent}.btn.danger{color:#ffb2cb}.btn:disabled{opacity:.42;cursor:not-allowed}.muted{color:var(--muted)}
    .queued{margin:12px 0 0;padding:0;list-style:none;max-height:200px;overflow:auto}.queued li{display:flex;gap:9px;align-items:center;padding:6px;border-top:1px solid #ffffff11}.queued li span:first-child{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.queued button{border:0;background:transparent;color:var(--pink);padding:3px 9px}.queue-footer{margin-top:9px;font-size:.83rem;color:var(--muted)}
    .browser-top,.toolbar,.crumbs{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.browser-top{justify-content:space-between;margin-bottom:17px}.crumbs{gap:5px;min-width:0}.crumbs button{border:0;background:transparent;color:var(--blue);padding:4px 5px;border-radius:6px}.crumbs button:last-child{color:var(--text);font-weight:700}.crumbs span{color:var(--muted)}.toolbar{margin:9px 0 14px}.toolbar .grow{flex:1}.search{background:#0c1725;border:1px solid var(--edge);border-radius:10px;padding:10px 12px;color:var(--text);min-width:190px;width:min(245px,100%)}
    .table-shell{border:1px solid var(--edge);border-radius:12px;overflow:hidden;min-height:170px}.file-head,.file-row{display:grid;grid-template-columns:36px minmax(170px,1fr) 105px 180px;align-items:center;gap:10px;padding:11px 15px}.file-head{font-size:.77rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);background:#112137}.file-row{border-top:1px solid #29415770;min-height:51px}.file-row:hover{background:#66e0ff0e}.file-row.selected{background:#66e0ff19}.file-row button.name-button{display:flex;align-items:center;text-align:left;gap:11px;border:0;background:transparent;color:var(--text);padding:0;min-width:0}.file-row button.name-button:hover{text-decoration:underline;text-decoration-color:var(--blue)}.file-icon{font-size:20px;flex-shrink:0}.file-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.file-row .meta{font-size:.84rem;color:var(--muted);white-space:nowrap}.file-row input[type=checkbox],.file-head input[type=checkbox]{accent-color:var(--blue);width:17px;height:17px;cursor:pointer}.empty{color:var(--muted);padding:47px 15px;text-align:center}.browser-footer{display:flex;justify-content:space-between;gap:8px;margin-top:12px;color:var(--muted);font-size:.84rem}
    .context{position:fixed;z-index:100;background:#18283a;border:1px solid #517189;border-radius:11px;padding:6px;min-width:188px;box-shadow:0 15px 45px #000a}.context[hidden]{display:none}.context button{display:block;width:100%;padding:9px 12px;text-align:left;border:0;border-radius:6px;color:var(--text);background:transparent}.context button:hover,.context button:focus-visible{background:#305069}.context button.danger{color:#ffadc9}.context hr{border:0;border-top:1px solid var(--edge)}
    .toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);max-width:min(550px,95%);border:1px solid #507d88;border-radius:11px;padding:11px 17px;background:#172c3c;box-shadow:0 10px 30px #000a;z-index:200}.toast[hidden]{display:none}.hint{font-size:.83rem;color:var(--muted);margin:14px 0 0}
    @media(max-width:700px){body{padding:16px 10px 40px}.card{padding:14px}.file-head,.file-row{grid-template-columns:25px minmax(100px,1fr) 80px;padding:10px 9px;gap:7px}.file-head span:last-child,.file-row .date{display:none}.toolbar .grow{display:none}.search{flex:1;width:100%}.browser-top{align-items:flex-start}.top-pill{display:none}}
  </style>
</head>
<body>
  <main class="wrap">
    <header class="header">
      <div class="brand"><div class="logo" aria-hidden="true">N</div><div><h1>Neon Uploader</h1><p class="subtitle">Upload · Browse · Organize · Download</p></div></div>
      <span class="top-pill">● Local file workspace</span>
    </header>
    <section class="card" aria-label="Upload files">
      <h2 class="section-title">Upload to <span id="uploadTarget">/</span></h2>
      <div class="upload-row">
        <label class="dropzone" id="dropzone"><span class="drop-icon" aria-hidden="true">⇧</span><span><strong>Choose files or drop them here</strong><small>Multiple files supported · duplicate names are renamed</small></span><input id="filePicker" type="file" multiple aria-label="Choose files"></label>
        <button id="uploadBtn" type="button" class="btn primary" disabled>Upload files</button>
      </div>
      <ul id="queueList" class="queued" aria-label="Upload queue"></ul>
      <div id="queueCount" class="queue-footer">No files queued</div>
    </section>
    <section class="card" aria-label="File browser">
      <div class="browser-top">
        <div><h2 class="section-title" style="margin:0">File browser</h2><nav id="breadcrumbs" class="crumbs" aria-label="Folder path"></nav></div>
        <div class="toolbar"><button class="btn ghost" id="refreshBtn" type="button">↻ Refresh</button><button class="btn" id="newFolderBtn" type="button">+ New folder</button></div>
      </div>
      <div class="toolbar">
        <input id="search" class="search" type="search" placeholder="Search this folder…" aria-label="Search files">
        <span class="grow"></span><button class="btn" type="button" id="downloadSelected" disabled>↓ Download selected</button>
        <button class="btn danger" type="button" id="deleteSelected" disabled>Delete selected</button>
      </div>
      <div class="table-shell" id="fileBrowser" tabindex="0" aria-label="Files and folders">
        <div class="file-head"><input id="selectAll" type="checkbox" aria-label="Select all visible files and folders"><span>Name</span><span>Size</span><span>Modified</span></div>
        <div id="rows" aria-live="polite"><div class="empty">Loading files…</div></div>
      </div>
      <div class="browser-footer"><span id="fileCount">0 items</span><span id="selectionCount">0 selected</span></div>
      <p class="hint">Right-click an item for actions. Select multiple items with checkmarks; folders download as ZIP archives. Selection applies to the current folder.</p>
    </section>
  </main>
  <div id="contextMenu" class="context" role="menu" hidden></div>
  <div id="toast" class="toast" role="status" aria-live="polite" hidden></div>
  <script>
  (() => {
    'use strict';
    const $ = id => document.getElementById(id);
    const state = {path:'',items:[],selected:new Set(),queue:[],busy:false};
    const rows = $('rows'), menu = $('contextMenu'), selectAll = $('selectAll');
    let toastTimer;
    const bytes = n => n == null ? '—' : n === 0 ? '0 B' :
      (n / (1024 ** Math.min(4, Math.floor(Math.log(n)/Math.log(1024))))).toFixed(2) + ' ' +
      ['B','KB','MB','GB','TB'][Math.min(4, Math.floor(Math.log(n)/Math.log(1024)))];
    const pathJoin = (base,name) => base ? base+'/'+name : name;
    const dlUrl = path => '/api/download?path='+encodeURIComponent(path);
    function toast(message){ const box=$('toast');box.textContent=message;box.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>box.hidden=true,5000); }
    async function api(url, options={}) {
      const response = await fetch(url, options);
      if(!response.ok){let msg='Request failed ('+response.status+')';try{msg=(await response.json()).error||msg;}catch{}throw new Error(msg);}
      return response;
    }
    const jsonOptions = obj => ({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)});
    async function run(fn){ try { await fn(); } catch(error){toast(error.message || String(error));} }
    function visibleItems(){const filter=$('search').value.trim().toLocaleLowerCase();return state.items.filter(i=>i.name.toLocaleLowerCase().includes(filter));}
    function renderCrumbs(){
      const nav=$('breadcrumbs');nav.replaceChildren();const segments=state.path?state.path.split('/'):[];
      [['Home',''],...segments.map((s,i)=>[s,segments.slice(0,i+1).join('/')])].forEach(([name,path],i)=>{
        if(i){const slash=document.createElement('span');slash.textContent='/';nav.append(slash);}
        const button=document.createElement('button');button.type='button';button.textContent=name;
        button.addEventListener('click',()=>run(()=>navigate(path)));nav.append(button);
      });
      $('uploadTarget').textContent='/'+state.path;
    }
    function renderQueue(){
      const ul=$('queueList');ul.replaceChildren();let total=0;
      state.queue.forEach((file,index)=>{total+=file.size;const li=document.createElement('li');
        const label=document.createElement('span');label.textContent=file.name;label.title=file.name;
        const size=document.createElement('small');size.className='muted';size.textContent=bytes(file.size);
        const remove=document.createElement('button');remove.type='button';remove.textContent='✕';remove.setAttribute('aria-label','Remove '+file.name);
        remove.addEventListener('click',()=>{state.queue.splice(index,1);renderQueue();});li.append(label,size,remove);ul.append(li);
      });
      $('queueCount').textContent=state.queue.length ? state.queue.length+' queued · '+bytes(total):'No files queued';
      $('uploadBtn').disabled=!state.queue.length||state.busy;
    }
    function updateSelection(){
      const visible=visibleItems(), count=visible.filter(i=>state.selected.has(i.path)).length;
      selectAll.checked=visible.length>0&&count===visible.length;
      selectAll.indeterminate=count>0&&count<visible.length;
      $('selectionCount').textContent=state.selected.size+' selected';
      $('downloadSelected').disabled=!state.selected.size||state.busy;
      $('deleteSelected').disabled=!state.selected.size||state.busy;
      rows.querySelectorAll('.file-row').forEach(row=>{
        const checked=state.selected.has(row.dataset.path);row.classList.toggle('selected',checked);
        const cb=row.querySelector('input[type=checkbox]');if(cb)cb.checked=checked;
      });
    }
    function renderRows(){
      menu.hidden=true;rows.replaceChildren();const items=visibleItems();
      if(!items.length){const empty=document.createElement('div');empty.className='empty';empty.textContent=state.items.length?'No matching files or folders.':'This folder is empty. Upload files or create a folder.';rows.append(empty);}
      items.forEach(item=>{
        const row=document.createElement('div');row.className='file-row';row.dataset.path=item.path;
        const box=document.createElement('input');box.type='checkbox';box.checked=state.selected.has(item.path);box.setAttribute('aria-label','Select '+item.name);
        box.addEventListener('change',()=>{if(box.checked)state.selected.add(item.path);else state.selected.delete(item.path);updateSelection();});
        const open=document.createElement('button');open.type='button';open.className='name-button';open.title=item.type==='directory'?'Open folder':'Download file';
        const icon=document.createElement('span');icon.className='file-icon';icon.setAttribute('aria-hidden','true');icon.textContent=item.type==='directory'?'📁':'▤';
        const name=document.createElement('span');name.className='file-name';name.textContent=item.name;
        open.append(icon,name);open.addEventListener('click',()=>run(()=>openItem(item)));
        const size=document.createElement('span');size.className='meta';size.textContent=bytes(item.size);
        const date=document.createElement('span');date.className='meta date';date.textContent=new Date(item.modified).toLocaleString();
        row.append(box,open,size,date);
        row.addEventListener('contextmenu',event=>{event.preventDefault();if(!state.selected.has(item.path)){state.selected.clear();state.selected.add(item.path);updateSelection();}showMenu(item,event.clientX,event.clientY);});
        rows.append(row);
      });
      $('fileCount').textContent=items.length+' shown · '+state.items.length+' total';updateSelection();
    }
    async function navigate(path){
      menu.hidden=true;
      const response=await api('/api/files?path='+encodeURIComponent(path));const data=await response.json();
      state.path=data.path;state.items=data.items;state.selected.clear();$('search').value='';renderCrumbs();renderRows();
    }
    async function refresh(){const response=await api('/api/files?path='+encodeURIComponent(state.path));const data=await response.json();state.items=data.items;
      const stillHere=new Set(data.items.map(i=>i.path));state.selected=new Set([...state.selected].filter(p=>stillHere.has(p)));renderRows();}
    async function openItem(item){if(item.type==='directory')await navigate(item.path);else downloadFile(item.path);}
    function downloadFile(path){const anchor=document.createElement('a');anchor.href=dlUrl(path);anchor.download='';document.body.append(anchor);anchor.click();anchor.remove();}
    async function downloadZip(paths){
      state.busy=true;updateSelection();toast('Preparing ZIP archive…');
      try{const response=await api('/api/download-zip',jsonOptions({paths}));const blob=await response.blob();const url=URL.createObjectURL(blob);
        const anchor=document.createElement('a');anchor.href=url;anchor.download='neon-selection.zip';document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
        toast('ZIP download started.');
      }finally{state.busy=false;updateSelection();}
    }
    async function downloadPaths(paths){
      const items=paths.map(path=>state.items.find(item=>item.path===path)).filter(Boolean);
      if(items.length===1&&items[0].type==='file')downloadFile(items[0].path);
      else if(paths.length)await downloadZip(paths);
    }
    async function deletePaths(paths){
      if(!paths.length)return;
      if(!confirm('Permanently delete '+paths.length+' selected item(s)? Folders and their contents will also be deleted. This cannot be undone.'))return;
      const result=await (await api('/api/delete',jsonOptions({paths,confirm:true}))).json();
      toast('Deleted '+result.deleted+' item(s).');await refresh();
    }
    async function rename(item){
      const proposed=prompt('Rename '+item.name+' to:',item.name);if(proposed===null||proposed===item.name)return;
      await api('/api/rename',jsonOptions({path:item.path,name:proposed}));toast('Renamed '+item.name);await refresh();
    }
    async function createFolder(){
      const name=prompt('Name the new folder:');if(name===null)return;
      await api('/api/folders',jsonOptions({path:state.path,name}));toast('Folder created.');await refresh();
    }
    function menuAction(text,callback,destructive=false){
      const button=document.createElement('button');button.type='button';button.role='menuitem';button.textContent=text;
      if(destructive)button.className='danger';button.addEventListener('click',()=>{menu.hidden=true;run(callback);});menu.append(button);
    }
    function showMenu(item,x,y){
      menu.replaceChildren();if(item.type==='directory')menuAction('📂 Open folder',()=>navigate(item.path));
      menuAction('↓ Download'+(item.type==='directory'?' as ZIP':''),()=>downloadPaths([item.path]));
      menuAction('◫ Copy filename',async()=>{await navigator.clipboard.writeText(item.name);toast('Filename copied.');});
      if(item.type==='file')menuAction('🔗 Copy download URL',async()=>{await navigator.clipboard.writeText(location.origin+dlUrl(item.path));toast('Download URL copied.');});
      menuAction('✎ Rename',()=>rename(item));
      const separator=document.createElement('hr');menu.append(separator);
      menuAction('✕ Delete',()=>deletePaths([item.path]),true);
      menu.hidden=false;menu.style.left=Math.max(5,Math.min(x,window.innerWidth-menu.offsetWidth-8))+'px';
      menu.style.top=Math.max(5,Math.min(y,window.innerHeight-menu.offsetHeight-8))+'px';
      menu.querySelector('button')?.focus();
    }
    document.addEventListener('click',event=>{if(!menu.contains(event.target))menu.hidden=true;});
    document.addEventListener('keydown',event=>{if(event.key==='Escape')menu.hidden=true;});
    $('search').addEventListener('input',renderRows);
    selectAll.addEventListener('change',()=>{const targets=visibleItems();targets.forEach(item=>selectAll.checked?state.selected.add(item.path):state.selected.delete(item.path));updateSelection();});
    $('fileBrowser').addEventListener('keydown',event=>{
      if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='a'&&!['INPUT','TEXTAREA'].includes(event.target.tagName)){
        event.preventDefault();visibleItems().forEach(item=>state.selected.add(item.path));updateSelection();
      }
      if(event.key==='Delete'&&!['INPUT','TEXTAREA'].includes(event.target.tagName)){event.preventDefault();run(()=>deletePaths([...state.selected]));}
    });
    $('refreshBtn').addEventListener('click',()=>run(refresh));
    $('newFolderBtn').addEventListener('click',()=>run(createFolder));
    $('downloadSelected').addEventListener('click',()=>run(()=>downloadPaths([...state.selected])));
    $('deleteSelected').addEventListener('click',()=>run(()=>deletePaths([...state.selected])));
    $('filePicker').addEventListener('change',event=>{state.queue.push(...Array.from(event.target.files));event.target.value='';renderQueue();});
    const dropzone=$('dropzone');
    ['dragenter','dragover'].forEach(type=>dropzone.addEventListener(type,event=>{event.preventDefault();dropzone.classList.add('over');}));
    ['dragleave','drop'].forEach(type=>dropzone.addEventListener(type,event=>{event.preventDefault();dropzone.classList.remove('over');}));
    dropzone.addEventListener('drop',event=>{state.queue.push(...Array.from(event.dataTransfer.files));renderQueue();});
    $('uploadBtn').addEventListener('click',()=>run(async()=>{
      if(!state.queue.length)return;state.busy=true;renderQueue();
      const data=new FormData();data.append('path',state.path);state.queue.forEach(f=>data.append('files',f,f.name));
      try{const response=await api('/upload',{method:'POST',body:data});const result=await response.json();
        toast('Uploaded '+result.saved.length+' file(s).'+(result.skipped.length?' Skipped '+result.skipped.length+'.':''));state.queue=[];await refresh();
      }finally{state.busy=false;renderQueue();}
    }));
    renderQueue();run(()=>navigate(''));
  })();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
