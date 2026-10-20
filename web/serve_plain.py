"""Like GitHub Pages: plain static server, no COOP/COEP headers (tests coi-sw.js).  python -I serve_plain.py"""
import functools, http.server, os
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "out")
http.server.ThreadingHTTPServer(("127.0.0.1", 8766), functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)).serve_forever()
