"""Datenmodell. Schlüssel ist überall die GitHub-Repo-ID, nie der Name —
Repositories werden umbenannt, IDs nicht."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Repo(Base):
    """Stammdaten aus dem HACS-Datensatz."""

    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # GitHub-Repo-ID
    category: Mapped[str] = mapped_column(String(32), index=True)
    full_name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    manifest_name: Mapped[str | None] = mapped_column(String(255))
    domain: Mapped[str | None] = mapped_column(String(128), index=True)
    topics: Mapped[str] = mapped_column(Text, default="[]")  # JSON-Array
    country: Mapped[str | None] = mapped_column(String(64))

    first_seen: Mapped[date] = mapped_column(Date, index=True)
    last_seen: Mapped[date] = mapped_column(Date, index=True)

    # Aus /removed/data.json bzw. /critical/data.json
    is_removed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    removal_type: Mapped[str | None] = mapped_column(String(128))
    removal_reason: Mapped[str | None] = mapped_column(Text)
    removal_link: Mapped[str | None] = mapped_column(Text)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class RepoGithub(Base):
    """Anreicherung über die GitHub-GraphQL-API. Liefert die Felder, die HACS nicht hat —
    vor allem pushed_at (echtes Commit-Datum) und is_archived."""

    __tablename__ = "repo_github"

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    name_with_owner: Mapped[str | None] = mapped_column(String(255))
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_tag: Mapped[str | None] = mapped_column(String(128))
    is_archived: Mapped[bool | None] = mapped_column(Boolean, index=True)
    is_fork: Mapped[bool | None] = mapped_column(Boolean)
    is_disabled: Mapped[bool | None] = mapped_column(Boolean)
    license_key: Mapped[str | None] = mapped_column(String(64))
    fork_count: Mapped[int | None] = mapped_column(Integer)
    primary_language: Mapped[str | None] = mapped_column(String(64))
    homepage: Mapped[str | None] = mapped_column(Text)
    # Wenn GitHub das Repo nicht mehr kennt (gelöscht/privat), steht hier der Grund.
    unavailable: Mapped[str | None] = mapped_column(String(64), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Snapshot(Base):
    """Ein Messpunkt je Repo und Tag. Basis für alle Delta-Werte.
    Läuft der Sync mehrmals am Tag, gewinnt der letzte Lauf des Tages."""

    __tablename__ = "snapshots"

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Bewusst nullable: im HACS-Datensatz fehlen stargazers_count bei ~400 und
    # downloads bei rund zwei Dritteln aller Repos. NULL heißt "kein Wert geliefert",
    # nicht "null Sterne" — das ist ein wichtiger Unterschied für jede Sortierung.
    stars: Mapped[int | None] = mapped_column(Integer)
    downloads: Mapped[int | None] = mapped_column(Integer)
    open_issues: Mapped[int | None] = mapped_column(Integer)
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_version: Mapped[str | None] = mapped_column(String(128))
    last_commit: Mapped[str | None] = mapped_column(String(64))


class InstallSnapshot(Base):
    """Installationszahlen aus der Home-Assistant-Analytik, je Domain und Tag.
    Opt-in-Stichprobe, kein Absolutwert."""

    __tablename__ = "installs"

    domain: Mapped[str] = mapped_column(String(128), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    total: Mapped[int] = mapped_column(Integer)


class InstallVersion(Base):
    """Installationen je Domain, Tag und Version — für Adoptionskurven neuer Releases."""

    __tablename__ = "installs_version"

    domain: Mapped[str] = mapped_column(String(128), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)


class StarEvent(Base):
    """Einzelne Stern-Zeitstempel aus dem einmaligen Bootstrap über die Stargazer-API.
    Nur die jüngsten ~35 Tage, nur damit die 7/30-Tage-Spalten ab Tag 1 gefüllt sind."""

    __tablename__ = "star_events"

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    starred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)


class BootstrapState(Base):
    """Fortschritt des Stern-Bootstraps, damit der Lauf nach einem Rate-Limit-Stopp
    oder Abbruch dort weitermacht, wo er aufgehört hat."""

    __tablename__ = "bootstrap_state"

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    stars_at_bootstrap: Mapped[int | None] = mapped_column(Integer)
    next_page: Mapped[int | None] = mapped_column(Integer)
    oldest_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class RemovedRepo(Base):
    """Die HACS-Blacklist als eigene Tabelle.

    Wichtiger Befund aus der Verifikation: kein einziges der 447 entfernten Repos taucht
    noch im aktuellen HACS-Datensatz auf — entfernt heißt wirklich entfernt. Die Liste
    ist deshalb kein Flag auf bestehenden Repos, sondern ein Nachschlagewerk: verschwindet
    ein Repo, das wir bisher verfolgt haben, steht hier der Grund.
    """

    __tablename__ = "removed_repos"

    repository: Mapped[str] = mapped_column(String(255), primary_key=True)
    removal_type: Mapped[str | None] = mapped_column(String(128), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[date] = mapped_column(Date)


class ListGap(Base):
    """Repos, die in der offiziellen HACS-Kategorieliste stehen, für die es aber
    keinen Datensatz gibt (aktuell 52).

    Das sind entweder frische Aufnahmen, die HACS' Datengenerator noch nicht erfasst hat,
    oder Repos, die auf GitHub verschwunden sind. Wird mitgeführt, weil ein plötzliches
    Anwachsen dieser Zahl bedeutet, dass die Quelle klemmt — und nicht, dass HACS
    schrumpft.
    """

    __tablename__ = "list_gaps"

    full_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    category: Mapped[str] = mapped_column(String(32))
    first_seen: Mapped[date] = mapped_column(Date)
    last_seen: Mapped[date] = mapped_column(Date, index=True)


class SourceEtag(Base):
    """ETags je Quell-URL. Unveränderte Quellen liefern 304 und kosten nichts —
    Rücksicht gegenüber einem von der Community bezahlten Endpunkt."""

    __tablename__ = "source_etags"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    etag: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    counts: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    notes: Mapped[str | None] = mapped_column(Text)
    duration_s: Mapped[float | None] = mapped_column(Float)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_engine(db_path, echo: bool = False):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", echo=echo, future=True)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        # WAL ist schneller, funktioniert aber nicht auf jedem Dateisystem
        # (Netzlaufwerke, FUSE-Mounts). Scheitert es, laeuft SQLite im Standardmodus
        # weiter — langsamer, aber korrekt. Kein Grund, den Lauf abzubrechen.
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine):
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)
