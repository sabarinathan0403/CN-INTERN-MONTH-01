"""
Desktop launcher for the Product Sentiment Dashboard.

Running this (instead of app.py directly) starts the Flask server in the
background and automatically opens your default browser to the dashboard.
This is the entry point used when packaging the app into a Windows .exe
with PyInstaller (see README.md, section "Build a Windows .exe").
"""
import threading
import time
import webbrowser
import sys
import os

# Make sure imports work whether run as a script or as a frozen .exe
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)

from app import app

HOST = '127.0.0.1'
PORT = 5000
URL = f'http://{HOST}:{PORT}'


def run_server():
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Give Flask a moment to start before opening the browser
    time.sleep(1.5)
    webbrowser.open(URL)

    print(f"Signal is running at {URL}")
    print("Close this window (or press Ctrl+C) to stop the app.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down.")
