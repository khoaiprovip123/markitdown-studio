import os
import sys
import time
import socket
import threading
import webview
from app import app, VERSION

def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

def run_flask(port):
    # Disable logging in production build to run quietly
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    # Ensure static ffmpeg paths are loaded
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception:
        pass

    # Find a free port dynamically
    port = find_free_port()

    # Start Flask server thread
    flask_thread = threading.Thread(target=run_flask, args=(port,))
    flask_thread.daemon = True
    flask_thread.start()

    # Wait for Flask boot
    time.sleep(0.8)

    # Launch PyWebView native desktop window
    webview.create_window(
        title=f'MarkItDown Studio - Version {VERSION}',
        url=f'http://127.0.0.1:{port}',
        width=1366,
        height=800,
        min_size=(1024, 768),
        resizable=True
    )
    webview.start()
