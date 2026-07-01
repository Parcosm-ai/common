# Agent guide — Parcosm (shared contracts)

Conventions for humans and coding agents across Parcosm projects. 

This file lives in the **`common`** repo and describes patterns repeated in per-project `AGENTS.md` files (e.g. `openfigi`, `databento`). Each application repo should keep a short local `AGENTS.md` for project-specific table prefixes, modules, and cron — and link here for shared rules.


### Ingestors/ Downloaders ####

Ingestors/Downloaders are modules that proactively download some data

1. When possible, ingestors should save downloaded files onto their own folder in /data2/parcosm
2. Ingestors' files should follow roughly ingestor-YYYY-MM-DD-filename.xxx format
2a. For multiple files per day ingestors use the structure ingestor_name/year/year-month/year-month-day/files-for-the-day
2b. for single file per day ingestors use ingestor_name/year

3. Ingestors should be designed to restart safely, for example, if files for the day are found, skip them. 
4. Ingestors may populate databases either at the very end of their process or simmultaneously with each download
5. Ingestors may populate database tables -- use prefix naming such as ingestor_tablename
6. Preserve raw data as much as possible, especially on the files saved on disk -- save raw jsons etc.
6b. For very busy downloaders that might generate tons of disk space, discuss the merits of overriding the raw data rule
6c. **Capture-at-discovery for signed/expiring URLs.** When a source serves a raw asset behind a *signed, time-limited, session-scoped, or CDN-expiring* URL (media/audio, presigned S3-style links, one-shot download tokens), download and persist the asset the **instant the URL resolves** — in the SAME step that discovers it. Do NOT defer the download behind later processing (queueing, a separate transcribe/parse stage, the next cron run): the URL expires and the asset is gone, often silently. If capture and heavy processing must be separate stages, split them so *capture* runs first and independently (e.g. bank the audio now, transcribe later). Learned the hard way on earnings-call webcasts — a whole retroactive quarter was lost to replay-window expiry before we moved capture to discovery time.
7. Always save the timestamp of the download and add a column updated_timestamp to the database tables
 - So in addition to any provider timestamps or date information (e.g. "this is the AAPL closing value for 2016-01-01") we also have the  "this is the exact date and time when our data provider said so" 

### Data-quality guardrails (detect, quarantine — don't silent-delete)

Real-world sources fail in *silent, recurring classes*, not just loud errors. Ad-hoc one-off fixes
don't hold — the same class recurs next run. Two shared rules:

1. **Every data-quality failure class becomes a PERMANENT, automated detection stage** in the
   pipeline (a wired-in check that runs every pass), not a manual clean-up you do once. When you
   discover a new way the data can be wrong, ship the *detector* alongside the fix. Classes seen
   repeatedly (build a guard for each as they appear):
   - **Duplicate content across periods** — the same record content attributed to ≥2 distinct
     periods of the same entity (e.g. one transcript/file replicated across quarters because an
     adapter fell back to a prior-period URL). Byte-identical content across distinct periods is
     provably wrong.
   - **Future-dated records** — a record whose event date is in the future can't have really
     occurred; content on it is a dup/mislabel/mis-date. A future-dated "ready" record is always a
     DQ signal.
   - **Wrong-entity / wrong-type content** — the captured artifact isn't the intended entity or type
     (a different filing, a conference vs the earnings call). Validate the artifact IS what the row
     claims, at every step; prefer capturing **nothing** over capturing wrong content.

2. **Quarantine, never silent-delete.** A row that fails a guard (or is uncertain) is NOT deleted
   and NOT dropped from the raw tables. Mark it with a **confidence flag** (e.g. `content_confidence
   = 'low'`) plus a **machine-readable reason** (e.g. `pending_reason = 'duplicate_content'`,
   `'future_dated'`), and EXCLUDE it from the "ready"/ground-truth/accessor views via that flag.
   This keeps the decision **reversible and auditable** — a later good capture reclaims the row, and
   you can always see *why* something was withheld. Correctness beats idempotency: when a better
   version of a record arrives, replace the worse one rather than preserving the stale row for
   idempotency's sake.

### Ingest and job status (shared `pcom_status_*` tables)

Every **ingestor, downloader, and downstream analyzer** publishes operational status to a **single pair of tables** owned by the `common` project (`pcom_` prefix). Do not create per-project status tables.

| Table | Role |
|-------|------|
| `pcom_status_all` | Append-only **event log** — one row per status transition (`running`, `failed`, `complete`, …) |
| `pcom_status_latest` | **Snapshot** — one row per `(project, job_key)` for fast reads |

Configure table names in `conf/db_credentials.conf` (optional; defaults above):

| Key | Purpose |
|-----|---------|
| `status_all_table` | Event log table name (default `pcom_status_all`) |
| `status_latest_table` | Snapshot table name (default `pcom_status_latest`) |

