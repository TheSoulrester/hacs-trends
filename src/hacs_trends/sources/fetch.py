"""Gemeinsame Abrufschicht: HTTP mit ETag-Unterstützung, optional aus Fixtures."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..config import USER_AGENT

log = logging.getLogger(__name__)


class SourceError(RuntimeError):
    """Die Quelle war nicht abrufbar oder hat unbrauchbare Daten geliefert.

    Wird bewusst laut geworfen statt still zu schlucken: ein Sync, der halbe Daten
    schreibt, ist schlimmer als ein Sync, der abbricht.
    """


@dataclass
class FetchResult:
    data: Any | None
    etag: str | None
    not_modified: bool = False
    from_fixture: bool = False


class Fetcher:
    def __init__(self, fixtures: Path | None = None, timeout: float = 60.0):
        self.fixtures = fixtures
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def get_json(
        self,
        url: str,
        *,
        fixture_name: str | None = None,
        etag: str | None = None,
    ) -> FetchResult:
        """Holt JSON. Liegt ein Fixture-Verzeichnis vor und enthält es die Datei,
        wird sie benutzt — so ist der Collector ohne Netzzugang entwickelbar."""
        if self.fixtures and fixture_name:
            path = self.fixtures / fixture_name
            if path.is_file():
                log.debug("fixture %s", path)
                return FetchResult(json.loads(path.read_text()), None, from_fixture=True)

        headers = {"If-None-Match": etag} if etag else {}
        try:
            resp = self._client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise SourceError(f"{url} nicht erreichbar: {exc}") from exc

        if resp.status_code == 304:
            return FetchResult(None, etag, not_modified=True)
        if resp.status_code != 200:
            raise SourceError(f"{url} antwortete mit HTTP {resp.status_code}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise SourceError(f"{url} lieferte kein gültiges JSON: {exc}") from exc

        return FetchResult(data, resp.headers.get("etag"))
