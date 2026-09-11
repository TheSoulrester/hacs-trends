"""Data model. The key is always the GitHub repository ID, never the name -
repositories get renamed, IDs do not."""

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
    """Master data from the HACS dataset."""

    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # GitHub repository ID
    category: Mapped[str] = mapped_column(String(32), index=True)
    full_name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    manifest_name: Mapped[str | None] = mapped_column(String(255))
    domain: Mapped[str | None] = mapped_column(String(128), index=True)
    topics: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    country: Mapped[str | None] = mapped_column(String(64))

    first_seen: Mapped[date] = mapped_column(Date, index=True)
    last_seen: Mapped[date] = mapped_column(Date, index=True)

    # Acceptance date from the git history of hacs/default. Not to be confused with
    # first_seen, which is the day THIS project first saw the repository.
    added_to_hacs: Mapped[date | None] = mapped_column(Date, index=True)

    # From /removed/data.json and /critical/data.json
    is_removed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    removal_type: Mapped[str | None] = mapped_column(String(128))
    removal_reason: Mapped[str | None] = mapped_column(Text)
    removal_link: Mapped[str | None] = mapped_column(Text)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class RepoGithub(Base):
    """Enrichment from the GitHub GraphQL API: the fields HACS does not have.

    pushed_at is kept but redundant: a sample against the GitHub API showed that HACS'
    last_updated matches pushed_at to the second. It stays as a control - if the two
    ever differ, something changed at the HACS source. The real gain of this step is
    is_archived, which exists nowhere else, and released_at.
    """

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
    # When GitHub no longer knows the repository (deleted/private), the reason is here.
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    watchers: Mapped[int | None] = mapped_column(Integer)
    open_issues_gh: Mapped[int | None] = mapped_column(Integer)
    closed_issues: Mapped[int | None] = mapped_column(Integer)

    # Release rhythm. Measured on a 611-repo sample, the median gap between the last
    # 15 releases is 5 days - which sounds like everything ships weekly and is an
    # artefact: those 15 releases cluster tightly even when the whole block is two
    # years old. Releases within the last year plus the age of the newest one are the
    # honest measures, so those are what get stored.
    releases_total: Mapped[int | None] = mapped_column(Integer)
    releases_year: Mapped[int | None] = mapped_column(Integer)
    releases_quarter: Mapped[int | None] = mapped_column(Integer)
    releases_year_capped: Mapped[bool | None] = mapped_column(Boolean)
    uses_prerelease: Mapped[bool | None] = mapped_column(Boolean)

    commits_year: Mapped[int | None] = mapped_column(Integer)
    commits_quarter: Mapped[int | None] = mapped_column(Integer)

    # GitHub's own current star count. Not displayed - the page shows HACS' figure, per
    # r.stars on Repo/Snapshot, sourced independently. This exists only to tell the
    # daily star refresh which repositories moved since yesterday without re-reading
    # every one of them; see star_history.py.
    stars_live: Mapped[int | None] = mapped_column(Integer)

    unavailable: Mapped[str | None] = mapped_column(String(64), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Snapshot(Base):
    """One data point per repository and day, the basis of every delta.
    If the sync runs several times a day, the day's last run wins."""

    __tablename__ = "snapshots"

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Nullable on purpose: the HACS dataset lacks stargazers_count for ~400 and
    # downloads for about two thirds of all repositories. NULL means "no value
    # delivered", not "zero stars" - a difference that matters for every sort.
    stars: Mapped[int | None] = mapped_column(Integer)
    downloads: Mapped[int | None] = mapped_column(Integer)
    open_issues: Mapped[int | None] = mapped_column(Integer)
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_version: Mapped[str | None] = mapped_column(String(128))
    last_commit: Mapped[str | None] = mapped_column(String(64))


class InstallSnapshot(Base):
    """Installation counts from Home Assistant analytics, per domain and day.
    An opt-in sample, not an absolute figure."""

    __tablename__ = "installs"

    domain: Mapped[str] = mapped_column(String(128), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    total: Mapped[int] = mapped_column(Integer)


class InstallVersion(Base):
    """Installations per domain, day and version - for the adoption of new releases."""

    __tablename__ = "installs_version"

    domain: Mapped[str] = mapped_column(String(128), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)


class StarEvent(Base):
    """Individual star timestamps from the one-time bootstrap via the stargazer API.
    Only the latest ~35 days, only so the 7/30-day columns are filled from day one."""

    __tablename__ = "star_events"

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    starred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)


class StarDaily(Base):
    """Stars gained per repository per day, from the bootstrap.

    Note what this counts: stars *added* on that day. Removed stars are invisible —
    GitHub's history endpoint reports additions, not net change. So a window sum is
    "stars given during this period", which is very slightly different from "change in
    the star count". Both are legitimate; this one is stated so nobody has to guess.

    Having this makes the whole reference-snapshot machinery unnecessary for stars: a
    7-day delta is a sum over seven rows, not a comparison against a snapshot that may
    or may not exist at the right date.
    """

    __tablename__ = "star_daily"

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    added: Mapped[int] = mapped_column(Integer)


class BootstrapState(Base):
    """Progress of the star bootstrap, so a run stopped by the rate limit or an
    interruption continues where it left off."""

    __tablename__ = "bootstrap_state"

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    stars_at_bootstrap: Mapped[int | None] = mapped_column(Integer)
    next_page: Mapped[int | None] = mapped_column(Integer)
    oldest_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class RemovedRepo(Base):
    """The HACS removal list as a table of its own.

    Checked: none of the removed repositories still appears in the current HACS
    dataset - removed really means removed. So the list is not a flag on existing
    repositories but a lookup: when a repository we tracked disappears, the reason is
    here.
    """

    __tablename__ = "removed_repos"

    repository: Mapped[str] = mapped_column(String(255), primary_key=True)
    removal_type: Mapped[str | None] = mapped_column(String(128), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[date] = mapped_column(Date)


class ListGap(Base):
    """Repositories on the official HACS category lists that have no dataset entry.

    Either fresh additions HACS' data generator has not picked up yet, or repositories
    that disappeared from GitHub. Tracked because a sudden rise in this number means
    the source is stuck - not that HACS is shrinking.
    """

    __tablename__ = "list_gaps"

    full_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    category: Mapped[str] = mapped_column(String(32))
    first_seen: Mapped[date] = mapped_column(Date)
    last_seen: Mapped[date] = mapped_column(Date, index=True)


class SourceEtag(Base):
    """ETags per source URL. Unchanged sources answer 304 and cost nothing - a courtesy
    to an endpoint the community pays for."""

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
        # WAL is faster but does not work on every file system (network drives, FUSE
        # mounts). If it fails, SQLite carries on in its default mode - slower, but
        # correct. No reason to stop the run.
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    return engine


def _add_missing_columns(engine) -> None:
    """Add columns that exist in the models but not yet in the file.

    create_all() only creates missing TABLES; it never touches an existing one. So
    every new field silently failed on any database created before it - the collector
    would run, hit "no such column" on the first write, and lose the batch. SQLite
    supports ADD COLUMN, which is enough for a schema that only ever grows.

    Anything beyond added columns (a renamed or retyped one) is out of scope on
    purpose: it would need a table rebuild, and pretending to handle it here would
    hide a real migration problem rather than solve it.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl = column.type.compile(engine.dialect)
                # A NOT NULL column cannot be added without a default; those are all
                # primary keys here, which only appear on new tables anyway.
                null = "" if column.nullable else " NOT NULL DEFAULT 0"
                conn.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl}{null}')
                )
                log.info("schema: added %s.%s", table.name, column.name)


log = __import__("logging").getLogger(__name__)


def make_session_factory(engine):
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)
