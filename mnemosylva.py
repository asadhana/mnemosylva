import os
import hashlib
import json
import sqlite3
from datetime import datetime
from flask import Flask, jsonify, render_template_string
import webbrowser

# --- CONFIGURATION ---
DB_PATH = 'file_index.db'
SCAN_DIR = os.path.expanduser('~')  # Scan user's home directory by default
DEMO_MODE = True   # Set to False for full scan
VERBOSE = True     # Set to False to suppress output

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

# --- HASH FUNCTION ---
def get_file_hash(path):
    try:
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        if VERBOSE:
            print(f"Hashing failed for {path}: {e}")
        return None

# --- SCANNER FUNCTION ---
def scan_directory(base_path, demo_mode=False, verbose=False):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    file_count = 0
    max_demo_files = 50

    for root, dirs, files in os.walk(base_path):
        if verbose:
            print(f"Scanning directory: {root}")
        for name in files:
            full_path = os.path.join(root, name)
            try:
                stat = os.stat(full_path)
                created = datetime.fromtimestamp(stat.st_ctime).isoformat()
                modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
                size = stat.st_size
                hash = get_file_hash(full_path)

                c.execute("INSERT OR REPLACE INTO files (path, name, size, created, modified, hash) VALUES (?, ?, ?, ?, ?, ?)",
                          (full_path, name, size, created, modified, hash))

                if verbose:
                    print(f"Indexed: {full_path}")

                file_count += 1
                if demo_mode and file_count >= max_demo_files:
                    if verbose:
                        print(f"Demo mode limit reached ({max_demo_files} files). Stopping scan.")
                    conn.commit()
                    conn.close()
                    return
            except Exception as e:
                if verbose:
                    print(f"Failed to index {full_path}: {e}")
                continue

    conn.commit()
    conn.close()

# --- FLASK APP ---
app = Flask(__name__)

@app.route('/')
def index():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, path, size, modified FROM files ORDER BY modified DESC LIMIT 100")
    files = c.fetchall()
    conn.close()

    html = '''
    <html><head><title>File Index</title></head>
    <body style="font-family:Arial">
    <h2>Indexed Files (Top 100 by Last Modified)</h2>
    <table border="1" cellpadding="5">
        <tr><th>Name</th><th>Path</th><th>Size (bytes)</th><th>Modified</th></tr>
        {% for f in files %}
        <tr>
            <td>{{ f[0] }}</td>
            <td><a href="file://{{ f[1] }}" target="_blank">{{ f[1] }}</a></td>
            <td>{{ f[2] }}</td>
            <td>{{ f[3] }}</td>
        </tr>
        {% endfor %}
    </table></body></html>
    '''
    return render_template_string(html, files=files)

# --- MAIN ENTRY POINT ---
if __name__ == '__main__':
    print("Setting up database and scanning directory...")
    create_db()
    scan_directory(SCAN_DIR, demo_mode=DEMO_MODE, verbose=VERBOSE)
    print("Launching web interface...")
    webbrowser.open('http://127.0.0.1:5000')
    app.run(debug=False)
