#!/usr/bin/env python3
"""Serve the local test-videos.co.uk mirror over plain HTTP for Kodi (WASM) to browse.

Usage:
    python3 serve.py [--port 8000] [--dir vids]

Then in Kodi: Add video source -> http://<this-machine-ip>:8000/
Kodi's HTTP source browser reads the directory listing this serves, so you
can navigate bigbuckbunny/jellyfish/sintel -> format -> resolution and play
any file directly, or add the whole tree as a source.
"""
import argparse
import http.server
import os
import re
import socket
from pathlib import Path

DEFAULT_DIR = Path(__file__).parent / "vids"

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with HTTP Range support, needed for Kodi to seek."""

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        if not os.path.exists(path):
            self.send_error(404, "File not found")
            return None

        ctype = self.guess_type(path)
        f = open(path, "rb")
        fs = os.fstat(f.fileno())
        file_len = fs.st_size
        start, end = 0, file_len - 1

        range_header = self.headers.get("Range")
        if range_header:
            m = RANGE_RE.fullmatch(range_header.strip())
            if not m:
                self.send_error(416, "Invalid Range header")
                f.close()
                return None
            s, e = m.groups()
            if s:
                start = int(s)
                end = int(e) if e else file_len - 1
            elif e:
                start = max(0, file_len - int(e))
                end = file_len - 1
            if start > end or start >= file_len:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{file_len}")
                self.end_headers()
                f.close()
                return None
            end = min(end, file_len - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_len}")
        else:
            self.send_response(200)

        self.send_header("Content-type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Last-Modified", self.date_time_string(int(fs.st_mtime)))
        self.end_headers()

        f.seek(start)
        self._range_remaining = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "_range_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        bufsize = 64 * 1024
        while remaining > 0:
            chunk = source.read(min(bufsize, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--dir", default=str(DEFAULT_DIR))
    args = parser.parse_args()

    serve_dir = str(Path(args.dir).resolve())

    class Handler(RangeRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=serve_dir, **kw)

    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", args.port), Handler)

    ip = local_ip()
    print(f"Serving {serve_dir}")
    print(f"Point Kodi to: http://{ip}:{args.port}/  (or http://localhost:{args.port}/ if Kodi runs on this machine)")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