**Publish at phase boundaries** (start, success, failure) — not per row of domain data. Use `lib.ingest_status.IngestStatusStore.publish_status()` so the event log and snapshot stay in sync inside one transaction.

| Column (both tables where applicable) | Purpose |
|---------------------------------------|---------|
| `project` | Owning module, e.g. `wikipedia`, `databento`, `my_analysis` |
| `job_key` | Stable job id within the project, e.g. `download`, `hist_close` |
| `status` | `pending`, `running`, `complete`, `failed`, `skipped` |
| `event_at` / `last_event_at` | When this event happened (UTC `timestamptz`) |
| `last_success_at` | Snapshot only — last `complete` time; unchanged on `running` / `failed` |
| `session_date` | Target calendar day (`date`) on successful completion when relevant |
| `artifact_version` | Comparable id from last success (ISO date, build id, content hash) |
| `message` | Human-readable text for dashboards |
| `metadata` | Optional `jsonb` for paths, counts, error detail |
| `updated_timestamp` | When Parcosm wrote the row |

**Two “latest” meanings** (do not conflate):

- `get_latest_status(project, job_key)` → current `status` and `last_event_at` (any transition).
- `get_latest_completion(project, job_key)` → `last_success_at`, `session_date`, `artifact_version` from the last successful run.

Listeners compare upstream `artifact_version` or `last_success_at` against their own cursor row (e.g. `project='my_app'`, `job_key='wikipedia_sync'`). Dashboards call `list_latest_statuses()` for a single-table overview.

```python
from lib.db_connection import DatabaseCredentials
from lib.ingest_status import IngestStatusStore, STATUS_RUNNING, STATUS_COMPLETE

db = DatabaseCredentials(credentials_file="/abs/path/to/conf/db_credentials.conf")
store = IngestStatusStore.from_credentials(db)
store.ensure_tables()

store.publish_status("wikipedia", "download", STATUS_RUNNING, message="download in progress")
store.publish_status(
    "wikipedia",
    "download",
    STATUS_COMPLETE,
    message="download 2026-06-02 complete",
    session_date="2026-06-02",
    artifact_version="2026-06-02",
)

latest = store.get_latest_status("wikipedia", "download")
done = store.get_latest_completion("wikipedia", "download")
```

## Ingestors must care about pulling/syncing context information at ingestion time

When data interpretation is context-sensitive, maintain parallel context tables to help in future access, for example:
- The databento data tables use "symbol" to identify companies
- But symbols may change meanings along time, for example *V* Vivendi until 2006, *V* Visa since 2008
- Thus projects are required to keep context tables to help in retrieving backdated info, for example, in order to properly decode V depending on the date, we can keep a separate table with the Symbol-OpenFIGI equivalences for the dates.
- As an example, the databento project refreshes openfigi-symbol tables by way of calling the openfigi project, so that a daily table with all symbols and their openfigi mappings are persisted. 


## Databases

Shared PostgreSQL policies below come from `openfigi/AGENTS.md` and `databento/AGENTS.md`. Project repos should link here and document only local table keys, modules, and cron.


### Table naming in Databases

Each project that owns tables in a shared database uses a **mandatory prefix** on every table it creates. Names are configured in conf and validated before SQL interpolation.

| Project | Prefix | Conf / pattern | Example tables |
|---------|--------|----------------|----------------|
| common | `pcom_` | `status_all_table`, `status_latest_table` | `pcom_status_all`, `pcom_status_latest` |
| openfigi | `ofigi_` | `figi_mappings_table` → base name | `ofigi_mappings_daily`, `ofigi_mappings_latest` |
| databento | `dbento_` | `quotes_history_table`, `quotes_current_table` | `dbento_quotes_history`, `dbento_quotes_current` |
| (others) | per project `AGENTS.md` | … | … |

Rules:

- Configure table names in conf (full name or base + documented suffixes), not Python string literals.
- Validate with `project_table_identifier()` (or equivalent): match `[A-Za-z_][A-Za-z0-9_]*` and the required prefix.
- **Do not** create unprefixed tables in shared databases.
- Table and schema names are **not** SQL bind parameters — use validated identifiers only; pass **values** as query parameters.

Implement `sql_identifier()` / `project_table_identifier()` in each project's `conf_paths` or `_paths` module (prefix constant + regex), mirroring `openfigi._paths` and `databento` `lib/conf_paths.py`.

### SQL safety

- Never interpolate unvalidated user input into identifiers.
- Use validated identifiers for dynamic table/schema names.

### Atomicity / Double Buffering

Data must drop into the live database insuring atomicity, so that a process reading that data does not get conflicting records

