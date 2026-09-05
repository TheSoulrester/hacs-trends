#!/usr/bin/env python3
"""Build a single self-contained HTML file: markup, styles, script, language packs
and data in one document. Used for the shareable preview; the deployed site keeps
them separate so only the active language is downloaded."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def build(data_path: Path, out: Path, strip_wrapper: bool = False) -> Path:
    html = (WEB / "index.html").read_text()
    app = (WEB / "app.js").read_text()
    data = data_path.read_text()
    bundle = {p.stem: json.loads(p.read_text()) for p in sorted((WEB / "i18n").glob("*.json"))}

    html = html.replace('<script src="./app.js"></script>', "<script>\n" + app + "\n</script>")
    html = html.replace('<script id="inline-i18n" type="application/json"></script>',
                        '<script id="inline-i18n" type="application/json">'
                        + json.dumps(bundle, ensure_ascii=False) + "</script>")
    html = html.replace('<script id="inline-data" type="application/json"></script>',
                        '<script id="inline-data" type="application/json">' + data + "</script>")

    if strip_wrapper:
        head = html.split("<head>", 1)[1].split("</head>", 1)[0]
        body = html.split("<body>", 1)[1].split("</body>", 1)[0]
        keep = [re.search(r"<title>.*?</title>", head, re.S).group(0),
                re.search(r'<link rel="stylesheet".*?>', head, re.S).group(0),
                re.search(r"<style>.*?</style>", head, re.S).group(0)]
        html = "\n".join(keep) + body

    out.write_text(html)
    return out


if __name__ == "__main__":
    data = Path(sys.argv[1]) if len(sys.argv) > 1 else WEB / "data.json"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "preview.html"
    strip = "--strip" in sys.argv
    p = build(data, out, strip)
    print(f"{p}  {p.stat().st_size / 1024 / 1024:.2f} MB")
