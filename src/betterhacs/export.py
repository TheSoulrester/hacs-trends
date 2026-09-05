"""Statischer Export: aus der SQLite wird eine einzelne JSON, die die Seite lädt.

Bewusst klein gehalten — die Datei geht bei jedem Seitenaufruf über die Leitung.
Kurze Schlüssel, keine Null-Felder, Datumswerte auf den Tag gekürzt.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from .config import Config
from .db import InstallSnapshot, Repo, Snapshot, make_engine, make_session_factory
from .metrics import (
    HealthThresholds,
    activity_percentiles,
    classify_health,
    compute_install_deltas,
    compute_star_deltas,
    coverage,
    load_github_activity,
    snapshot_days,
)
from .sources.analytics import map_repos_to_domains

log = logging.getLogger(__name__)


def _iso_day(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)[:10]


def build_payload(session, today: date | None = None) -> dict:
    today = today or session.scalar(select(func.max(Snapshot.day)))
    if today is None:
        raise RuntimeError("Keine Snapshots in der Datenbank — erst 'betterhacs sync' laufen lassen.")

    star_deltas, star_refs = compute_star_deltas(session, today)
    install_deltas = compute_install_deltas(session, today)
    gh = load_github_activity(session)
    thresholds = HealthThresholds()
    now = datetime.now(timezone.utc)

    installs_today = {
        d: t
        for d, t in session.execute(
            select(InstallSnapshot.domain, InstallSnapshot.total).where(InstallSnapshot.day == today)
        )
    }

    rows = session.execute(
        select(
            Repo.id,
            Repo.full_name,
            Repo.manifest_name,
            Repo.category,
            Repo.description,
            Repo.domain,
            Repo.topics,
            Repo.first_seen,
            Repo.is_critical,
            Snapshot.stars,
            Snapshot.downloads,
            Snapshot.open_issues,
            Snapshot.last_updated,
            Snapshot.last_version,
        )
        .join(Snapshot, Snapshot.repo_id == Repo.id)
        .where(Snapshot.day == today)
    ).all()

    # Mehrdeutige Domains ermitteln: mehrere Repos, die dieselbe Domain beanspruchen.
    class _R:
        __slots__ = ("id", "domain")

        def __init__(self, i, d):
            self.id, self.domain = i, d

    mapping, ana_report = map_repos_to_domains(
        [_R(r.id, r.domain) for r in rows], {d: type("E", (), {"total": t})() for d, t in installs_today.items()}
    )

    repos = []
    for r in rows:
        info = gh.get(r.id, {})
        # Nach der Anreicherung ist pushed_at das bessere Aktivitaetsmass;
        # vorher bleibt nur last_updated aus dem HACS-Datensatz.
        activity = info.get("pushed_at") or r.last_updated
        health, age = classify_health(
            last_activity=activity,
            is_archived=info.get("is_archived"),
            is_unavailable=bool(info.get("unavailable")),
            now=now,
            thresholds=thresholds,
        )
        sd = star_deltas.get(r.id)
        dom_entry = mapping.get(r.id)
        inst = installs_today.get(r.domain) if r.domain else None
        idl = install_deltas.get(r.domain) if r.domain else None

        item = {
            "id": r.id,
            "n": r.full_name,
            "c": r.category,
        }
        if r.manifest_name and r.manifest_name != r.full_name.split("/")[-1]:
            item["t"] = r.manifest_name
        if r.description:
            item["d"] = r.description[:300]
        if r.stars is not None:
            item["s"] = r.stars
        if r.downloads is not None:
            item["dl"] = r.downloads
        if r.open_issues:
            item["oi"] = r.open_issues
        if r.last_version:
            item["v"] = r.last_version
        if activity:
            item["lu"] = _iso_day(activity)
        if age is not None:
            item["age"] = age
        item["h"] = health
        if r.domain:
            item["dom"] = r.domain
        if inst is not None:
            item["inst"] = inst
            if dom_entry and dom_entry[1]:
                item["amb"] = 1  # Domain von mehreren Repos beansprucht
        if sd:
            for key, val in (("d7", sd.d7), ("d30", sd.d30)):
                if val is not None:
                    item[key] = val
            for key, val in (("p7", sd.p7), ("p30", sd.p30)):
                if val is not None:
                    item[key] = round(val, 1)
        if idl:
            for key, val in (("i7", idl.d7), ("i30", idl.d30)):
                if val is not None:
                    item[key] = val
        if r.is_critical:
            item["crit"] = 1
        try:
            topics = json.loads(r.topics or "[]")[:6]
            if topics:
                item["tp"] = topics
        except ValueError:
            pass
        item["fs"] = _iso_day(r.first_seen)
        repos.append(item)

    repos.sort(key=lambda x: -(x.get("s") or 0))

    days = snapshot_days(session)
    cov = coverage(session, today)
    meta = {
        "generated_at": now.isoformat(timespec="seconds"),
        "day": today.isoformat(),
        "history_days": len(days),
        "first_snapshot": days[0].isoformat() if days else None,
        "reference_days": {str(k): (v.isoformat() if v else None) for k, v in star_refs.items()},
        "coverage": cov,
        "analytics": {
            "matched": ana_report.matched,
            "repos_with_domain": ana_report.repos_with_domain,
            "ambiguous_domains": ana_report.ambiguous_domains,
        },
        "activity_percentiles": activity_percentiles(session, today),
        "thresholds": {
            "active": thresholds.active,
            "quiet": thresholds.quiet,
            "stale": thresholds.stale,
        },
        "enriched": bool(gh),
        "counts": {"repos": len(repos)},
    }
    return {"meta": meta, "repos": repos}


def export(config: Config, out_path: Path | None = None) -> Path:
    engine = make_engine(config.db_path)
    Session = make_session_factory(engine)
    out_path = out_path or (config.db_path.parent.parent / "docs" / "data.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Session() as session:
        payload = build_payload(session)
    out_path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    size = out_path.stat().st_size
    log.info("Export: %s (%d Repos, %.1f KB)", out_path, len(payload["repos"]), size / 1024)
    return out_path