a) when simple enough, just ensure single transaction updates with BEGIN ... COMMIT
b) for highly complex, large downloads (such as wikipedia) use the schema drop double buffering pattern:
- populate new table versions on a working schema, in the background
- when ready: BEGIN, move current tables to schema "recycling_bin", move new tables to schema "public", COMMIT
  

### Bulk insertions

**Always use PostgreSQL bulk load paths when inserting more than 10 rows.** When in doubt, use them anyway.

Preferred mechanisms (already used across cursor repos):

- `psycopg2.extras.execute_values` for batched `INSERT … VALUES %s`
- `cursor.copy_expert` / `COPY … FROM STDIN` for large flat files (marketstack ingest, panopticon staging)

Avoid row-by-row `INSERT` loops for non-trivial batch sizes. Large ETL scripts in marketstack2 favor `COPY` for throughput — same principle applies to new code.

### Current vs historical (no `is_current`)

When data is refreshed **daily or more often** and callers need a **fast path to the latest** value per key (symbol, ticker, etc.):

- **Do** maintain a **separate current/snapshot table** (or `{base}_latest`, `*_current_table`) updated on each ingest.
- **Do** keep **historical** rows in an append-only or date-keyed table (typically `*_all`).
- **Do not** use an `is_current` boolean (or equivalent flag) on a single wide table as the primary access pattern.

Rationale: point lookups and `most_recent`-style APIs stay indexed and simple; history stays append-only without flag maintenance.

#### Reference layouts

**openfigi** — conf base `figi_mappings_table` (e.g. `ofigi_mappings`):

| Table | Role |
|-------|------|
| `{base}_daily` | Historical by calendar `date` + `symbol`; day-scoped reads (`get_p_id_as_of`, `YYYY-MM-DD`) |
| `{base}_latest` | Current snapshot per `symbol`; default accessor / `get_p_id` |

No `is_current` column. Prefix `ofigi_` enforced on the base name.

**databento** — conf keys `quotes_history_table`, `quotes_current_table`:

| Table | Role |
|-------|------|
| `*_1m_(all, current)` | 1m quotes with timestamps provided by databento between 9:30 and 16:00 daily
| `*_hist_(all,current)` | historical (closing) data publish by databento at midnight after closing

Both tables carry a **`date`** column (`date` type): US equity **market calendar day** (`America/New_York` date of `ts_recv`), computed on ingest. Filter day-scoped history with `date`, not by converting stored timestamps to Eastern in application code.

### Timestamps and market dates (database columns)

- Store live/vendor event times as **UTC** (`timestamptz`) — e.g. `ts_event`, `ts_recv` from nanosecond or ISO sources.
- Add a **`date`** (`date` type) column where day-scoped queries matter; set it at ingest from the market calendar (not at read time).
- How `psql` displays `timestamptz` depends on the client `TIME ZONE`; storage remains UTC.

### Rules for storing data from data providers

- Store raw values from data provider as much as possible
- Always add a updated_timestamp column reflecting the time stamp of when the data was obtained by Parcosm and added to the database

### Calendar dates in database APIs (`YYYY-MM-DD`)

- Day-scoped DB accessors take market/session dates as **`YYYY-MM-DD` strings** (e.g. `price_history(symbol, "2026-06-03")`, `get_p_id_as_of(symbol, "2026-06-03")`), aligned with the ``date`` column — not bare `datetime`, unless an API explicitly documents otherwise.
- Parse at module boundaries with project helpers (`parse_session_date()`, `SESSION_DATE_FMT`, etc.).

## Agent and tool configuration files

Prefer **vendor-agnostic names** for agent instructions and skill definitions so they are readable by any tool.

| Purpose | Preferred | Avoid |
|---------|-----------|-------|
| Agent instructions / rules | `AGENTS.md` | `CLAUDE.md`, `.cursorrules`, `copilot-instructions.md` |
| Skill / command definitions | `.agents/commands/<skill>.md` | `.claude/commands/`, `.cursor/commands/` |
| Machine-local tool settings | vendor directory is fine (e.g. `.claude/settings.local.json`) | — |

**Rules:**

- Every repo's agent instructions live in `AGENTS.md` at the root (and link to `common/AGENTS.md`).
- Reusable skills (install, configure, run, etc.) are `.md` files under `.agents/commands/`.  
  Tool-specific directories (`.claude/commands/`) may symlink to `.agents/commands/` so native slash-command lookup still works — the canonical source stays in `.agents/`.
- Vendor-specific tooling config (e.g. `.claude/settings.local.json`, `.vscode/settings.json`) is fine where it must live; only *content files* (instructions, skills) should be kept vendor-agnostic.
- Never create a `CLAUDE.md` when `AGENTS.md` serves the same purpose.

## Git and commits

- **Commit:** `conf/*.example`, application code, tests, docs without secrets.
- **Do not commit:** live conf with credentials, `conf/*.local`, `.env`, notebooks with embedded keys.

