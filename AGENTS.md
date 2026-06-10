# Agent guide — cursor (shared contracts)

Conventions for humans and coding agents across Parcosm projects. This file lives in the **`common`** repo and describes patterns repeated in per-project `AGENTS.md` files (e.g. `openfigi`, `databento`). Each application repo should keep a short local `AGENTS.md` for project-specific table prefixes, modules, and cron — and link here for shared rules.

## Configuration Files

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
| Project-specific table keys | e.g. `figi_mappings_table`, `quotes_current_table` |

Loaded by `DatabaseCredentials` / `CastedDict` after the project passes a resolved credentials path.

## Database

Shared PostgreSQL policies below come from `openfigi/AGENTS.md` and `databento/AGENTS.md`. Project repos should link here and document only local table keys, modules, and cron.

### Connection

- Use `lib.db_connection.DatabaseCredentials(credentials_file=...)`.
- **`credentials_file` is required** in `common` — each project defines `DEFAULT_*` in its own `_paths` / `conf_paths` module.
- Supports `service=` (libpq) or discrete host/user/password fields; optional `db_opts`.
- `set_schema` creates the first schema in `search_path` if needed, then `SET search_path`.
- Use `.engine()` for pandas `to_sql()` (NullPool SQLAlchemy engine wrapping psycopg2).
- Read connection and table names from `conf/db_credentials.conf` (+ optional `.local`) via `CastedDict` or a project `load_conf()` wrapper — never hardcode credentials, database names, or table names in source or notebooks.



### Table naming in shared PostgreSQL

Each project that owns tables in a shared database uses a **mandatory prefix** on every table it creates. Names are configured in conf and validated before SQL interpolation.

| Project | Prefix | Conf / pattern | Example tables |
|---------|--------|----------------|----------------|
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

### Ingestors/ Downloaders ####

Ingestors/Downloaders are modules that proactively download some data

1. When possible, ingestors should save downloaded files onto their own folder in /data2/parcosm
2. Ingestors files should follow roughly ingestor-YYYY-MM-DD-filename.xxx format
2a. For multiple files per day ingestors use the structure ingestor_name/year/year-month/year-month-day/files-for-the-day
2b. for single file per day ingestors use intestor_name/year

3. Ingestors should be designed to restart safely, for example, if files for the day are found, skip them. 
4. Ingestors may populate databases at the very end of their process or simmultaneously with each download
5. Ingestors may populate database tables -- use prefix naming such as ingestor-tablename



### Calendar dates in database APIs (`YYYY-MM-DD`)

- Day-scoped DB accessors take market/session dates as **`YYYY-MM-DD` strings** (e.g. `price_history(symbol, "2026-06-03")`, `get_p_id_as_of(symbol, "2026-06-03")`), aligned with the ``date`` column — not bare `datetime`, unless an API explicitly documents otherwise.
- Parse at module boundaries with project helpers (`parse_session_date()`, `SESSION_DATE_FMT`, etc.).

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

Project-specific: `conf_paths`, `_paths`, domain DB modules, ingest, cron — remain in each application repo.

