import os
import hashlib
import sqlite3
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request, redirect, url_for
import threading
import webbrowser
from collections import Counter

# --- CONFIGURATION ---
DB_PATH = 'file_index.db'
SCAN_DIR = os.path.expanduser('~')
MAX_DEMO_FILES = 50
PER_PAGE = 100

JUNK_NAMES = frozenset({'RECORD', 'INSTALLER', 'REQUESTED', 'WHEEL', 'METADATA'})
JUNK_EXTENSIONS = frozenset({'.pyc', '.pyo', '.ds_store'})

VALID_SORT_COLS = {'name': 'name', 'path': 'path', 'size': 'size', 'modified': 'modified'}

# Global state
DEMO_MODE = True
VERBOSE = True
SCANNING = False
SCANNER_THREAD = None
SCAN_METADATA = {}
SCAN_PROGRESS = {'file_count': 0, 'current_dir': ''}

# --- DB SETUP ---
def create_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY,
                    path TEXT UNIQUE,
                    name TEXT,
                    size INTEGER,
                    created TEXT,
                    modified TEXT,
                    hash TEXT
                )''')
    conn.commit()
    conn.close()

# --- UTILS ---
def get_file_hash(path):
    try:
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        if VERBOSE:
            print(f"Hashing failed for {path}: {e}")
        return None

def clear_index():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM files")
    conn.commit()
    conn.close()

def format_size(size):
    """Convert bytes to a human-readable string."""
    if size is None:
        return '—'
    if size < 1024:
        return f'{size} B'
    elif size < 1024 * 1024:
        return f'{size / 1024:.1f} KB'
    elif size < 1024 * 1024 * 1024:
        return f'{size / (1024 * 1024):.1f} MB'
    else:
        return f'{size / (1024 * 1024 * 1024):.1f} GB'

def build_where_clause(show_junk, search_query=None):
    """Build a WHERE clause with optional junk filter and filename search."""
    conditions = []
    params = []

    if not show_junk:
        name_placeholders = ','.join('?' for _ in JUNK_NAMES)
        conditions.append(f"UPPER(name) NOT IN ({name_placeholders})")
        params.extend(JUNK_NAMES)
        for ext in JUNK_EXTENSIONS:
            conditions.append("LOWER(name) NOT LIKE ?")
            params.append(f'%{ext}')

    if search_query:
        conditions.append("LOWER(name) LIKE ?")
        params.append(f'%{search_query.lower()}%')

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
    return where, params

# --- SCANNER ---
def scan_directory(base_path, demo_mode=False, verbose=False):
    global SCANNING, SCAN_METADATA, SCAN_PROGRESS
    SCANNING = True
    SCAN_PROGRESS = {'file_count': 0, 'current_dir': base_path}
    start_time = datetime.now()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    file_count = 0
    extensions = []

    for root, dirs, files in os.walk(base_path):
        if not SCANNING:
            break
        SCAN_PROGRESS['current_dir'] = root
        if verbose:
            print(f"Scanning directory: {root}")
        for name in files:
            if not SCANNING:
                break
            full_path = os.path.join(root, name)
            try:
                stat = os.stat(full_path)
                created = datetime.fromtimestamp(stat.st_ctime).isoformat()
                modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
                size = stat.st_size
                file_hash = get_file_hash(full_path)
                c.execute(
                    "INSERT OR REPLACE INTO files (path, name, size, created, modified, hash) VALUES (?, ?, ?, ?, ?, ?)",
                    (full_path, name, size, created, modified, file_hash)
                )
                ext = os.path.splitext(name)[1].lower()
                extensions.append(ext)
                if verbose:
                    print(f"Indexed: {full_path}")
                file_count += 1
                SCAN_PROGRESS['file_count'] = file_count
                if demo_mode and file_count >= MAX_DEMO_FILES:
                    if verbose:
                        print("Demo mode limit reached. Stopping scan.")
                    SCANNING = False
                    break
            except Exception as e:
                if verbose:
                    print(f"Failed to index {full_path}: {e}")
                continue

    conn.commit()
    conn.close()
    SCANNING = False
    end_time = datetime.now()
    SCAN_METADATA = {
        'start_time': start_time,
        'end_time': end_time,
        'file_count': file_count,
        'scan_dir': base_path,
        'file_types': dict(Counter(extensions))
    }

# --- FLASK APP ---
app = Flask(__name__)

HTML_TEMPLATE = '''
<html>
<head>
  <meta charset="UTF-8">
  <title>Mnemosylva — File Index</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }

    body {
      font-family: Arial, sans-serif;
      font-size: 14px;
      color: #222;
      margin: 0;
      background: #f0f2f5;
    }

    /* ── Top bar (sticky) ───────────────────────────────────────── */
    .top-bar {
      position: sticky; top: 0; z-index: 100;
      background: #1a1f36; color: white;
      padding: 10px 20px;
      display: flex; align-items: center; gap: 16px;
    }
    .top-bar h1 { margin: 0; font-size: 18px; font-weight: 600; flex-shrink: 0; }
    .top-bar form { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .top-bar label { font-size: 13px; display: flex; align-items: center; gap: 4px; }
    .top-bar input[type=text] {
      padding: 5px 10px; border-radius: 4px; border: 1px solid #555;
      background: #2d3350; color: white; font-size: 13px; width: 240px;
    }
    .top-bar input[type=text]::placeholder { color: #aaa; }
    .top-bar button {
      padding: 5px 12px; border-radius: 4px; border: none;
      background: #4a90d9; color: white; cursor: pointer; font-size: 13px;
    }
    .top-bar button:hover { background: #357abd; }
    .top-bar button.btn-stop { background: #c0392b; }
    .top-bar button.btn-stop:hover { background: #a93226; }

    /* ── Page content ───────────────────────────────────────────── */
    .page { padding: 16px 20px; }

    /* ── Scan progress banner ───────────────────────────────────── */
    #progress-banner {
      display: none;
      background: #fff8e1; border: 1px solid #f9a825;
      border-radius: 6px; padding: 12px 16px; margin-bottom: 16px;
      align-items: center; gap: 16px;
    }
    #progress-banner.active { display: flex; }
    .spinner {
      width: 20px; height: 20px; flex-shrink: 0;
      border: 3px solid #f9a825; border-top-color: #e65100;
      border-radius: 50%; animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    #progress-text { flex: 1; font-size: 14px; }
    #progress-count { font-weight: bold; font-size: 16px; }
    #progress-dir { font-size: 12px; color: #888; margin-top: 3px;
                    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

    /* ── Metadata info bar ──────────────────────────────────────── */
    .meta-bar {
      display: flex; flex-wrap: wrap; gap: 10px;
      background: white; border-radius: 6px;
      padding: 12px 16px; margin-bottom: 16px;
      border: 1px solid #dde1e7;
    }
    .meta-card {
      display: flex; flex-direction: column;
      padding: 6px 16px; border-right: 1px solid #e0e4ea; min-width: 140px;
    }
    .meta-card:last-child { border-right: none; }
    .meta-card label { font-size: 11px; text-transform: uppercase;
                       color: #888; letter-spacing: 0.5px; margin-bottom: 3px; }
    .meta-card span { font-size: 14px; font-weight: 600; color: #1a1f36; word-break: break-all; }

    /* ── Search + filter row ────────────────────────────────────── */
    .toolbar {
      display: flex; align-items: center; gap: 12px;
      background: white; border: 1px solid #dde1e7;
      border-radius: 6px; padding: 10px 14px; margin-bottom: 12px; flex-wrap: wrap;
    }
    .toolbar input[type=text], .toolbar input[list] {
      padding: 6px 12px; border: 1px solid #ccc; border-radius: 4px;
      font-size: 14px; outline: none;
    }
    .toolbar input[type=text]:focus, .toolbar input[list]:focus {
      border-color: #4a90d9; box-shadow: 0 0 0 2px rgba(74,144,217,0.15);
    }
    #search-input { width: 280px; }
    #ext-input { width: 180px; }
    .toolbar button {
      padding: 6px 14px; background: #4a90d9; color: white;
      border: none; border-radius: 4px; cursor: pointer; font-size: 13px;
    }
    .toolbar button:hover { background: #357abd; }
    .toolbar button.btn-ghost {
      background: none; color: #555; border: 1px solid #ccc;
    }
    .toolbar button.btn-ghost:hover { background: #f5f5f5; }
    .toolbar-sep { color: #ccc; }

    /* ── Table ──────────────────────────────────────────────────── */
    .table-wrap { background: white; border-radius: 6px;
                  border: 1px solid #dde1e7; overflow: clip; }
    .table-meta {
      display: flex; align-items: center; justify-content: space-between;
      padding: 8px 14px; border-bottom: 1px solid #eee;
      font-size: 13px; color: #555;
    }
    .table-meta a { color: #4a90d9; text-decoration: none; }
    .table-meta a:hover { text-decoration: underline; }

    table { border-collapse: collapse; width: 100%; table-layout: fixed; }
    col.col-name     { width: 17%; }
    col.col-path     { width: 42%; }
    col.col-size     { width: 9%; }
    col.col-modified { width: 16%; }
    col.col-actions  { width: 16%; }

    thead th {
      background: #f7f8fa; border-bottom: 2px solid #dde1e7;
      padding: 9px 12px; text-align: left; white-space: nowrap;
      position: sticky; top: 48px; z-index: 10;
    }
    thead th a {
      color: #444; text-decoration: none;
      display: inline-flex; align-items: center; gap: 4px;
    }
    thead th a:hover { color: #4a90d9; }
    thead th.sorted { background: #eef3fb; }

    td { padding: 7px 12px; border-bottom: 1px solid #eee;
         overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    tr.file:hover td { background: #f0f6ff; }
    tr.file:last-child td { border-bottom: none; }

    td.col-name { font-weight: 500; }
    td.col-path { color: #555; font-size: 13px; }
    td.col-size { text-align: right; color: #555; }
    td.col-modified { font-size: 13px; color: #666; }
    td.col-actions { white-space: nowrap; }

    .link-open   { color: #4a90d9; text-decoration: none; font-size: 12px; }
    .link-folder { color: #888; text-decoration: none; font-size: 12px; margin-left: 8px; }
    .link-open:hover   { text-decoration: underline; }
    .link-folder:hover { color: #4a90d9; text-decoration: underline; }

    .no-results { text-align: center; padding: 32px; color: #888; font-style: italic; }

    /* ── Pagination ─────────────────────────────────────────────── */
    .pagination {
      display: flex; align-items: center; gap: 10px;
      padding: 12px 14px; border-top: 1px solid #eee; font-size: 13px;
    }
    .pagination a {
      padding: 5px 14px; background: #4a90d9; color: white;
      text-decoration: none; border-radius: 4px; font-size: 13px;
    }
    .pagination a.disabled { background: #ccc; pointer-events: none; }
  </style>
</head>
<body>

  <!-- ── Sticky top bar ── -->
  <div class="top-bar">
    <h1>Mnemosylva</h1>
    <form method="POST" action="/action">
      <button name="action" value="initialize">Initialize</button>
      <label><input type="checkbox" name="clear"> Clear index</label>
      <span style="color:#555">|</span>
      <button name="action" value="scan">Scan</button>
      <input type="text" name="scan_dir" placeholder="Directory (default: home)">
      <label><input type="checkbox" name="demo"> Demo</label>
      <button name="action" value="stop" class="btn-stop">Stop</button>
    </form>
  </div>

  <div class="page">

    <!-- ── Progress banner ── -->
    <div id="progress-banner" {% if scanning %}class="active"{% endif %}>
      <div class="spinner"></div>
      <div id="progress-text">
        Scanning &mdash; <span id="progress-count">{{ progress_count }}</span> files indexed
        <div id="progress-dir">{{ progress_dir }}</div>
      </div>
    </div>

    <!-- ── Metadata info bar ── -->
    <div class="meta-bar">
      <div class="meta-card">
        <label>Directory</label>
        <span title="{{ meta.get('scan_dir','') }}">{{ meta.get('scan_dir', '—') }}</span>
      </div>
      <div class="meta-card">
        <label>Files Indexed</label>
        <span>{{ "{:,}".format(meta.get('file_count', 0)) if meta else '—' }}</span>
      </div>
      <div class="meta-card">
        <label>Scan Started</label>
        <span>{{ meta.get('start_time', '—') }}</span>
      </div>
      <div class="meta-card">
        <label>Scan Ended</label>
        <span>{{ meta.get('end_time', '—') }}</span>
      </div>
      <div class="meta-card">
        <label>Unique Types</label>
        <span>{{ meta.get('file_types', {})|length if meta else '—' }}</span>
      </div>
    </div>

    <!-- ── Search + filter toolbar ── -->
    <div class="toolbar">
      <form method="GET" action="/" id="search-form" style="display:contents">
        <input type="hidden" name="show_junk" value="{{ '1' if show_junk else '0' }}">
        <input type="hidden" name="sort" value="{{ sort }}">
        <input type="hidden" name="dir" value="{{ direction }}">
        <input type="text" name="q" id="search-input"
               value="{{ search_query }}" placeholder="Search filenames…" autocomplete="off">
        <button type="submit">Search</button>
        {% if search_query %}
          <a href="{{ url_for('index', page=1, show_junk='1' if show_junk else '0', sort=sort, dir=direction) }}"
             style="font-size:13px; color:#888; text-decoration:none;">✕ Clear</a>
        {% endif %}
      </form>

      <span class="toolbar-sep">|</span>

      <!-- Searchable extension filter -->
      <input list="ext-list" id="ext-input" placeholder="Filter by extension…" autocomplete="off">
      <datalist id="ext-list">
        {% for t in types %}
          <option value="{{ t }}">
        {% endfor %}
      </datalist>
      <button class="btn-ghost" onclick="applyExtFilter()">Apply</button>
      <button class="btn-ghost" onclick="clearExtFilter()">Show All</button>

      <span class="toolbar-sep">|</span>

      {% if show_junk %}
        <a href="{{ url_for('index', page=1, show_junk='0', q=search_query, sort=sort, dir=direction) }}"
           style="font-size:13px; color:#888; text-decoration:none;">Hide system files</a>
      {% else %}
        <a href="{{ url_for('index', page=1, show_junk='1', q=search_query, sort=sort, dir=direction) }}"
           style="font-size:13px; color:#888; text-decoration:none;">Show system files</a>
      {% endif %}
    </div>

    <!-- ── File table ── -->
    <div class="table-wrap">
      <div class="table-meta">
        <span>
          {% if search_query %}
            <b>{{ total }}</b> result(s) for "<b>{{ search_query }}</b>"
          {% else %}
            <b>{{ "{:,}".format(total) }}</b> files{% if not show_junk %} (system files hidden){% endif %}
          {% endif %}
        </span>
      </div>

      <table>
        <colgroup>
          <col class="col-name">
          <col class="col-path">
          <col class="col-size">
          <col class="col-modified">
          <col class="col-actions">
        </colgroup>
        <thead>
          <tr>
            {% set cols = [('name','Name'), ('path','Path'), ('size','Size'), ('modified','Modified')] %}
            {% for col_key, col_label in cols %}
              {% set is_sorted = (sort == col_key) %}
              {% set next_dir = 'asc' if (is_sorted and direction == 'desc') else 'desc' %}
              <th {% if is_sorted %}class="sorted"{% endif %}>
                <a href="{{ url_for('index', page=1, sort=col_key, dir=next_dir,
                                    show_junk='1' if show_junk else '0', q=search_query) }}">
                  {{ col_label }}
                  {% if is_sorted %}{{ '▲' if direction == 'asc' else '▼' }}{% else %}<span style="color:#bbb">⇅</span>{% endif %}
                </a>
              </th>
            {% endfor %}
            <th>Actions</th>
          </tr>
        </thead>
        <tbody id="file-tbody">
          {% for f in files %}
          {# f: (name, path, size_raw, size_label, modified, ext, dirname) #}
          <tr class="file" data-ext="{{ f[5] }}" data-name="{{ f[0]|lower }}">
            <td class="col-name" title="{{ f[0] }}">{{ f[0] }}</td>
            <td class="col-path" title="{{ f[1] }}">{{ f[1] }}</td>
            <td class="col-size">{{ f[3] }}</td>
            <td class="col-modified">{{ f[4] }}</td>
            <td class="col-actions">
              <a class="link-open"   href="file://{{ f[1] }}" target="_blank">Open</a>
              <a class="link-folder" href="file://{{ f[6] }}" target="_blank">Folder ↗</a>
            </td>
          </tr>
          {% endfor %}
          {% if not files %}
          <tr><td colspan="5" class="no-results">No files found.</td></tr>
          {% endif %}
        </tbody>
      </table>

      <!-- Pagination inside the card -->
      <div class="pagination">
        {% if page > 1 %}
          <a href="{{ url_for('index', page=page-1, show_junk='1' if show_junk else '0',
                              q=search_query, sort=sort, dir=direction) }}">&larr; Prev</a>
        {% else %}
          <a class="disabled">&larr; Prev</a>
        {% endif %}

        <span>Page <b>{{ page }}</b> of <b>{{ total_pages }}</b></span>

        {% if page < total_pages %}
          <a href="{{ url_for('index', page=page+1, show_junk='1' if show_junk else '0',
                              q=search_query, sort=sort, dir=direction) }}">Next &rarr;</a>
        {% else %}
          <a class="disabled">Next &rarr;</a>
        {% endif %}
      </div>
    </div>

  </div><!-- .page -->

  <script>
    // ── Extension filter (datalist, client-side) ─────────────────
    function applyExtFilter() {
      const ext = document.getElementById('ext-input').value.trim();
      document.querySelectorAll('#file-tbody tr.file').forEach(row => {
        row.style.display = (!ext || row.dataset.ext === ext) ? '' : 'none';
      });
    }
    function clearExtFilter() {
      document.getElementById('ext-input').value = '';
      document.querySelectorAll('#file-tbody tr.file').forEach(row => {
        row.style.display = '';
      });
    }
    document.getElementById('ext-input').addEventListener('change', applyExtFilter);

    // ── Live filename search (client-side, current page) ─────────
    document.getElementById('search-input').addEventListener('input', function () {
      const term = this.value.toLowerCase();
      document.querySelectorAll('#file-tbody tr.file').forEach(row => {
        row.style.display = row.dataset.name.includes(term) ? '' : 'none';
      });
    });

    // ── Scan progress polling ─────────────────────────────────────
    const banner     = document.getElementById('progress-banner');
    const countEl    = document.getElementById('progress-count');
    const dirEl      = document.getElementById('progress-dir');

    function startPolling() {
      banner.classList.add('active');
      const interval = setInterval(async () => {
        try {
          const data = await fetch('/status').then(r => r.json());
          countEl.textContent = data.file_count.toLocaleString();
          dirEl.textContent   = data.current_dir;
          if (!data.scanning) {
            clearInterval(interval);
            setTimeout(() => window.location.reload(), 800);
          }
        } catch (e) { /* server not yet ready */ }
      }, 1000);
    }

    if ({{ 'true' if scanning else 'false' }}) { startPolling(); }
  </script>
</body>
</html>
'''

@app.route('/status')
def status():
    return jsonify({
        'scanning': SCANNING,
        'file_count': SCAN_PROGRESS.get('file_count', 0),
        'current_dir': SCAN_PROGRESS.get('current_dir', '')
    })

@app.route('/')
def index():
    page         = max(1, request.args.get('page', 1, type=int))
    show_junk    = request.args.get('show_junk', '0') == '1'
    search_query = request.args.get('q', '').strip()
    sort         = request.args.get('sort', 'modified')
    direction    = request.args.get('dir', 'desc')

    if sort not in VALID_SORT_COLS:
        sort = 'modified'
    if direction not in ('asc', 'desc'):
        direction = 'desc'

    where, params = build_where_clause(show_junk, search_query or None)
    order_by = f"ORDER BY {VALID_SORT_COLS[sort]} {direction.upper()}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(f"SELECT COUNT(*) FROM files {where}", params)
    total = c.fetchone()[0]
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    offset = (page - 1) * PER_PAGE

    c.execute(
        f"SELECT name, path, size, modified FROM files {where} {order_by} LIMIT ? OFFSET ?",
        params + [PER_PAGE, offset]
    )
    raw_files = c.fetchall()
    conn.close()

    # Build enriched file tuples:
    # (name, path, size_raw, size_label, modified, ext, dirname)
    files = [
        (
            name,
            path,
            size,
            format_size(size),
            modified,
            os.path.splitext(name)[1].lower(),
            os.path.dirname(path)
        )
        for name, path, size, modified in raw_files
    ]

    if SCAN_METADATA.get('file_types'):
        types = sorted(ext for ext in SCAN_METADATA['file_types'] if ext)
    else:
        types = []

    return render_template_string(
        HTML_TEMPLATE,
        files=files,
        meta=SCAN_METADATA,
        types=types,
        page=page,
        total_pages=total_pages,
        total=total,
        show_junk=show_junk,
        search_query=search_query,
        sort=sort,
        direction=direction,
        scanning=SCANNING,
        progress_count=SCAN_PROGRESS.get('file_count', 0),
        progress_dir=SCAN_PROGRESS.get('current_dir', '')
    )

@app.route('/action', methods=['POST'])
def action():
    global SCANNER_THREAD, DEMO_MODE, SCANNING
    action_type = request.form.get('action')
    demo = 'demo' in request.form
    scan_dir = request.form.get('scan_dir') or SCAN_DIR

    if action_type == 'initialize':
        if 'clear' in request.form:
            clear_index()
        create_db()
    elif action_type == 'scan':
        DEMO_MODE = demo
        if not SCANNING:
            SCANNER_THREAD = threading.Thread(
                target=scan_directory, args=(scan_dir, DEMO_MODE, VERBOSE)
            )
            SCANNER_THREAD.start()
    elif action_type == 'stop':
        SCANNING = False

    return redirect(url_for('index'))

# --- MAIN ---
if __name__ == '__main__':
    create_db()
    webbrowser.open('http://127.0.0.1:5000')
    app.run(debug=False)