## Python packaging

- Prefer **`uv`** + `pyproject.toml` for projects that already use it.
- Shared utilities: editable path dependency on `../common` (`cursor-common`), package name on disk remains `lib`.
- Application code stays in named packages (`openfigi`, `price_logger`, `mstack2`, …), not in `lib/` except shared helpers.

## Operations (where applicable)

### Hetzner / cron (databento and similar)

- Server timezone may be **CEST**; crontabs and launch windows should account for DST.
- Cron entry scripts should exit promptly when it is not the correct session window.
- Prefer a single shell wrapper in crontab that delegates to `python -m …` with documented flags (`--cron`, `--lock`, etc.).

### Logging and locks

- Long-running ingest: file locks under `var/` or configured paths; quiet exit if another process holds the lock.

## Per-project agent guides

Each repo's `AGENTS.md` should:

1. State what the project does and its module map.
2. Link to this file for shared conf/DB/git rules.
3. Document **only** project-specific prefixes, conf keys, cron, and APIs.

| Project | Local guide |
|---------|-------------|
| openfigi | `openfigi/AGENTS.md` — accessor modes, `{base}_daily` / `{base}_latest`, smoke test |
| databento | `databento/AGENTS.md` — live ingest cron, `dbento_` tables, ingest flags |
| others | Add or extend `AGENTS.md` when agents work there regularly |

## Implementation map (`common` only)

| Concern | Module |
|---------|--------|
| Typed conf loader | `lib/casted_dict.py` |
| PostgreSQL connection | `lib/db_connection.py` |
| Ingest / job status tables and accessors | `lib/ingest_status.py` |

Project-specific: `conf_paths`, `_paths`, domain DB modules, ingest, cron — remain in each application repo.

-----------

## Configuration Files Library

### Read conf with `CastedDict` 

- Load **all** project config through `CastedDict` (`lib/casted_dict.py` from `common` once migrated), never ad-hoc line parsing in application code.
- Each project should expose a small path helper that resolves conf relative to the repo root and merges **`.local`** automatically:
  - `openfigi._paths.load_conf("db_credentials.conf")` → `conf/<name>`
  - `databento` / others: `lib/conf_paths.load_conf("conf/….conf")`
- Prefer absolute paths from the helper so scripts work regardless of cwd.

```python
from lib.casted_dict import CastedDict

# After migration: from lib.casted_dict import CastedDict  # via cursor-common dep
conf = CastedDict("/abs/path/to/project/conf/db_credentials.conf")
schema = conf["schema"]
```

### Conf file format

- Whitespace-separated lines: `key value type` (tab or spaces).
- Quote values that contain spaces: `"my value" str`.
- Lists: `[a, b, c]` with optional type suffix.
- Types: `str`, `int`, `float`, `bool`, `date`, `timestamp`, `path`, `filepath`, `list`.
- Environment expansion via `$VAR` in values (`string.Template`).
- CLI override: `-c key=value` when the process parses `sys.argv`.

### `.local` files

- Override: sibling `conf/<name>.conf.local` (same format as base).
- `CastedDict` loads base then `.local` when either exists under cwd, absolute path, or `sys.path`.
- **Never commit** `*.local`, live `conf/*.conf` with secrets, or `.env`.

### Secrets and keys in conf, not in code

- API keys, passwords, connection strings, database names, and **table names** belong in conf (or conf keys that name tables), not in source or notebooks.
- Document keys in `conf/*.example`; keep real values gitignored.
- Typical `conf/db_credentials.conf` keys:

| Key | Purpose |
|-----|---------|
| `service` **or** `database` / `host` / `user` / `password` / `port` | PostgreSQL connection |
| `schema` | `search_path` (e.g. `public` or `project, public`) |
| `status_all_table` / `status_latest_table` | Shared ingest status tables (defaults `pcom_status_all`, `pcom_status_latest`) |
| Project-specific table keys | e.g. `figi_mappings_table`, `quotes_current_table` |

Loaded by `DatabaseCredentials` / `CastedDict` after the project passes a resolved credentials path.


### Database Connection Library

- Use `lib.db_connection.DatabaseCredentials(credentials_file=...)`.
- **`credentials_file` is required** in `common` — each project defines `DEFAULT_*` in its own `_paths` / `conf_paths` module.
- Supports `service=` (libpq) or discrete host/user/password fields; optional `db_opts`.
- `set_schema` creates the first schema in `search_path` if needed, then `SET search_path`.
- Use `.engine()` for pandas `to_sql()` (NullPool SQLAlchemy engine wrapping psycopg2).
- Read connection and table names from `conf/db_credentials.conf` (+ optional `.local`) via `CastedDict` or a project `load_conf()` wrapper — never hardcode credentials, database names, or table names in source or notebooks.

