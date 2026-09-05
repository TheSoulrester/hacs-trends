"""A stand-in for GitHub's stargazer endpoint, so the bootstrap can be tested without
spending an hour and 7,000 real requests."""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

PER_PAGE = 100
REPOS = {
    "acme/big": 250,       # 3 pages
    "acme/exact": 200,     # exactly 2 pages - the boundary case
    "acme/small": 7,       # 1 page, no Link header
    "acme/empty": 0,       # no stars at all
    "acme/gone": -1,       # 404
}


def _stars(n: int, seed: int) -> list[dict]:
    rnd = random.Random(seed)
    start = date(2021, 1, 1)
    days = sorted(rnd.randint(0, 1700) for _ in range(n))
    return [
        {"starred_at": (start + timedelta(days=d)).isoformat() + "T12:00:00Z",
         "user": {"login": f"u{i}"}}
        for i, d in enumerate(days)
    ]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        parts = u.path.strip("/").split("/")
        if len(parts) != 4 or parts[0] != "repos" or parts[3] != "stargazers":
            return self._send(404, {"message": "Not Found"})
        full = f"{parts[1]}/{parts[2]}"
        if full not in REPOS or REPOS[full] < 0:
            return self._send(404, {"message": "Not Found"})
        if self.headers.get("Accept") != "application/vnd.github.v3.star+json":
            # Exactly what GitHub does without the media type: bare users, no timestamps.
            return self._send(200, [{"login": "u1"}])

        total = REPOS[full]
        page = int(parse_qs(u.query).get("page", ["1"])[0])
        allstars = _stars(total, hash(full) % 1000)
        chunk = allstars[(page - 1) * PER_PAGE : page * PER_PAGE]
        last = max(1, -(-total // PER_PAGE))
        headers = {}
        if last > 1:
            headers["Link"] = (
                f'<http://x/repos/{full}/stargazers?per_page=100&page={last}>; rel="last"'
            )
        self._send(200, chunk, headers)

    def _send(self, code, body, extra=None):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-RateLimit-Remaining", "4999")
        self.send_header("X-RateLimit-Reset", "9999999999")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)


def serve(port=8731):
    return HTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    serve().serve_forever()
