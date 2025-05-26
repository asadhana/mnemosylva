# Mnemosylva Documentation

Mnemosylva – mnemo- (memory) + sylva (forest) — “forest of memory”

This document provides a comprehensive overview of the Mnemosylva application, covering its usage and technical details.

## User Guide

This guide will help you set up and use Mnemosylva to index and browse your files.

### Prerequisites

*   **Python 3:** Mnemosylva is a Python application. You'll need Python 3 installed on your system. You can download it from [python.org](https://www.python.org/).
*   **Web Browser:** A modern web browser (like Chrome, Firefox, Edge, or Safari) is needed to access the user interface.

### Setup and Running the Application

1.  **Download:** Get the `mnemosylva.py` file.
2.  **Open a Terminal or Command Prompt:** Navigate to the directory where you saved `mnemosylva.py`.
3.  **Run the Application:** Execute the script using Python:
    ```bash
    python mnemosylva.py
    ```
4.  **Access the Web Interface:**
    *   The application should automatically attempt to open a new tab in your default web browser at `http://127.0.0.1:5000`.
    *   If it doesn't open automatically, manually open your web browser and go to `http://127.0.0.1:5000`.

### Using the Web Interface

The web interface allows you to manage the file index and browse its contents.

**1. Initializing the Database:**

*   Before you can scan any files, you need to initialize the database.
*   Click the **"Initialize"** button.
*   **Optional:** If you want to start with a completely fresh index (removing any previously indexed files), check the **"Remove existing index"** box *before* clicking "Initialize".

**2. Scanning Files:**

*   Once the database is initialized, you can start scanning directories.
*   **Specify Directory (Optional):**
    *   By default, Mnemosylva will scan your user's home directory (e.g., `/home/youruser` on Linux, `C:\Users\youruser` on Windows - note the double backslash for Windows paths in this documentation).
    *   To scan a different directory, type its full path into the **"Directory"** text field (e.g., `/mnt/data/photos` or `D:\Documents`).
*   **Demo Mode (Optional):**
    *   If you want to do a quick test scan, check the **"Demo mode"** box. This will limit the scan to a small number of files (currently 50). This is useful for quickly seeing how the application works without waiting for a full scan of a large directory.
*   **Start Scan:** Click the **"Scan"** button.
    *   The scan will run in the background. You can continue to use the application interface, but it might be less responsive during very intensive scanning.
    *   Console output (in the terminal where you ran `python mnemosylva.py`) will show verbose progress if `VERBOSE` is enabled (which it is by default).

**3. Monitoring Scan Progress & Metadata:**

*   The **"Scan Metadata"** section on the page will update after a scan is completed or stopped. It shows:
    *   **Start:** The time the last scan started.
    *   **End:** The time the last scan finished.
    *   **File Count:** The number of files processed in the last scan.
    *   **File Types:** A summary of the different file extensions found and how many of each.

**4. Stopping a Scan:**

*   If a scan is taking too long or you want to halt it for any reason, click the **"Stop"** button. The scan will stop, and any files indexed up to that point will be saved.

**5. Browsing and Filtering Indexed Files:**

*   **File Table:** The main part of the page displays a table of the "Top 100 by Last Modified" files from your index. For each file, it shows:
    *   **Name:** The file name.
    *   **Path:** The full path to the file. This is a clickable link (`file://...`) that *may* open the file directly on your computer, depending on your browser's security settings and operating system configuration.
    *   **Size (bytes):** The file size.
    *   **Modified:** The date and time the file was last modified.
*   **Filter by File Type:**
    *   Above the file table, you'll see buttons for each unique file extension found in the current view (e.g., `.txt`, `.jpg`, `.pdf`).
    *   Click any of these buttons to show *only* files of that type in the table.
    *   Click **"Show All"** to remove the filter and display all file types again.

**6. Shutting Down the Application:**

*   To stop the Mnemosylva application, go to the terminal or command prompt where you launched it and press `Ctrl+C`.

## Developer Guide

This section provides information for developers looking to understand, modify, or extend the Mnemosylva application.

### Core Technologies

*   **Python 3:** The application is written in Python 3.
*   **Flask:** A lightweight web framework used for the user interface. Key Flask concepts in use include routes (`@app.route`), request handling (`request` object), template rendering (`render_template_string`), and URL generation (`url_for`).
*   **SQLite3:** The `sqlite3` standard library module is used for all database operations. SQL queries are embedded directly in the Python code.
*   **HTML/JavaScript:** The frontend is a single HTML page with some inline JavaScript for client-side filtering.

### Project Structure

*   `mnemosylva.py`: This single file contains all the Python code for the application, including:
    *   Database setup and utility functions.
    *   The file scanning logic.
    *   Flask application definition and routes.
