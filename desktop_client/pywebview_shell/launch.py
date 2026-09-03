"""
Primary desktop shell using pywebview (WebView2 on Windows).
"""
import json
import os
import sys
import webview
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from desktop_client.base_shell import BaseShell
import config


class Api:
    def __init__(self, api_base_url):
        self._api_base_url = api_base_url
        self._is_maximized = False
        self._old_size = (1280, 720)
        self._old_pos = (0, 0)
        self._win = None

    def set_window(self, win):
        self._win = win

    def get_config(self):
        return {
            "API_KEY": config.API_KEY,
            "API_BASE_URL": self._api_base_url,
            "USE_EXTERNAL_CDN": not config.is_mock_mode()
        }

    def minimize(self):
        if self._win:
            self._win.minimize()

    def toggle_maximize(self):
        if not self._win:
            return
        if self._is_maximized:
            self._win.resize(self._old_size[0], self._old_size[1])
            self._win.move(self._old_pos[0], self._old_pos[1])
            self._is_maximized = False
        else:
            self._old_size = (self._win.width, self._win.height)
            self._old_pos = (self._win.x, self._win.y)
            try:
                import webview
                screens = webview.screens
                if screens:
                    s = screens[0]
                    self._win.move(0, 0)
                    self._win.resize(s.width, s.height - 40)
                    self._is_maximized = True
                else:
                    self._win.maximize()
                    self._is_maximized = True
            except Exception as e:
                print("Failed to maximize:", e)
                self._win.maximize()
                self._is_maximized = True

    def close_window(self):
        if self._win:
            self._win.destroy()

class PyWebViewShell(BaseShell):
    def launch(self, frontend_path: str, api_base_url: str) -> None:
        webview.settings['IGNORE_SSL_ERRORS'] = True
        index_file = os.path.join(frontend_path, "dist", "index.html")
        if not os.path.exists(index_file):
            raise FileNotFoundError(f"Frontend index not found at: {index_file}")
            
        api = Api(api_base_url)
        window = webview.create_window(
            title="CCTV Unified - Operator Dashboard", 
            url=index_file,
            width=1280,
            height=720,
            min_size=(1024, 600),
            background_color='#f0f2f5',
            frameless=False,
            easy_drag=False,
            js_api=api
        )
        api.set_window(window)
        
        def on_loaded(win):
            # Inject the real API key/base URL into the frontend now that the
            # page has loaded. Values are escaped with json.dumps() rather than
            # raw f-string interpolation to avoid JS injection via config values.
            win.evaluate_js(
                f"window.API_KEY = {json.dumps(config.API_KEY)}; "
                f"window.API_BASE_URL = {json.dumps(api_base_url)};"
                f"window.USE_EXTERNAL_CDN = {json.dumps(not config.is_mock_mode())};"
            )

        webview.start(on_loaded, window, http_server=True, debug=False)

if __name__ == "__main__":
    shell = PyWebViewShell()
    frontend_dir = str(Path(__file__).resolve().parent.parent / "frontend")
    
    # Check if TLS certs exist in the root directory
    root_dir = Path(__file__).resolve().parent.parent.parent
    if (root_dir / "key.pem").exists() and (root_dir / "cert.pem").exists():
        protocol = "https"
    else:
        protocol = "http"
        
    api_url = f"{protocol}://{os.getenv('API_HOST', '127.0.0.1')}:{config.API_PORT}"
    shell.launch(frontend_dir, api_url)
