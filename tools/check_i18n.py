#!/usr/bin/env python3
"""Guard the translation contract.

en.json is the source of truth. A translation may be incomplete — the page falls back
per key, so a partial file is useful from the first pull request. What must never
happen is a key that exists nowhere else (a typo that silently never renders) or a
placeholder that does not match, which would print {n} at the reader instead of a
number.

Unknown keys and placeholder mismatches fail the build. Missing keys are reported as
a count so contributors can see what is left without being blocked.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

I18N = Path(__file__).resolve().parents[1] / "web" / "i18n"
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def main() -> int:
    en_path = I18N / "en.json"
    if not en_path.is_file():
        print(f"missing {en_path}", file=sys.stderr)
        return 1
    en = json.loads(en_path.read_text())
    failed = False

    for path in sorted(I18N.glob("*.json")):
        if path.name == "en.json":
            continue
        data = json.loads(path.read_text())
        unknown = sorted(set(data) - set(en))
        missing = sorted(set(en) - set(data))
        bad_ph = []
        for key, value in data.items():
            if key in en and isinstance(value, str):
                if set(PLACEHOLDER.findall(value)) != set(PLACEHOLDER.findall(en[key])):
                    bad_ph.append(key)

        status = "ok"
        if unknown or bad_ph:
            status = "FAIL"
            failed = True
        pct = round(100 * (len(en) - len(missing)) / len(en))
        print(f"{path.name:<12} {status:<5} {pct:>3}% translated ({len(en) - len(missing)}/{len(en)})")
        for key in unknown:
            print(f"    unknown key, not in en.json: {key}")
        for key in bad_ph:
            print(f"    placeholders differ from en.json: {key}")
        if missing:
            print(f"    {len(missing)} not yet translated (falls back to English)")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