*   `file_index.db`: The SQLite database file that is created/used by the application. It's not part of the source code itself but is generated at runtime.
*   `.gitignore`: Standard file for ignoring generated files (like `__pycache__`, `*.db`).
*   `README.md`: Basic readme.

### Key Code Components

**1. Configuration (Global Variables):**

*   `DB_PATH`: Path to the database file.
*   `SCAN_DIR`: Default directory to scan.
*   `MAX_DEMO_FILES`: Limit for demo mode scans.
*   `DEMO_MODE`: Boolean flag, controlled by UI for scans.
*   `VERBOSE`: Boolean flag, controls console output during scans.
*   `SCANNING`: Boolean flag, indicates if a scan is active. Critical for controlling the scanner thread.
*   `SCANNER_THREAD`: Holds the `threading.Thread` object for the scanner.
*   `SCAN_METADATA`: Dictionary storing results from the last scan.

**2. Database (`create_db`, `clear_index`, `get_file_hash`):**

*   `create_db()`: Sets up the `files` table. Schema:
    *   `id` INTEGER PRIMARY KEY
    *   `path` TEXT UNIQUE
    *   `name` TEXT
    *   `size` INTEGER
    *   `created` TEXT (ISO datetime)
    *   `modified` TEXT (ISO datetime)
    *   `hash` TEXT (SHA256)
*   `clear_index()`: Empties the `files` table.
*   `get_file_hash(path)`: Calculates SHA256 hash. Errors are caught and printed if `VERBOSE` is true.

**3. Scanner (`scan_directory` function):**

*   Runs in a separate thread (`threading.Thread`) to keep the UI responsive.
*   Uses `os.walk` for directory traversal.
*   Collects file stats (`os.stat`) and hashes.
*   Uses `INSERT OR REPLACE INTO files ...` to add/update file records. This means re-scanning a directory will update existing entries based on the unique `path`.
*   Checks the `SCANNING` global flag in its loops to allow for early termination if the "Stop" button is pressed.
*   Populates `SCAN_METADATA` upon completion or stoppage.

**4. Flask Web Application (`app`):**

*   **`@app.route('/')` (index):**
    *   Fetches the 100 most recently modified files.
    *   Fetches distinct file extensions for the filter buttons.
    *   Renders an HTML string directly using `render_template_string`. The HTML includes inline CSS and JavaScript.
    *   Displays `SCAN_METADATA`.
*   **`@app.route('/action', methods=['POST'])` (action):**
    *   Handles form submissions from the main page.
    *   `action_type`: Determines whether to `initialize`, `scan`, or `stop`.
    *   Manages the `SCANNER_THREAD` lifecycle for scanning.
    *   Updates global `DEMO_MODE` based on form input.
    *   Redirects to `/` after the action.

**5. Main Execution (`if __name__ == '__main__':`)**

*   Calls `create_db()` to ensure DB is ready.
*   `webbrowser.open()`: Attempts to open the app in a browser for convenience.
*   `app.run(debug=False)`: Starts the Flask development server.

### Potential Areas for Extension or Modification

*   **Improved UI:**
    *   Separate HTML templates, CSS, and JS files instead of inline.
    *   Use a more robust frontend framework (e.g., Vue, React, or even just more structured vanilla JS).
    *   Add pagination for browsing large numbers of files.
    *   More advanced search and filtering capabilities (e.g., by name, date range, size range).
*   **Configuration File:**
    *   Move settings like `DB_PATH`, `SCAN_DIR`, `MAX_DEMO_FILES`, `VERBOSE` to an external configuration file (e.g., JSON, YAML, INI).
*   **Error Handling:**
    *   More graceful error handling and feedback in the UI (e.g., if a scan directory doesn't exist).
*   **Asynchronous Operations:**
    *   For the web app, consider using Flask with `async/await` or a framework like FastAPI if I/O-bound operations become a bottleneck beyond the current scanner thread.
*   **Database Migrations:**
    *   If the schema evolves, a simple migration system might be needed (though for its current scale, manual changes might suffice).
*   **File Content Indexing (Advanced):**
    *   Currently, it only indexes metadata. For full-text search, integrating a search engine library (e.g., Whoosh, Elasticsearch) would be a major extension.
*   **Security:**
    *   The `file://` links can be a security concern in some browsers or might not work as expected. Consider serving files through a dedicated Flask route if direct file system access is problematic (this would be a significant change).
    *   The application is designed for local use. If exposing it to a network, proper security hardening (authentication, input validation, etc.) would be critical.
*   **Packaging and Distribution:**
    *   Use `setuptools` or similar to create a proper Python package.
    *   Consider tools like PyInstaller to bundle it as a standalone executable.
