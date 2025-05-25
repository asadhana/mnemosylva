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

# Global state
DEMO_MODE = True
VERBOSE = True
SCANNING = False
SCANNER_THREAD = None
SCAN_METADATA = {}

# --- INITIAL SETUP ---
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

# --- SCANNER FUNCTION ---
def scan_directory(base_path, demo_mode=False, verbose=False):
    global SCANNING, SCAN_METADATA
    SCANNING = True
    start_time = datetime.now()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    file_count = 0
    extensions = []

    for root, dirs, files in os.walk(base_path):
        if not SCANNING:
            break
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
                hash = get_file_hash(full_path)
                c.execute("INSERT OR REPLACE INTO files (path, name, size, created, modified, hash) VALUES (?, ?, ?, ?, ?, ?)",
                          (full_path, name, size, created, modified, hash))
                ext = os.path.splitext(name)[1].lower()
                extensions.append(ext)
                if verbose:
                    print(f"Indexed: {full_path}")
                file_count += 1
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
        'file_types': dict(Counter(extensions))
    }

# --- FLASK APP ---
app = Flask(__name__)

@app.route('/')
def index():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, path, size, modified FROM files ORDER BY modified DESC LIMIT 100")
    files = c.fetchall()
#   c.execute("SELECT DISTINCT LOWER(SUBSTR(name, INSTR(name, '.', -1))) FROM files")
    c.execute("SELECT DISTINCT LOWER(SUBSTR(name, INSTR(name, '.'))) FROM files")
    types = [row[0] for row in c.fetchall() if row[0]]
    conn.close()
    html = '''
    <html><head><title>File Index</title>
    <script>
    function toggleFilter(ext) {
        const rows = document.querySelectorAll('table tr.file');
        rows.forEach(row => {
            if (!ext || row.dataset.ext === ext) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    }
    </script>
    </head>
    <body style="font-family:Arial">
    <h2>Indexed Files (Top 100 by Last Modified)</h2>
    <form method="POST" action="/action">
        <button name="action" value="initialize">Initialize</button>
        <label><input type="checkbox" name="clear"> Remove existing index</label>
        <button name="action" value="scan">Scan</button>
        <label>Directory: <input type="text" name="scan_dir" value="" /></label>
        <label><input type="checkbox" name="demo"> Demo mode</label>
        <button name="action" value="stop">Stop</button>
    </form>

    <h3>Scan Metadata</h3>
    <ul>
        <li><b>Start:</b> {{ meta.get('start_time') }}</li>
        <li><b>End:</b> {{ meta.get('end_time') }}</li>
        <li><b>File Count:</b> {{ meta.get('file_count') }}</li>
        <li><b>File Types:</b> {{ meta.get('file_types') }}</li>
    </ul>

    <h3>Filter by File Type</h3>
    {% for t in types %}
        <button onclick="toggleFilter('{{ t }}')">{{ t }}</button>
    {% endfor %}
    <button onclick="toggleFilter('')">Show All</button>

    <table border="1" cellpadding="5">
        <tr><th>Name</th><th>Path</th><th>Size (bytes)</th><th>Modified</th></tr>
        {% for f in files %}
        <tr class="file" data-ext="{{ f[0].split('.')[-1].lower() if '.' in f[0] else '' }}">
            <td>{{ f[0] }}</td>
            <td><a href="file://{{ f[1] }}" target="_blank">{{ f[1] }}</a></td>
            <td>{{ f[2] }}</td>
            <td>{{ f[3] }}</td>
        </tr>
        {% endfor %}
    </table></body></html>
    '''
    return render_template_string(html, files=files, meta=SCAN_METADATA, types=types)

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
            SCANNER_THREAD = threading.Thread(target=scan_directory, args=(scan_dir, DEMO_MODE, VERBOSE))
            SCANNER_THREAD.start()
    elif action_type == 'stop':
        SCANNING = False

    return redirect(url_for('index'))

# --- MAIN ENTRY POINT ---
if __name__ == '__main__':
    create_db()
    webbrowser.open('http://127.0.0.1:5000')
    app.run(debug=False)
