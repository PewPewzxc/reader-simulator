"""Like GitHub Pages: plain static server, no COOP/COEP headers (tests coi-sw.js), site under /reader-simulator/.
  python -I serve_plain.py [folder] [port]    (default ../site/preview on http://127.0.0.1:8766/reader-simulator/)"""
import functools, http.server, os, sys
here = os.path.dirname(os.path.abspath(__file__))
root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "site", "preview")
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8766
BASE = "/reader-simulator"


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if not path.startswith(BASE + "/"):
            return os.path.join(root, "__not_here__")  # 404 outside the project path, like Pages
        return super().translate_path(path[len(BASE):])


http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=root)).serve_forever()
