"""Local test server with the two headers WebAssembly threads need (COOP/COEP).
  python -I serve.py [port]   -> http://127.0.0.1:8765/ (serves build/out)"""
import functools
import http.server
import os
import sys


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "out")
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=root)).serve_forever()
