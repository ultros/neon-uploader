import os
import datetime
from flask import Flask, request, render_template_string, jsonify
from werkzeug.utils import secure_filename


def human_readable_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(min(len(size_name) - 1, (len(str(size_bytes)) - 1) / 3))
    p = pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


def generate_unique_filename(directory, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    new_name = filename
    while os.path.exists(os.path.join(directory, new_name)):
        new_name = f"{base}_{counter:03d}{ext}"
        counter += 1
    return new_name


def main():
    host = input('Host [0.0.0.0]: ').strip() or '0.0.0.0'
    port_input = input('Port [8080]: ').strip()
    try:
        port = int(port_input) if port_input else 8080
    except ValueError:
        port = 8080

    upload_folder = input('Upload folder [uploads]: ').strip() or 'uploads'

    app = Flask(__name__)
    os.makedirs(upload_folder, exist_ok=True)

    HTML_FORM = """
    <!doctype html>
    <html lang='en'>
    <head>
      <meta charset='utf-8'>
      <meta name='viewport' content='width=device-width, initial-scale=1'>
      <title>Neon Uploader</title>
      <style>
        :root{
          --bg:#0b0f14;
          --panel:#0f1722;
          --muted:#9aa4b2;
          --text:#e6f1ff;
          --edge:#132235;
          --accent:#66e0ff;
          --accent-2:#b372ff;
          --ok:#54f1c3;
          --warn:#ffb86b;
          --danger:#ff6b9e;
          --radius:16px;
          --ring:0 0 0 1px var(--edge), 0 8px 30px rgba(102,224,255,0.08);
        }
        *{box-sizing:border-box}
        html,body{height:100%}
        body{
          margin:0;display:flex;align-items:center;justify-content:center;background:
            radial-gradient(1200px 800px at 80% -20%, rgba(179,114,255,0.12), transparent 60%),
            radial-gradient(1000px 700px at -10% 120%, rgba(102,224,255,0.10), transparent 60%),
            var(--bg);
          color:var(--text);font:500 16px/1.4 system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, sans-serif;
          padding:24px;
        }
        .wrap{width:min(860px, 100%)}
        .card{
          background:linear-gradient(180deg, rgba(19,34,53,0.8), rgba(15,23,34,0.9));
          border-radius:var(--radius);box-shadow:var(--ring);border:1px solid var(--edge);
          padding:22px 22px 18px 22px;backdrop-filter: blur(8px);
        }
        h1{margin:0 0 8px 0;font-weight:700;letter-spacing:.3px;}
        .sub{margin:0 0 18px 0;color:var(--muted);}
        .row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
        input[type=file]{
          color:var(--muted);background:var(--panel);border:1px dashed var(--edge);
          border-radius:12px;padding:12px;flex:1;min-width:260px;outline:none;
        }
        .btn{
          appearance:none;border:0;border-radius:12px;padding:12px 16px;font-weight:700;letter-spacing:.3px;
          background:linear-gradient(90deg, var(--accent), var(--accent-2));
          color:#001018;cursor:pointer;box-shadow:0 6px 18px rgba(102,224,255,.18), inset 0 0 0 1px rgba(255,255,255,.08);
          transition: transform .08s ease, filter .15s ease;
        }
        .btn[disabled]{opacity:.5;cursor:not-allowed;filter:grayscale(.4)}
        .btn:not([disabled]):active{transform:translateY(1px)}
        .panel{margin-top:14px;background:var(--panel);border:1px solid var(--edge);border-radius:14px;padding:12px}
        ul{list-style:none;margin:0;padding:0;max-height:260px;overflow:auto}
        li{display:flex;align-items:center;gap:8px;padding:10px 8px;border-bottom:1px dashed rgba(102,224,255,.08)}
        li:last-child{border-bottom:0}
        .tag{font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;font-size:12px;color:var(--muted)}
        .name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .chip{font:600 12px/1 ui-monospace; color:#001018;background:var(--accent);padding:6px 8px;border-radius:999px;}
        .remove{appearance:none;border:1px solid var(--edge);color:var(--text);background:transparent;padding:6px 10px;border-radius:10px;cursor:pointer}
        .remove:hover{border-color:var(--danger);color:var(--danger)}
        .stats{display:flex;justify-content:space-between;align-items:center;margin-top:10px;color:var(--muted)}
        .stats strong{color:var(--text)}
      </style>
    </head>
    <body>
      <div class='wrap'>
        <div class='card'>
          <h1>Neon Uploader</h1>
          <p class='sub'>Fast multi-file uploader with soft cyberpunk vibes.</p>
          <div class='row'>
            <input id='filePicker' type='file' name='files' multiple>
            <button id='uploadBtn' class='btn' type='button' disabled>Upload</button>
          </div>
          <div class='panel'>
            <ul id='fileList'></ul>
            <div class='stats'>
              <span class='tag' id='counter'>0 files — 0 B</span>
              <span class='tag'>Ready</span>
            </div>
          </div>
        </div>
      </div>

      <script>
      (function() {
        const picker = document.getElementById('filePicker');
        const list = document.getElementById('fileList');
        const uploadBtn = document.getElementById('uploadBtn');
        const counterEl = document.getElementById('counter');
        const queue = [];

        function humanReadableSize(size) {
          if (!size) return '0 B';
          const u = ['B','KB','MB','GB','TB'];
          const i = Math.min(u.length-1, Math.floor(Math.log(size)/Math.log(1024)));
          return (size/Math.pow(1024,i)).toFixed(2)+' '+u[i];
        }

        function renderList() {
          list.textContent = '';
          let total = 0;
          queue.forEach((f, i) => {
            total += f.size||0;
            const li = document.createElement('li');
            const name = document.createElement('span');
            name.className = 'name';
            name.title = f.name;
            name.textContent = f.name;
            const size = document.createElement('span');
            size.className = 'tag';
            size.textContent = humanReadableSize(f.size||0);
            const rm = document.createElement('button');
            rm.className = 'remove';
            rm.type = 'button';
            rm.textContent = 'remove';
            rm.addEventListener('click', () => { queue.splice(i,1); renderList(); });
            li.appendChild(name);
            li.appendChild(size);
            li.appendChild(rm);
            list.appendChild(li);
          });
          counterEl.textContent = `${queue.length} file${queue.length!==1?'s':''} — ${humanReadableSize(total)}`;
          uploadBtn.disabled = queue.length === 0;
        }

        picker.addEventListener('change', () => {
          const files = Array.from(picker.files||[]);
          files.forEach(f => queue.push(f));
          picker.value = '';
          renderList();
        });

        uploadBtn.addEventListener('click', async () => {
          uploadBtn.disabled = true;
          const fd = new FormData();
          queue.forEach(f => fd.append('files', f, f.name));
          try {
            const res = await fetch('/upload', { method: 'POST', body: fd });
            const data = await res.json();
            if (!res.ok) throw new Error('Upload failed');
            alert('Saved: ' + data.saved.join(', ') + (data.skipped.length ? '\nSkipped: ' + data.skipped.join(', ') : ''));
            queue.length = 0;
            renderList();
          } catch (e) {
            alert(String(e));
            uploadBtn.disabled = false;
          }
        });
      })();
      </script>
    </body>
    </html>
    """

    @app.route('/', methods=['GET'])
    def index():
        return render_template_string(HTML_FORM)

    @app.route('/upload', methods=['POST'])
    def upload_files():
        incoming = request.files.getlist('files') or []
        saved, skipped = [], []
        for f in incoming:
            raw_name = getattr(f, 'filename', '') or ''
            name = secure_filename(raw_name)
            if name:
                unique_name = generate_unique_filename(upload_folder, name)
                dest = os.path.join(upload_folder, unique_name)
                f.save(dest)
                saved.append(unique_name)
                size = os.path.getsize(dest)
                readable_size = human_readable_size(size)
                timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f"[{timestamp}] Uploaded: {unique_name} -> {dest} ({readable_size})")
            else:
                skipped.append(raw_name)
        if not saved:
            print('[!] No valid files uploaded.')
        else:
            total_size = sum(os.path.getsize(os.path.join(upload_folder, s)) for s in saved)
            print(f"[+] {len(saved)} files successfully uploaded. Total size: {human_readable_size(total_size)}")
        return jsonify({'saved': saved, 'skipped': skipped}), (200 if saved else 400)

    print(f"Server running on http://{host}:{port}/")
    print(f"Uploads will be stored in: {os.path.abspath(upload_folder)}")
    app.run(host=host, port=port)


if __name__ == '__main__':
    main()

