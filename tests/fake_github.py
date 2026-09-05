"""A stand-in for GitHub's star history endpoint, so the bootstrap can be tested
without spending an hour and thousands of real requests."""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

PER_PAGE = 30
# repo -> number of weeks of history it has
REPOS = {
    "acme/old": 420,       # 14 pages, older than any depth we ask for
    "acme/exact": 60,      # exactly 2 pages - the boundary that must not fetch a third
    "acme/young": 9,       # less than one page, no trailing empty page
    "acme/empty": 0,       # exists, never starred
    "acme/gone": -1,       # 404
    "acme/broken": -2,     # returns a malformed bucket
}
WEEK0 = datetime(2026, 8, 30, tzinfo=timezone.utc)  # a Sunday


def _buckets(full: str, weeks: int, page: int):
    rnd = random.Random(hash(full) % 9999)
    out = []
    for i in range((page - 1) * PER_PAGE, min(page * PER_PAGE, weeks)):
        start = WEEK0 - timedelta(weeks=i)
        days = [rnd.randint(0, 5) for _ in range(7)]
        out.append({"week": int(start.timestamp()), "total": sum(days), "days": days})
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        parts = u.path.strip("/").split("/")
        if len(parts) != 5 or parts[0] != "repos" or parts[3:5] != ["stargazers", "history"]:
            return self._send(404, {"message": "Not Found"})
        full = f"{parts[1]}/{parts[2]}"
        if full not in REPOS or REPOS[full] == -1:
            return self._send(404, {"message": "Not Found"})
        page = int(parse_qs(u.query).get("page", ["1"])[0])
        if REPOS[full] == -2:
            return self._send(200, [{"week": 1, "total": 3}])  # days missing
        return self._send(200, _buckets(full, REPOS[full], page))

    def _send(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-RateLimit-Remaining", "4999")
        self.send_header("X-RateLimit-Reset", "9999999999")
        self.end_headers()
        self.wfile.write(raw)


def serve(port=8731):
    return HTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    serve().serve_forever()
