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
    adoption_share,
    installs_by_version,
    release_rhythm,
    activity_percentiles,
    classify_health,
    compute_install_deltas,
    compute_star_deltas,
    coverage,
    load_github_activity,
    snapshot_days,
)
from .sources.analytics import map_repos_to_domains
from .star_history import WINDOWS
from .star_history import coverage as star_coverage
from .star_history import window_sums

log = logging.getLogger(__name__)

# Below this many stars at the start of a window, a percentage says more about
# rounding than about growth. The star median across HACS is 13.
MIN_PCT_BASE = 25


def _iso_day(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)[:10]


def build_payload(session, today: date | None = None) -> dict:
    today = today or session.scalar(select(func.max(Snapshot.day)))
    if today is None:
        raise RuntimeError("Keine Snapshots in der Datenbank — erst 'hacs-trends sync' laufen lassen.")

    # Stars come from the bootstrapped history when it is there: an exact sum over
    # days, with no reference snapshot to pick and no tolerance to apply. Only if the
    # bootstrap has not run do we fall back to differencing our own snapshots, which
    # can offer 7 and 30 days at best and only after weeks of collecting.
    star_hist = star_coverage(session)
    use_history = star_hist["repos_with_history"] > 0
    star_windows = window_sums(session, today) if use_history else {}
    star_deltas, star_refs = compute_star_deltas(session, today)
    install_deltas = compute_install_deltas(session, today)
    gh = load_github_activity(session)
    thresholds = HealthThresholds()
    now = datetime.now(timezone.utc)

    versions_today = installs_by_version(session, today)
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
        # last_updated aus HACS ist bereits das echte Commit-Datum (nachgemessen).
        # pushed_at aus der Anreicherung dient nur als Rueckfallebene.
        activity = r.last_updated or info.get("pushed_at")
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

        # --- release rhythm and activity ---------------------------------
        ry = info.get("releases_year")
        if ry is not None:
            item["ry"] = ry
            if info.get("releases_capped"):
                item["ryc"] = 1
        if info.get("commits_year") is not None:
            item["cy"] = info["commits_year"]
        if info.get("commits_quarter"):
            item["cq"] = info["commits_quarter"]
        rel_at = info.get("released_at")
        if rel_at:
            item["rd"] = _iso_day(rel_at)
            item["ra"] = (now - (rel_at.replace(tzinfo=timezone.utc)
                                 if rel_at.tzinfo is None else rel_at)).days
        item["rh"] = release_rhythm(ry, rel_at, now)
        if info.get("forks"):
            item["fk"] = info["forks"]
        if info.get("open_issues") is not None:
            item["oi2"] = info["open_issues"]
        if info.get("license"):
            item["lic"] = info["license"]
        if info.get("is_archived"):
            item["arch"] = 1
        if r.domain:
            item["dom"] = r.domain
            versions = versions_today.get(r.domain)
            if versions:
                share = adoption_share(versions, r.last_version or info.get("latest_tag"))
                if share is not None:
                    item["va"] = share
        if inst is not None:
            item["inst"] = inst
            if dom_entry and dom_entry[1]:
                item["amb"] = 1  # Domain von mehreren Repos beansprucht
        if use_history:
            for n in WINDOWS:
                gained = star_windows.get(n, {}).get(r.id)
                if gained:
                    item[f"d{n}"] = gained
                    # Percentage is measured against where the repository stood at the
                    # start of the window, not where it stands now - otherwise a repo
                    # that doubled would report 50% growth.
                    if r.stars is not None:
                        base = r.stars - gained
                        if base >= MIN_PCT_BASE:
                            item[f"p{n}"] = round(gained / base * 100, 1)
        elif sd:
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
        "star_source": "history" if use_history else "snapshots",
        "star_windows": list(WINDOWS) if use_history else [7, 30],
        "star_history": star_hist,
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
        "adoption_domains": len(versions_today),
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
